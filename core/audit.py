"""
Audit mode: verdict per citation in a pasted draft.

1. Nano extracts every citation and the proposition it is cited for.
2. Each citation is resolved against the corpus (reporter citation, then case name).
3. In corpus: the same Ultra judge with quote-back checks the proposition.
4. Not in corpus: Tavily search. Reported as "found online, not verified against
   the judgment text", or "not found".
"""

import re
from typing import Callable, List, Optional, Sequence

from pydantic import BaseModel, Field

from core.claims import Claim, ClaimType, JudgmentPassage, Status, WebResult
from core.config import settings
from core.judgments import Judgment, JudgmentStore
from core.normalize import contains_verbatim
from core.verifiers import JudgeFn, _judge_prompt, judge_with_quote_retry

EXTRACT_PROMPT_VERSION = "extract_citations_v1"


class ExtractedCitation(BaseModel):
    case_name: str = ""
    citation: str = ""
    proposition: str = Field(default="", max_length=1500)


class ExtractedCitations(BaseModel):
    citations: List[ExtractedCitation]


class AuditVerdict(BaseModel):
    index: int
    case_name: str
    citation: str
    proposition: str
    verdict: str          # verified | weak | contradicted | not_supported | found_online_unverified | not_found | unverified
    label: str            # text shown to the advocate
    reason: str
    case_id: Optional[str] = None
    claim: Optional[Claim] = None
    fetched_from: Optional[str] = None  # host the judgment text was fetched from, if not in our library


def extract_prompt(draft: str) -> str:
    tpl = (settings.prompts_dir / f"{EXTRACT_PROMPT_VERSION}.txt").read_text(encoding="utf-8")
    return tpl.replace("{draft}", draft)


_WORD = re.compile(r"[a-z]{3,}")


def best_windows(j: Judgment, proposition: str, size: int, k: int = 2) -> str:
    """Pick the k text windows sharing the most words with the proposition (no model involved)."""
    if len(j.text) <= settings.judge_full_text_chars:
        return j.text
    words = set(_WORD.findall(proposition.lower()))
    step = size // 2
    scored = []
    for start in range(0, len(j.text), step):
        chunk = j.text[start:start + size]
        scored.append((len(words & set(_WORD.findall(chunk.lower()))), start))
    top = sorted(sorted(scored, reverse=True)[:k], key=lambda x: x[1])
    return "\n...\n".join(j.text[s:s + size] for _, s in top)


_STOP = {"the", "of", "and", "state", "union", "india", "ors", "anr", "others", "another", "v", "vs", "versus", "mr", "smt", "shri", "etc", "page", "no"}


def _party_words(name: str):
    sides = re.split(r"\s+(?:v\.?|vs\.?|versus)\s+", name.strip(), maxsplit=1, flags=re.IGNORECASE)
    return [[w for w in re.findall(r"[a-z]+", side.lower()) if w not in _STOP and len(w) > 2] for side in sides]


def mentions_case(result: dict, c: "ExtractedCitation") -> bool:
    """A web hit counts only if it names the case: every distinctive party word, or the exact citation."""
    hay = " ".join([result.get("title", ""), result.get("content", ""), result.get("url", "")]).lower()
    if c.citation and re.sub(r"\s+", " ", c.citation.lower()) in re.sub(r"\s+", " ", hay):
        return True
    sides = [s for s in _party_words(c.case_name) if s] if c.case_name else []
    return bool(sides) and all(all(w in hay for w in side) for side in sides)


def resolve(store: JudgmentStore, c: ExtractedCitation) -> Optional[Judgment]:
    if c.citation:
        j = store.find_by_citation(c.citation)
        if j:
            return j
    if c.case_name:
        return store.find_by_title(c.case_name)
    return None


def _judge_text(i: int, c: ExtractedCitation, base: dict, j: Judgment, judge: JudgeFn, fetched_from: Optional[str] = None) -> AuditVerdict:
    """Same checks for a library judgment or a fetched one: judge with quote-back, quote verbatim in the text."""
    where = f" (judgment text fetched from {fetched_from})" if fetched_from else ""
    ev = JudgmentPassage(case_id=j.case_id, quote="", title=j.title, court=j.court, date=j.date, source_url=j.source_url)
    if not c.proposition.strip():
        return AuditVerdict(**base, case_id=j.case_id, verdict="unverified", label="Case exists; proposition unclear",
                            reason="the judgment was found, but the draft does not say what it is cited for" + where)
    window = best_windows(j, c.proposition, settings.judge_window_chars)
    prompt = _judge_prompt().format(proposition=c.proposition, title=j.title, judgment_text=window)
    try:
        out = judge_with_quote_retry(judge, prompt, j.text)
        v = out["value"]
    except Exception as e:
        return AuditVerdict(**base, case_id=j.case_id, verdict="unverified", label="Case exists; check incomplete",
                            reason=f"judge did not return a valid verdict ({type(e).__name__})" + where)
    ev = ev.model_copy(update={"quote": v.quote, "judge_verdict": v.verdict, "judge_quote": v.quote, "judge_model": out.get("model")})
    claim = Claim(id=f"A{i}", type=ClaimType.precedent_holding, text=c.proposition, evidence=[ev])
    if not v.quote or not contains_verbatim(j.text, v.quote):
        claim = claim.model_copy(update={"status": Status.unverified, "reason": "judge's quote is not in the judgment text"})
        return AuditVerdict(**base, case_id=j.case_id, verdict="unverified", label="Case exists; check incomplete",
                            reason=claim.reason + where, claim=claim)
    mapping = {
        "supports": ("verified", "Verified against source text", Status.passed),
        "partial": ("weak", "Partly supported", Status.weak),
        "contradicts": ("contradicted", "Judgment says the opposite", Status.failed),
        "not_addressed": ("not_supported", "Judgment does not support this", Status.failed),
    }
    verdict, label, status = mapping[v.verdict]
    reason = (v.reason or verdict) + where
    claim = claim.model_copy(update={"status": status, "reason": reason})
    return AuditVerdict(**base, case_id=j.case_id, verdict=verdict, label=label, reason=reason, claim=claim,
                        fetched_from=fetched_from)


