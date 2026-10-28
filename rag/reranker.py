"""
CrossEncoder Reranker.
Takes top-K from hybrid retrieval, reranks by actual relevance to query.
Why needed: BM25 + dense retrieval gives good recall but noisy ranking.
CrossEncoder reads query+passage together — much better at judging relevance.
Model: ms-marco-MiniLM-L-6-v2 — small, fast, strong.
"""

from typing import List, Tuple
from langchain_core.documents import Document
from sentence_transformers import CrossEncoder

RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class LegalReranker:
    def __init__(self, top_n: int = 5):
        """
        top_n: how many documents to return after reranking
        Load model once, reuse across calls.
        """
        self.top_n = top_n
        print(f"[RERANKER] Loading {RERANKER_MODEL}...")
        self.model = CrossEncoder(RERANKER_MODEL)
        print("[RERANKER] Ready.")

    def rerank(self, query: str, documents: List[Document]) -> List[Document]:
        """
        Rerank retrieved documents by relevance to query.
        Returns top_n documents in ranked order.
        """
        if not documents:
            return []

        # CrossEncoder needs (query, passage) pairs
        pairs = [(query, doc.page_content) for doc in documents]
        scores = self.model.predict(pairs)

        # Sort by score descending
        scored_docs = sorted(
            zip(scores, documents),
            key=lambda x: x[0],
            reverse=True
        )

        # Add reranker score to metadata for transparency
        reranked = []
        for score, doc in scored_docs[:self.top_n]:
            doc.metadata["reranker_score"] = round(float(score), 4)
            reranked.append(doc)

        return reranked

    def rerank_with_scores(self, query: str, documents: List[Document]) -> List[Tuple[float, Document]]:
        """Same as rerank but returns (score, doc) tuples — useful for citation verifier."""
        if not documents:
            return []

        pairs = [(query, doc.page_content) for doc in documents]
        scores = self.model.predict(pairs)

        scored = sorted(
            zip(scores.tolist(), documents),
            key=lambda x: x[0],
            reverse=True
        )
        return scored[:self.top_n]


if __name__ == "__main__":
    # Quick test — plug in your retriever results here
    from langchain_core.documents import Document

    sample_docs = [
        Document(page_content="The accused was granted bail under IPC 302 after the court considered...", metadata={}),
        Document(page_content="In matrimonial disputes under Section 498A, the court held that...", metadata={}),
        Document(page_content="The High Court dismissed the bail application citing flight risk...", metadata={}),
    ]

    reranker = LegalReranker(top_n=2)
    results = reranker.rerank("bail application murder case", sample_docs)

    for doc in results:
        print(f"Score: {doc.metadata['reranker_score']} | {doc.page_content[:100]}")
