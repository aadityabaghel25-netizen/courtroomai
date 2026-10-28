"""
Unit and Integration tests for Legal Hybrid Retriever and Citation Verifier.
"""

import pytest

pytestmark = pytest.mark.models  # downloads models; not run in CI
from langchain_core.documents import Document
from rag.hybrid_retriever import DirectBM25
from rag.reranker import LegalReranker


def test_direct_bm25_retriever():
    docs = [
        Document(page_content="Murder punishable under Section 302 IPC with life imprisonment or death.", metadata={"doc_id": "1"}),
        Document(page_content="Bail under Section 438 CrPC for anticipatory protection.", metadata={"doc_id": "2"}),
        Document(page_content="Cheating under Section 420 IPC for dishonestly inducing property transfer.", metadata={"doc_id": "3"}),
    ]

    retriever = DirectBM25(docs=docs, k=2)
    results = retriever.invoke("Section 302 IPC murder")

    assert len(results) > 0
    assert "302" in results[0][1].page_content


def test_reranker():
    sample_docs = [
        Document(page_content="The accused was granted bail under IPC 302 after considering flight risk.", metadata={}),
        Document(page_content="In matrimonial disputes under Section 498A IPC, domestic violence alleged.", metadata={}),
    ]

    reranker = LegalReranker(top_n=1)
    results = reranker.rerank("bail for murder charge IPC 302", sample_docs)

    assert len(results) == 1
    assert "reranker_score" in results[0].metadata
    assert "302" in results[0].page_content
