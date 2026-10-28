"""
Hybrid Retriever — BM25 + Dense (Chroma) combined.
Uses rank_bm25 directly (NO langchain_community, NO pydantic inheritance).
BM25 handles exact statutory references (IPC 302, Section 438 CrPC).
Dense handles semantic similarity for contextual legal arguments.

Score merging: 0.4 × bm25_norm + 0.6 × dense_norm (manual, not EnsembleRetriever).
"""

import re
import logging
from typing import List, Tuple

import numpy as np
from rank_bm25 import BM25Okapi
from langchain_core.documents import Document
from langchain_chroma import Chroma
from sentence_transformers import SentenceTransformer
import chromadb

from core.normalize import html_to_text, normalize

logger = logging.getLogger(__name__)

from core.config import settings as _settings

CHROMA_DIR = str(_settings.chroma_dir)
COLLECTION_NAME = "courtroom_judgments"
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"


class BGEEmbeddings:
    """Wrapper to use SentenceTransformer with LangChain Chroma."""

    def __init__(self, model: SentenceTransformer):
        self.model = model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        prefixed = [f"Represent this legal document: {t}" for t in texts]
        return self.model.encode(prefixed).tolist()

    def embed_query(self, text: str) -> List[float]:
        prefixed = f"Represent this legal query for retrieving relevant documents: {text}"
        return self.model.encode([prefixed])[0].tolist()


class DirectBM25:
    """
    BM25 retriever using rank_bm25 directly.
    No pydantic, no BaseRetriever — zero v1/v2 conflicts.
    """

    def __init__(self, docs: List[Document], k: int = 10):
        self.docs = docs
        self.k = k
        tokenized = [doc.page_content.lower().split() for doc in docs]
        self.bm25 = BM25Okapi(tokenized)
        logger.info(f"DirectBM25 initialized with {len(docs)} documents, k={k}")

    def invoke(self, query: str) -> List[Tuple[float, Document]]:
        """Return (score, Document) tuples sorted by BM25 score descending."""
        tokens = query.lower().split()
        scores = self.bm25.get_scores(tokens)
        top_idx = np.argsort(scores)[::-1][:self.k]
        return [(float(scores[i]), self.docs[i]) for i in top_idx if scores[i] > 0]


def _normalize_scores(scored_docs: List[Tuple[float, Document]]) -> List[Tuple[float, Document]]:
    """Normalize scores to [0, 1] range using min-max normalization."""
    if not scored_docs:
        return []

    scores = [s for s, _ in scored_docs]
    min_s = min(scores)
    max_s = max(scores)
    spread = max_s - min_s

    if spread == 0:
        # All scores identical — assign uniform 1.0
        return [(1.0, doc) for _, doc in scored_docs]

    return [((s - min_s) / spread, doc) for s, doc in scored_docs]


def _chunk_key(doc: Document) -> str:
    """One entry per chunk, not per judgment (doc_id alone merged all chunks of a case)."""
    return f"{doc.metadata.get('doc_id', '')}#{doc.metadata.get('chunk_index', '')}" if doc.metadata.get("doc_id") else doc.page_content[:100]


