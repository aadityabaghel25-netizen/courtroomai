"""
Per-type claim verifiers. Each returns a new Claim with status and reason set.
Any exception, timeout, parse error or missing source ends in "unverified" or
"failed", never "passed".
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional, Sequence

from core.claims import (Claim, ClaimType, DraftClaim, FirSpan, JudgeVerdict,
                         JudgmentPassage, Status, WebResult)
from core.config import settings
from core.judgments import JudgmentStore
from core.lint import extract_entities, lint_text
from core.normalize import contains_verbatim, find_span, normalize

logger = logging.getLogger(__name__)

JUDGE_PROMPT_VERSION = "judge_precedent_v3"


def _judge_prompt() -> str:
    return (settings.prompts_dir / f"{JUDGE_PROMPT_VERSION}.txt").read_text(encoding="utf-8")


def _with(claim: Claim, status: Status, reason: str, **upd) -> Claim:
    return claim.model_copy(update={"status": status, "reason": reason, **upd})


# --- fact -----------------------------------------------------------------

def verify_fact(claim: Claim, fir_text: str) -> Claim:
    """The claim's quote (or text) must be a verbatim substring of the FIR after normalisation."""
    quote = next((e.text for e in claim.evidence if isinstance(e, FirSpan)), None) or claim.text
    fir_n = normalize(fir_text)
    span = find_span(fir_n, quote)
    if span is None:
        return _with(claim, Status.failed, "not found in the FIR")
    ev = FirSpan(start=span[0], end=span[1], text=fir_n[span[0]:span[1]])
    return _with(claim, Status.passed, "verbatim in the FIR", evidence=[ev])


# --- precedent_holding ----------------------------------------------------

JudgeFn = Callable[[str], dict]
"""Takes the full judge prompt, returns {"value": JudgeVerdict, "model": str, "fallback": str|None}.
Raises on any failure."""


def is_near_copy(point: str, quote: str, threshold: float = 0.95) -> bool:
    """True when the point is essentially the quote itself (or a slice of it).
    Copies measured 1.0 in a real run; a fair paraphrase of a principle measured 0.83."""
    from difflib import SequenceMatcher
    a, b = normalize(point).lower().rstrip(". "), normalize(quote).lower().rstrip(". ")
    if not a or not b:
        return False
    if a in b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= threshold


def judge_with_quote_retry(judge: JudgeFn, prompt: str, source_text: str) -> dict:
    """
    Call the judge; if its quote is not verbatim in the source, ask once more and
    say why. The verbatim rule is unchanged: the caller still checks the final quote.
    """
    out = judge(prompt)
    q = out["value"].quote
    if q and contains_verbatim(source_text, q):
        return out
    retry = (prompt + "\n\nYour previous quote was not found verbatim in the TEXT"
             + (f": {q[:300]!r}" if q else " (it was empty)")
             + ". Copy ONE contiguous passage exactly as it appears, without joining sentences from different places.")
    out2 = judge(retry)
    out2["retried_quote"] = True
    return out2


def verify_precedent(claim: Claim, store: JudgmentStore, judge: JudgeFn) -> Claim:
    ev = next((e for e in claim.evidence if isinstance(e, JudgmentPassage)), None)
    if ev is None or not ev.case_id:
        return _with(claim, Status.failed, "no case ID given")
    # (a) case ID exists
    j = store.get(ev.case_id)
    if j is None:
        return _with(claim, Status.failed, f"case ID {ev.case_id} is not in the corpus")
    ev = ev.model_copy(update={"title": j.title, "court": j.court, "date": j.date, "source_url": j.source_url})
    # (b) quoted passage verbatim in the stored judgment
    if not ev.quote or not contains_verbatim(j.text, ev.quote):
        return _with(claim, Status.failed, "quoted passage not found verbatim in the judgment", evidence=[ev])
    # (b2) the point must be a principle, not a copy of the passage (a sentence always "supports" itself)
    if is_near_copy(claim.text, ev.quote):
        return _with(claim, Status.failed, "the point only repeats the quoted passage; it must state the legal principle", evidence=[ev])
    # (c) Ultra judge with quote-back
    window = store.window(ev.case_id, ev.quote, settings.judge_full_text_chars, settings.judge_window_chars)
    if window is None:
        return _with(claim, Status.unverified, "could not load judgment text for the judge", evidence=[ev])
    prompt = _judge_prompt().format(proposition=claim.text, title=j.title, judgment_text=window)
    try:
        out = judge_with_quote_retry(judge, prompt, j.text)
        verdict: JudgeVerdict = out["value"]
        model = out.get("model")
        fallback = out.get("fallback")
    except Exception as e:  # timeout, HTTP error, malformed JSON after repair
        logger.warning("judge failed for %s: %s", claim.id, e)
        return _with(claim, Status.unverified, f"judge did not return a valid verdict ({type(e).__name__})", evidence=[ev])

    ev = ev.model_copy(update={"judge_verdict": verdict.verdict, "judge_quote": verdict.quote, "judge_model": model})
    note = f" (judge fell back: {fallback})" if fallback else ""
    if not verdict.quote or not contains_verbatim(j.text, verdict.quote):
        return _with(claim, Status.unverified, "judge's supporting quote is not in the judgment text" + note, evidence=[ev])
    if verdict.verdict == "supports":
        return _with(claim, Status.passed, "verified against source text: judge found support and its quote matches the judgment" + note, evidence=[ev])
    if verdict.verdict == "partial":
        return _with(claim, Status.weak, "judge found only partial support" + note, evidence=[ev])
    return _with(claim, Status.failed, f"judge verdict: {verdict.verdict}" + note, evidence=[ev])