def audit_one(i: int, c: ExtractedCitation, store: JudgmentStore, judge: JudgeFn,
              web_search: Callable[[str], Optional[Sequence[dict]]],
              extractor: Optional[Callable[[str], Optional[str]]] = None) -> AuditVerdict:
    """
    In the library: judge against the stored text. Otherwise search the web; if a trusted
    full-judgment page is found and `extractor` is given, fetch it and run the same checks.
    """
    base = dict(index=i, case_name=c.case_name, citation=c.citation, proposition=c.proposition)
    j = resolve(store, c)
    if j is not None:
        return _judge_text(i, c, base, j, judge)

    query = " ".join(x for x in (c.case_name, c.citation) if x).strip()
    try:
        results = web_search(query) if query else None
    except Exception:
        return AuditVerdict(**base, verdict="unverified", label="Could not check",
                            reason="not in our judgment library, and the web search did not respond")
    results = [r for r in (results or []) if r.get("url")]

    sides = [s for s in _party_words(c.case_name) if s] if c.case_name else []
    if extractor and sides:
        from core.webfetch import fetch_judgment
        try:
            got = fetch_judgment(results, sides, extractor)
        except Exception:
            got = None
        if got:
            web_j = Judgment(case_id=f"web:{got['host']}", title=got["title"] or c.case_name, court=got.get("court", ""), date="",
                             source_url=got["url"], text=got["text"])
            return _judge_text(i, c, base, web_j, judge, fetched_from=got["host"])

    hits = [r for r in results if mentions_case(r, c)]
    if hits:
        ev = [WebResult(url=r["url"], title=r.get("title", ""), snippet=(r.get("content") or "")[:300]) for r in hits[:3]]
        claim = Claim(id=f"A{i}", type=ClaimType.precedent_holding, text=c.proposition, evidence=ev,
                      status=Status.unverified, reason="found online, not verified against the judgment text")
        return AuditVerdict(**base, verdict="found_online_unverified",
                            label="Found online, not verified against the judgment text",
                            reason="not in our judgment library; a web page names it, but we could not read the full judgment", claim=claim)
    return AuditVerdict(**base, verdict="not_found", label="Not found",
                        reason="not in our judgment library and not found on the web; treat it as possibly fabricated")


def run_audit(draft: str, store: JudgmentStore, on_event: Optional[Callable[[dict], None]] = None) -> dict:
    """Extract citations with Nano, then verify each in parallel. Never raises for a bad citation."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    from core import tavily
    from core.llm import LLMError, get_llm

    emit = on_event or (lambda e: None)
    llm = get_llm()
    t0 = time.time()
    try:
        out = llm.structured("extract", [{"role": "user", "content": extract_prompt(draft)}], ExtractedCitations, max_tokens=6000)
    except LLMError as e:
        emit({"step": "extract", "status": "error", "detail": str(e)[:200], "model": llm.models["extract"]})
        return {"error": "could not extract citations", "verdicts": []}
    # Keep only citations whose name or reporter citation really appears in the draft.
    draft_n = " ".join(draft.split())
    cites = [c for c in out["value"].citations
             if (c.case_name and " ".join(c.case_name.split()) in draft_n) or (c.citation and " ".join(c.citation.split()) in draft_n)]
    emit({"step": "extract", "status": "ok", "detail": f"Found {len(cites)} citation(s)", "model": out["model"],
          "elapsed_s": round(time.time() - t0, 2)})

    def judge(prompt):
        from core.claims import JudgeVerdict
        return llm.structured("judge", [{"role": "user", "content": prompt}], JudgeVerdict, max_tokens=6000)

    # Full-text fetches are capped per request (cost and latency).
    import threading
    from core import webfetch
    budget = {"left": settings.max_web_fetches}
    lock = threading.Lock()

    def capped_extract(url):
        with lock:
            if budget["left"] <= 0:
                return None
            budget["left"] -= 1
        return webfetch.extract(url)

    t1 = time.time()
    with ThreadPoolExecutor(max_workers=settings.verify_concurrency) as ex:
        verdicts = list(ex.map(lambda ic: audit_one(ic[0], ic[1], store, judge, lambda q: tavily.search(q, max_results=5),
                                                    extractor=capped_extract),
                               enumerate(cites)))
    emit({"step": "verify", "status": "ok", "detail": f"Checked {len(verdicts)} citation(s)", "model": llm.models["judge"],
          "elapsed_s": round(time.time() - t1, 2)})
    return {"verdicts": [v.model_dump(mode="json") for v in verdicts],
            "notice": "Not legal advice. Check every source before relying on it."}