class LegalHybridRetriever:
    """
    Combines BM25 + semantic retrieval for legal queries.
    Manual score merging: 0.4 × bm25_norm + 0.6 × dense_norm.
    """

    def __init__(
        self,
        bm25_weight: float = 0.4,
        dense_weight: float = 0.6,
        k: int = 10,
    ):
        self.k = k
        self.bm25_weight = bm25_weight
        self.dense_weight = dense_weight

        logger.info("Loading embedding model...")
        self.model = SentenceTransformer(EMBEDDING_MODEL)
        self.embedding_fn = BGEEmbeddings(self.model)

        logger.info("Setting up retrievers...")
        self._setup_retrievers()
        logger.info("LegalHybridRetriever ready.")

    def _setup_retrievers(self) -> None:
        """Load documents from Chroma, build BM25 index and dense retriever."""
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        collection = client.get_collection(COLLECTION_NAME)
        data = collection.get(include=["documents", "metadatas"])

        if not data["documents"]:
            raise ValueError("Chroma DB is empty. Run embedder.py first.")

        logger.info(f"Loaded {len(data['documents'])} documents from Chroma")

        # Build LangChain Documents for BM25
        # Chunks are stored as Indian Kanoon HTML; BM25 must see text, not tags.
        all_docs = [
            Document(page_content=self._clean_html(text), metadata=meta or {})
            for text, meta in zip(data["documents"], data["metadatas"])
        ]

        # BM25 retriever (plain class, no pydantic)
        self.bm25 = DirectBM25(docs=all_docs, k=self.k)

        # Dense retriever via Chroma
        self.dense_vectorstore = Chroma(
            client=client,
            collection_name=COLLECTION_NAME,
            embedding_function=self.embedding_fn,
        )

    def _dense_search(self, query: str) -> List[Tuple[float, Document]]:
        """Run dense similarity search and return (score, Document) tuples."""
        results = self.dense_vectorstore.similarity_search_with_relevance_scores(
            query, k=self.k
        )
        # Returns list of (Document, score) — flip to (score, Document)
        return [(score, doc) for doc, score in results]

    def _merge_scores(
        self,
        bm25_results: List[Tuple[float, Document]],
        dense_results: List[Tuple[float, Document]],
    ) -> List[Document]:
        """
        Manual score merging:
        1. Normalize both score lists to [0, 1]
        2. Final score = 0.4 × bm25_norm + 0.6 × dense_norm
        3. Sort descending, return top k Documents
        """
        # Normalize scores
        bm25_normed = _normalize_scores(bm25_results)
        dense_normed = _normalize_scores(dense_results)

        # Build score lookup by doc identity (use page_content hash as key)
        merged: dict[str, Tuple[float, Document]] = {}

        for score, doc in bm25_normed:
            doc_key = _chunk_key(doc)
            merged[doc_key] = (self.bm25_weight * score, doc)

        for score, doc in dense_normed:
            doc_key = _chunk_key(doc)
            if doc_key in merged:
                existing_score, existing_doc = merged[doc_key]
                merged[doc_key] = (existing_score + self.dense_weight * score, existing_doc)
            else:
                merged[doc_key] = (self.dense_weight * score, doc)

        # Sort by final score descending
        sorted_results = sorted(merged.values(), key=lambda x: x[0], reverse=True)

        # Return top k Documents with hybrid score in metadata
        output = []
        for score, doc in sorted_results[:self.k]:
            doc.metadata["hybrid_score"] = round(score, 4)
            output.append(doc)

        return output

    def _clean_html(self, text: str) -> str:
        """Strip HTML from Indian Kanoon text with the same normaliser the verifier uses."""
        return normalize(html_to_text(text))

    def retrieve(self, query: str) -> List[Document]:
        """
        Run hybrid retrieval: BM25 + dense → normalize → merge → clean HTML.
        Returns top k Documents sorted by hybrid score.
        """
        # Get results from both retrievers
        bm25_results = self.bm25.invoke(query)
        dense_results = self._dense_search(query)

        logger.info(
            f"BM25 returned {len(bm25_results)} docs, "
            f"Dense returned {len(dense_results)} docs"
        )

        # Merge with weighted scores
        merged_docs = self._merge_scores(bm25_results, dense_results)

        # Clean HTML from all retrieved docs
        for doc in merged_docs:
            doc.page_content = self._clean_html(doc.page_content)

        logger.info(f"Hybrid retrieval returned {len(merged_docs)} merged docs")
        return merged_docs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    retriever = LegalHybridRetriever()
    test_queries = [
        "bail application murder case IPC 302",
        "dowry harassment wife Section 498A",
        "cheating fraud IPC 420 conviction",
    ]
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"QUERY: {query}")
        results = retriever.retrieve(query)
        print(f"Retrieved: {len(results)} documents")
        for i, doc in enumerate(results[:3]):
            print(f"\n  [{i+1}] {doc.metadata.get('title', 'N/A')[:60]}")
            print(f"       Court: {doc.metadata.get('court', 'N/A')}")
            print(f"       Hybrid Score: {doc.metadata.get('hybrid_score', 'N/A')}")
            print(f"       Text: {doc.page_content[:120]}...")