"""
The six adversarial tests required by the build prompt. None of them mocks the
verifier; where a model is involved the *judge* or the *HTTP client* is a
labelled test double, and live variants run against Token Factory.
"""

import types

import pytest

from tests.helpers import FIXTURE_JUDGMENT, stub_judge
from core.audit import ExtractedCitation, audit_one
from core.claims import Claim, ClaimType, JudgeVerdict, JudgmentPassage, Status
from core.lint import lint_text
from core.llm import LLMError, TokenFactoryLLM
from core.verifiers import verify_precedent

REAL_QUOTE = "We hold that anticipatory bail may be granted where the accused has joined the investigation and there is no risk of flight."


def precedent(case_id: str, quote: str, text: str = "Anticipatory bail may be granted where the accused joined the investigation and is not a flight risk."):
    return Claim(id="P1", type=ClaimType.precedent_holding, text=text,
                 evidence=[JudgmentPassage(case_id=case_id, quote=quote)])


# 1 -----------------------------------------------------------------------
def test_fabricated_case_id_is_rejected(store):
    out = verify_precedent(precedent("999999999", REAL_QUOTE), store, stub_judge("supports", REAL_QUOTE))
    assert out.status == Status.failed
    assert "not in the corpus" in out.reason


# 2 -----------------------------------------------------------------------
def test_real_case_with_altered_quote_is_rejected(store):
    altered = REAL_QUOTE.replace("may be granted", "must always be granted")
    out = verify_precedent(precedent("MOCK-0001", altered), store, stub_judge("supports", altered))
    assert out.status == Status.failed
    assert "not found verbatim" in out.reason


# 3 -----------------------------------------------------------------------
def test_real_quote_for_unsupported_proposition_not_passed(store):
    claim = precedent("MOCK-0001", REAL_QUOTE, text="Bail must be refused in every grave offence.")
    for verdict in ("not_addressed", "contradicts", "partial"):
        out = verify_precedent(claim, store, stub_judge(verdict, REAL_QUOTE))
        assert out.status != Status.passed, verdict


@pytest.mark.live
def test_live_ultra_rejects_unsupported_proposition(store):
    from core.llm import get_llm
    llm = get_llm()

    def judge(prompt):
        return llm.structured("judge", [{"role": "user", "content": prompt}], JudgeVerdict, max_tokens=4000)

    claim = precedent("MOCK-0001", REAL_QUOTE, text="Bail must be refused in every grave offence.")
    out = verify_precedent(claim, store, judge)
    # The judge must really have answered; a failed call would also be "not passed".
    assert out.evidence[0].judge_verdict is not None, out.reason
    assert out.status != Status.passed, out.reason


# 4 -----------------------------------------------------------------------
def test_lint_removes_sentence_with_extra_case_name_or_figure():
    passed = ["The accused snatched his mobile phone near the bus stand.",
              "Mock Petitioner vs State Of Testland held that anticipatory bail may be granted."]
    text = ("The accused snatched his mobile phone near the bus stand. "
            "See also Arnesh Kumar v. State of Bihar on arrest. "
            "Bail was granted in 87 percent of similar cases. "
            "Mock Petitioner vs State Of Testland held that anticipatory bail may be granted.")
    res = lint_text(text, passed)
    assert "Arnesh" not in res.text
    assert "87" not in res.text
    assert "bus stand" in res.text and "Mock Petitioner" in res.text
    assert len(res.drops) == 2


# 5 -----------------------------------------------------------------------
class _FakeClient:
    """MOCK HTTP client: returns canned completions in order."""
    def __init__(self, replies):
        self.replies = list(replies)
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))

    def _create(self, **kw):
        content = self.replies.pop(0)
        msg = types.SimpleNamespace(content=content)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)],
                                     usage=types.SimpleNamespace(prompt_tokens=1, completion_tokens=1))


def test_malformed_judge_json_becomes_unverified(store):
    llm = TokenFactoryLLM(client=_FakeClient(["this is not json", "{\"verdict\": \"maybe\"}"]))

    def judge(prompt):
        return llm.structured("judge", [{"role": "user", "content": prompt}], JudgeVerdict)

    with pytest.raises(LLMError):
        judge("x")
    llm = TokenFactoryLLM(client=_FakeClient(["not json", "still not json"]))
    out = verify_precedent(precedent("MOCK-0001", REAL_QUOTE), store,
                           lambda p: llm.structured("judge", [{"role": "user", "content": p}], JudgeVerdict))
    assert out.status == Status.unverified


def test_judge_quote_not_in_judgment_becomes_unverified(store):
    invented = "Anticipatory bail is a fundamental right of every accused."
    out = verify_precedent(precedent("MOCK-0001", REAL_QUOTE), store, stub_judge("supports", invented))
    assert out.status == Status.unverified
    assert "not in the judgment text" in out.reason


# 6 -----------------------------------------------------------------------
def test_audit_real_and_fake_citation_get_different_verdicts(store):
    real = ExtractedCitation(case_name="Mock Petitioner v. State of Testland", citation="(2020) 1 MOCK 1",
                             proposition="Anticipatory bail may be granted where the accused joined the investigation and is not a flight risk.")
    fake = ExtractedCitation(case_name="Imaginary Singh v. Union of Nowhere", citation="(2031) 99 SCC 999",
                             proposition="Bail is automatic for all offences.")
    judge = stub_judge("supports", REAL_QUOTE)
    no_web = lambda q: []  # MOCK: web search finds nothing
    v_real = audit_one(0, real, store, judge, no_web)
    v_fake = audit_one(1, fake, store, judge, no_web)
    assert v_real.verdict == "verified"
    assert v_fake.verdict == "not_found"
    assert v_real.verdict != v_fake.verdict


def test_point_that_just_repeats_the_quote_is_not_passed(store):
    # The judge would "support" a sentence with itself; the copy check must stop it first.
    claim = precedent("MOCK-0001", REAL_QUOTE, text=REAL_QUOTE)
    out = verify_precedent(claim, store, stub_judge("supports", REAL_QUOTE))
    assert out.status == Status.failed and "repeats" in out.reason


def test_extract_falls_back_to_super_after_bad_json_but_judge_does_not():
    from pydantic import BaseModel

    class Out(BaseModel):
        x: int

    llm = TokenFactoryLLM(client=_FakeClient(["{bad", "{still bad", '{"x": 1}']))
    out = llm.structured("extract", [{"role": "user", "content": "q"}], Out)
    assert out["value"].x == 1 and "->" in out["fallback"]
    judge_llm = TokenFactoryLLM(client=_FakeClient(["{bad", "{still bad", '{"x": 1}']))
    with pytest.raises(LLMError):
        judge_llm.structured("judge", [{"role": "user", "content": "q"}], Out)
