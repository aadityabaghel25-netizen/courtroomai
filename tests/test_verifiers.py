"""Unit tests for normalisation, per-type verifiers, statute lookup and the corpus store."""

import pytest

from tests.helpers import FIR_TEXT, stub_judge
from core.claims import Claim, ClaimType, FirSpan, Status
from core.judgments import JudgmentStore
from core.normalize import contains_verbatim, html_to_text, normalize
from core.statutes import StatuteMap, statute_claim
from core.verifiers import good_law_claim, verify_fact, verify_many, verify_strategy


def test_normalize_whitespace_and_unicode_only():
    assert normalize("a  b\n\tc") == "a b c"
    assert normalize("ﬁle") == "file"           # NFKC ligature
    assert normalize("Bail") != normalize("bail")  # no case folding


def test_html_to_text_decodes_entities_and_never_fuses_words():
    assert normalize(html_to_text("<p>State&nbsp;of&amp;M.P.</p><p>Next</p>")) == "State of&M.P. Next"


def test_fact_verbatim_passes_and_records_span():
    c = Claim(id="F1", type=ClaimType.fact, text="snatched", evidence=[FirSpan(start=-1, end=-1, text="the accused snatched his mobile   phone")])
    out = verify_fact(c, FIR_TEXT)
    assert out.status == Status.passed
    span = out.evidence[0]
    assert normalize(FIR_TEXT)[span.start:span.end] == "the accused snatched his mobile phone"


def test_fact_paraphrase_fails():
    c = Claim(id="F2", type=ClaimType.fact, text="The accused stole a phone at the railway station.")
    out = verify_fact(c, FIR_TEXT)
    assert out.status == Status.failed and out.reason == "not found in the FIR"


def test_statute_without_mapping_file_is_unverified():
    out = statute_claim("M1", "IPC", "379", None, StatuteMap([]))
    assert out.status == Status.unverified and "no mapping found" in out.reason


def test_statute_lookup_uses_offence_date(tmp_path):
    # MOCK mapping row for the test only; real mappings come from the owner's file.
    smap = StatuteMap([{"old_act": "IPC", "old_section": "999", "new_act": "BNS", "new_section": "MOCK-1",
                        "title": "mock", "source": "test fixture"}])
    from datetime import date
    before = statute_claim("M1", "I.P.C.", "999", date(2023, 3, 14), smap)
    after = statute_claim("M2", "IPC", "999", date(2024, 8, 1), smap)
    assert before.status == after.status == Status.passed
    assert "IPC applies" in before.text and "BNS applies" in after.text


def test_good_law_never_asserts_good_law():
    none = good_law_claim("G1", "X v Y", [])
    assert none.status == Status.unverified and "no later treatment found" in none.reason
    some = good_law_claim("G2", "X v Y", [{"url": "https://a", "title": "t", "content": "c"}])
    assert "not a confirmation" in some.text
    assert "is good law" not in some.text.replace("not a confirmation that the case is good law", "")


def test_strategy_needs_passed_ref_and_no_new_figures():
    fact = Claim(id="F1", type=ClaimType.fact, text="the accused snatched his mobile phone", status=Status.passed)
    ok = verify_strategy(Claim(id="S1", type=ClaimType.strategy_suggestion,
                               text="Test whether the accused snatched his mobile phone as alleged.", refs=["F1"]), [fact], FIR_TEXT)
    assert ok.status == Status.passed and ok.text.startswith("Suggestion:")
    no_ref = verify_strategy(Claim(id="S2", type=ClaimType.strategy_suggestion, text="Seek bail.", refs=["F9"]), [fact], FIR_TEXT)
    assert no_ref.status == Status.failed
    failed_prec = Claim(id="P1", type=ClaimType.precedent_holding, text="x", status=Status.failed)
    mixed = verify_strategy(Claim(id="S4", type=ClaimType.strategy_suggestion,
                                  text="Rely on the precedent and the snatching.", refs=["F1", "P1"]), [fact, failed_prec], FIR_TEXT)
    assert mixed.status == Status.failed and "P1" in mixed.reason
    new_fig = verify_strategy(Claim(id="S3", type=ClaimType.strategy_suggestion,
                                    text="Courts grant bail in 90 percent of such cases.", refs=["F1"]), [fact], FIR_TEXT)
    assert new_fig.status == Status.failed


def test_verify_many_turns_crash_into_unverified():
    c = Claim(id="X", type=ClaimType.fact, text="t")
    def boom(_):
        raise RuntimeError("x")
    assert verify_many([c], boom)[0].status == Status.unverified


@pytest.mark.corpus
def test_real_corpus_quote_check():
    s = JudgmentStore.load()
    assert len(s) >= 100  # corpus grows when ingestion is re-run
    j = s.get("101107975")
    assert j is not None and j.court == "Supreme Court of India"
    q = "Corroborative evidence is not an imperative component of judicial credence in every case of rape."
    assert contains_verbatim(j.text, q)
    assert not contains_verbatim(j.text, q.replace("not an imperative", "an imperative"))
    assert s.find_by_citation("(2013) 15 SCC 240").case_id == "101107975"


def test_web_hit_must_name_the_case():
    from core.audit import ExtractedCitation, mentions_case
    c = ExtractedCitation(case_name="Imaginary Kumar v. State of Nowhere", citation="(2031) 4 SCC 777")
    unrelated = {"title": "Manoj Kumar v. State of Uttar Pradesh", "content": "bail", "url": "https://x"}
    named = {"title": "Imaginary Kumar vs State Of Nowhere", "content": "", "url": "https://y"}
    by_cite = {"title": "", "content": "reported as (2031) 4 SCC 777", "url": "https://z"}
    assert not mentions_case(unrelated, c)
    assert mentions_case(named, c) and mentions_case(by_cite, c)


def test_statute_sources_disagree_is_weak():
    # MOCK mapping row: the second source disagrees, so the mapping must not pass.
    smap = StatuteMap([{"old_act": "IPC", "old_section": "998", "new_act": "BNS", "new_section": "MOCK-2",
                        "title": "mock", "source": "test fixture", "ik_agrees": "no"}])
    out = statute_claim("M1", "IPC", "998", None, smap)
    assert out.status == Status.weak and "differ" in out.reason


@pytest.mark.corpus
def test_real_statute_table_core_rows():
    smap = StatuteMap.load()
    assert smap.available
    assert smap.lookup("IPC", "302")[1]["new_section"] == "103(1)"
    assert smap.lookup("I.P.C.", "420")[1]["new_section"] == "318(4)"
    assert smap.lookup("CrPC", "438")[1]["new_section"] == "482"


def test_other_acts_keep_their_numbers():
    out = statute_claim("M1", "Negotiable Instruments Act", "138", None, StatuteMap([]))
    assert out.status == Status.passed and "unchanged" in out.text
