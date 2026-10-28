"""Pipeline behaviour that needs no models or keys."""

import dataclasses
import time

import core.pipeline as P


def test_retrieval_timeout_abstains_instead_of_hanging(monkeypatch):
    class SlowRetriever:  # MOCK: simulates a locked index
        def retrieve(self, q):
            time.sleep(2)
            return []

    class Reranker:  # MOCK
        def rerank(self, q, docs):
            return docs

    class NoLLM:  # MOCK: the search-query rewrite fails fast, so no live call in a unit test
        def structured(self, *a, **k):
            raise P.LLMError("mock")

    monkeypatch.setattr(P, "get_llm", lambda: NoLLM())
    monkeypatch.setattr(P, "_retrieval_models", lambda: (SlowRetriever(), Reranker()))
    monkeypatch.setattr(P, "settings", dataclasses.replace(P.settings, retrieval_timeout_s=0.2))
    state = P.initial_state("FIR text " * 10)
    state["intake_data"] = P.Intake().model_dump()
    t0 = time.time()
    out = P.retrieve_node(state)
    assert time.time() - t0 < 1.5
    assert out["abstained"] is True and out["passages"] == []
    assert "took too long" in out["trace"][-1]["detail"]


def test_strategy_refs_are_cleaned():
    assert P._clean_refs(["[F2]", "P1.", " M3 ", "none"]) == ["F2", "P1", "M3"]