# --- good_law_status ------------------------------------------------------

def good_law_claim(claim_id: str, case_title: str, results: Optional[Sequence[dict]]) -> Claim:
    """
    Built only from Tavily results. Never asserts "good law"; at most reports
    that later material mentioning the case was found, with links.
    """
    if not results:
        return Claim(id=claim_id, type=ClaimType.good_law_status,
                     text=f"No later treatment found in the sources searched for {case_title}.",
                     status=Status.unverified, reason="no later treatment found in the sources searched")
    ev = [WebResult(url=r.get("url", ""), title=r.get("title", ""), snippet=(r.get("content") or "")[:400])
          for r in results if r.get("url")]
    if not ev:
        return good_law_claim(claim_id, case_title, None)
    return Claim(id=claim_id, type=ClaimType.good_law_status,
                 text=f"Web search found {len(ev)} source(s) discussing {case_title}; read them for later treatment. This is not a confirmation that the case is good law.",
                 evidence=ev, status=Status.passed, reason="built from search results only")


# --- strategy_suggestion --------------------------------------------------

def verify_strategy(claim: Claim, passed_claims: Sequence[Claim], fir_text: str) -> Claim:
    passed_ids = {c.id for c in passed_claims if c.status == Status.passed}
    refs = list(claim.refs)
    if not refs:
        return _with(claim, Status.failed, "dropped: does not reference any passed claim")
    bad = [r for r in refs if r not in passed_ids]
    if bad:
        # Every reference must have passed; otherwise the suggestion could carry a failed claim's content.
        return _with(claim, Status.failed, f"dropped: relies on claims that did not pass ({', '.join(bad)})")
    allowed = [fir_text] + [c.text for c in passed_claims if c.status == Status.passed] + [
        getattr(e, "title", "") or "" for c in passed_claims if c.status == Status.passed for e in c.evidence]
    res = lint_text(claim.text, allowed)
    if res.drops:
        unknown = sorted({u for d in res.drops for u in d.unknown})
        return _with(claim, Status.failed, f"dropped: introduces names or figures not in passed claims: {', '.join(unknown)[:200]}")
    text = claim.text if claim.text.lower().startswith("suggestion:") else f"Suggestion: {claim.text}"
    return _with(claim, Status.passed, "references passed claims and adds no new names or figures", refs=refs, text=text)


# --- drafts -> claims -----------------------------------------------------

def claim_from_draft(i: int, d: DraftClaim) -> Claim:
    ctype = ClaimType(d.type)
    ev = []
    if ctype == ClaimType.fact and d.quote:
        ev = [FirSpan(start=-1, end=-1, text=d.quote)]
    elif ctype == ClaimType.precedent_holding:
        ev = [JudgmentPassage(case_id=str(d.case_id or ""), quote=d.quote or "")]
    prefix = {"fact": "F", "precedent_holding": "P", "strategy_suggestion": "S"}[d.type]
    return Claim(id=f"{prefix}{i}", type=ctype, text=d.text, evidence=ev, refs=d.refs)


def verify_many(claims: List[Claim], fn: Callable[[Claim], Claim], concurrency: Optional[int] = None) -> List[Claim]:
    """Parallel verification with a concurrency cap. A crash in fn makes that claim unverified."""
    def safe(c: Claim) -> Claim:
        try:
            return fn(c)
        except Exception as e:
            logger.exception("verifier crashed on %s", c.id)
            return _with(c, Status.unverified, f"verifier error ({type(e).__name__})")
    with ThreadPoolExecutor(max_workers=concurrency or settings.verify_concurrency) as ex:
        return list(ex.map(safe, claims))
