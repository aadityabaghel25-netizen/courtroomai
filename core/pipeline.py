"""
Brief-mode pipeline as a LangGraph graph:

  intake -> statutes -> retrieve -> draft -> verify -> good_law -> render
                           |                    ^   |
                           +--> render (abstain) +---+ re-draft failed precedents (max 2)

Every node appends trace events (step, model, status, detail) to state["trace"];
the API streams them as server-sent events.
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import date
from typing import Any, Callable, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field

from core.claims import Claim, ClaimType, DraftOutput, DraftPrecedent, FirSpan, JudgeVerdict, JudgmentPassage, Status
from core.config import settings
from core.judgments import JudgmentStore
from core.lint import lint_text
from core.llm import LLMError, get_llm
from core.normalize import normalize
from core.statutes import StatuteMap, statute_claim
from core.audit import ExtractedCitation, mentions_case
from core.verifiers import good_law_claim, verify_fact, verify_many, verify_precedent, verify_strategy

logger = logging.getLogger(__name__)


# --- intake schema ----------------------------------------------------------

class Party(BaseModel):
    role: str = ""
    name: str = ""
    quote: str = ""


class SectionRef(BaseModel):
    act: str
    section: str
    quote: str = ""


class Fact(BaseModel):
    text: str = ""
    quote: str


class Intake(BaseModel):
    # Bounded lists: Nano once looped to its token limit on an unbounded schema (eval case E06).
    parties: List[Party] = Field(default_factory=list, max_length=10)
    sections: List[SectionRef] = Field(default_factory=list, max_length=12)
    offence_date: str = ""
    offence_date_iso: str = ""
    facts: List[Fact] = Field(default_factory=list, max_length=8)


class SearchQuery(BaseModel):
    query: str = Field(default="", max_length=300)


class BriefState(TypedDict, total=False):
    case_summary: str
    fir_text: str
    perspective: str
    use_verifier: bool
    intake_data: Dict[str, Any]
    offence_date: Optional[str]
    claims: List[Dict[str, Any]]          # all claims, any status (Claim.model_dump)
    passages: List[Dict[str, Any]]
    top_rerank: Optional[float]
    abstained: bool
    redraft_round: int
    brief: Dict[str, Any]
    trace: List[Dict[str, Any]]
    error: Optional[str]


def _prompt(name: str, **kw) -> str:
    tpl = (settings.prompts_dir / f"{name}.txt").read_text(encoding="utf-8")
    for k, v in kw.items():
        tpl = tpl.replace("{" + k + "}", str(v))
    return tpl


def _ev(state: BriefState, step: str, status: str, detail: str = "", model: Optional[str] = None, t0: Optional[float] = None):
    ev = {"step": step, "status": status, "detail": detail, "model": model,
          "elapsed_s": round(time.time() - t0, 2) if t0 else None}
    return (state.get("trace") or []) + [ev]


def _claims(state) -> List[Claim]:
    return [Claim.model_validate(c) for c in state.get("claims", [])]


def _dump(claims: List[Claim]) -> List[Dict[str, Any]]:
    return [c.model_dump(mode="json") for c in claims]


# --- shared resources (loaded once) -----------------------------------------

_store: Optional[JudgmentStore] = None
_smap: Optional[StatuteMap] = None


def store() -> JudgmentStore:
    global _store
    if _store is None:
        _store = JudgmentStore.load()
    return _store


def smap() -> StatuteMap:
    global _smap
    if _smap is None:
        _smap = StatuteMap.load()
    return _smap


def make_judge() -> Callable[[str], dict]:
    llm = get_llm()

    def judge(prompt: str) -> dict:
        return llm.structured("judge", [{"role": "user", "content": prompt}], JudgeVerdict, max_tokens=6000)
    return judge


# --- nodes ------------------------------------------------------------------

def intake_node(state: BriefState) -> BriefState:
    t0 = time.time()
    llm = get_llm()
    try:
        out = llm.structured("extract", [{"role": "user", "content": _prompt("intake_v1", fir=state["fir_text"])}],
                             Intake, max_tokens=2500)
    except LLMError as e:
        return {"error": f"intake failed: {e}", "trace": _ev(state, "intake", "error", str(e)[:200], llm.models["extract"], t0)}
    intake: Intake = out["value"]
    facts = [Claim(id=f"F{i + 1}", type=ClaimType.fact, text=f.quote,
                   evidence=[FirSpan(start=-1, end=-1, text=f.quote)]) for i, f in enumerate(intake.facts)]
    facts = [verify_fact(c, state["fir_text"]) for c in facts]
    # Drop a fact whose quote is contained in another fact's quote (keeps the longer one).
    texts = [normalize(c.text) for c in facts]
    facts = [c for i, c in enumerate(facts)
             if not any(i != k and texts[i] in texts[k] and (len(texts[k]) > len(texts[i]) or k < i) for k in range(len(facts)))]
    n_ok = sum(c.status == Status.passed for c in facts)
    off = None
    try:
        if intake.offence_date_iso and normalize(intake.offence_date) and normalize(intake.offence_date) in normalize(state["fir_text"]):
            off = date.fromisoformat(intake.offence_date_iso).isoformat()
    except ValueError:
        off = None
    return {"intake_data": intake.model_dump(), "claims": _dump(facts), "offence_date": off,
            "trace": _ev(state, "intake", "ok", f"Found {n_ok} facts quoted word for word, {len(intake.sections)} section(s), offence date {off or 'not stated'}",
                         out["model"], t0)}


def statutes_node(state: BriefState) -> BriefState:
    t0 = time.time()
    intake = Intake.model_validate(state["intake_data"])
    fir_n = normalize(state["fir_text"])
    off = date.fromisoformat(state["offence_date"]) if state.get("offence_date") else None
    claims = _claims(state)
    seen = set()
    for s in intake.sections:
        key = (s.act.strip().upper(), s.section.strip().upper())
        # The section number itself must be in the FIR; Nano may not add sections.
        if key in seen or s.section.strip() not in fir_n:
            continue
        seen.add(key)
        claims.append(statute_claim(f"M{len(seen)}", s.act, s.section, off, smap()))
    n_ok = sum(c.status == Status.passed for c in claims if c.type == ClaimType.statute_mapping)
    note = "" if smap().available else " (official table not loaded yet)"
    return {"claims": _dump(claims), "trace": _ev(state, "statutes", "ok", f"{n_ok} of {len(seen)} section(s) matched to the new codes{note}", None, t0)}


_sections: Optional[Dict[tuple, str]] = None
# Headings that describe the code's machinery, not an offence; they add noise to the search.
_GENERIC = re.compile(r"general explanations|definitions|short title|acts done by several persons", re.I)


def section_heading(act: str, section: str) -> str:
    """Heading of a section from the downloaded Act texts (data/statutes/sections.jsonl), or ''."""
    global _sections
    if _sections is None:
        from core.statutes import canon_act, canon_section
        _sections = {}
        path = settings.statute_map_path.parent / "sections.jsonl"
        if path.exists():
            for line in open(path, encoding="utf-8"):
                r = json.loads(line)
                _sections[(canon_act(r["act"]), canon_section(r["section"]))] = r["heading"]
    from core.statutes import canon_act, canon_section
    base = re.match(r"\d+[A-Z]*", canon_section(section))
    return _sections.get((canon_act(act), base.group(0) if base else canon_section(section)), "")


_retriever = None
_reranker = None


def _retrieval_models():
    global _retriever, _reranker
    if _retriever is None:
        from rag.hybrid_retriever import LegalHybridRetriever
        from rag.reranker import LegalReranker
        _retriever = LegalHybridRetriever()
        _reranker = LegalReranker(top_n=6)
    return _retriever, _reranker


def retrieve_node(state: BriefState) -> BriefState:
    t0 = time.time()
    intake = Intake.model_validate(state["intake_data"])
    facts = [c.text for c in _claims(state) if c.type == ClaimType.fact and c.status == Status.passed]
    # Search for the LAW as well as the story: section headings from the statute table
    # (e.g. "Punishment for murder") pull up passages that state principles.
    titles, old_refs = [], []
    for sref in intake.sections:
        hit = smap().lookup(sref.act, sref.section)
        if hit:
            t = hit[1].get("title", "").split(";")[0]
            if not _GENERIC.search(t):
                titles.append(t)
        else:
            # New-code section (BNS/BNSS/BSA): most judgments cite the old numbers, so search both.
            rev = smap().reverse(sref.act, sref.section)[:3]
            for r in rev:
                titles.append(r.get("title", "").split(";")[0])
                old_refs.append(f"Section {r['old_section']} {r['old_act']}")
            if not rev:
                # A new offence with no old equivalent (e.g. BNS 304 Snatching): use its heading from the Act text.
                heading = section_heading(sref.act, sref.section)
                if heading and not _GENERIC.search(heading):
                    titles.append(heading)
    secs = " ".join([f"Section {s.section} {s.act}" for s in intake.sections] + old_refs)
    legal_query = (" ".join(t for t in titles if t) + " " + secs + " principle held law").strip()
    fact_query = (" ".join(facts)[:600] + " " + secs).strip() or state["fir_text"][:600]
    # Short search query written by Nano (only shapes retrieval; never shown as a claim).
    try:
        sq = get_llm().structured("extract", [{"role": "user", "content": _prompt("search_query_v1", fir=state["fir_text"][:6000])}],
                                  SearchQuery, max_tokens=300)["value"].query.strip()
        if sq:
            fact_query = f"{sq} {secs}".strip()
    except LLMError:
        pass
    case_summary = fact_query if fact_query != (" ".join(facts)[:600] + " " + secs).strip() else ""
    query = legal_query if titles else fact_query
    retriever, reranker = _retrieval_models()

    def _search():
        seen, docs = set(), []
        for q in dict.fromkeys([query, fact_query]):
            for d in retriever.retrieve(q):
                key = (d.metadata.get("doc_id"), d.metadata.get("chunk_index"))
                if key not in seen and not str(d.metadata.get("doc_id", "")).startswith("bare_act_"):
                    seen.add(key)
                    docs.append(d)
        # The cross-encoder is trained on short queries: score each passage against the
        # law query and the facts query separately and keep the better score.
        if not docs:
            return []
        queries = list(dict.fromkeys([query, fact_query]))
        best = [max(float(x) for x in col) for col in zip(*[reranker.model.predict([(q, d.page_content) for d in docs]) for q in queries])]
        ranked = sorted(zip(best, docs), key=lambda x: x[0], reverse=True)[:reranker.top_n]
        for sc, d in ranked:
            d.metadata["reranker_score"] = round(sc, 4)
        return [d for _, d in ranked]

    # A locked or slow index must not hang the request: time out and abstain (fail closed).
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        ranked = pool.submit(_search).result(timeout=settings.retrieval_timeout_s)
    except FutureTimeout:
        pool.shutdown(wait=False)
        return {"passages": [], "top_rerank": None, "abstained": True,
                "trace": _ev(state, "retrieve", "abstain", f"The judgment search took too long ({settings.retrieval_timeout_s:g}s), so no judgments were added", None, t0)}
    pool.shutdown(wait=False)
    passages = [{"case_id": str(d.metadata.get("doc_id")), "title": d.metadata.get("title", ""),
                 "passage": d.page_content[:2500], "rerank": d.metadata.get("reranker_score")} for d in ranked]
    top = passages[0]["rerank"] if passages else None
    abstain = top is None or top < settings.abstain_rerank_threshold
    detail = (f"Found {len(passages)} relevant passage(s)" if not abstain else "No close enough judgments found in the library")
    return {"passages": passages, "top_rerank": top, "abstained": abstain, "case_summary": case_summary,
            "trace": _ev(state, "retrieve", "abstain" if abstain else "ok", detail, "bge-base + BM25 + ms-marco reranker", t0)}


def _fmt_claims(claims: List[Claim], ctype: ClaimType) -> str:
    rows = [f"[{c.id}] {c.text}" for c in claims if c.type == ctype and c.status == Status.passed]
    return "\n".join(rows) or "(none)"


def _clean_refs(refs):
    """Super sometimes writes "[F2]" or "F2." for claim IDs; keep just the ID."""
    return [m.group(0) for r in refs for m in [re.search(r"[A-Z]\d+", r)] if m]


def draft_node(state: BriefState) -> BriefState:
    t0 = time.time()
    claims = _claims(state)
    passages = "\n\n".join(f"case_id: {p['case_id']}\ntitle: {p['title']}\npassage:\n{p['passage']}" for p in state["passages"])
    prompt = _prompt("draft_claims_v4", perspective=state.get("perspective", "defense"),
                     case_summary=state.get("case_summary") or "(see the facts)",
                     facts=_fmt_claims(claims, ClaimType.fact), statutes=_fmt_claims(claims, ClaimType.statute_mapping),
                     passages=passages)
    llm = get_llm()
    try:
        out = llm.structured("draft", [{"role": "user", "content": prompt}], DraftOutput, max_tokens=8000)
    except LLMError as e:
        return {"trace": _ev(state, "draft", "error", "Could not draft judgment points this time; the facts are still listed", llm.models["draft"], t0)}
    new = [Claim(id=f"P{i}", type=ClaimType.precedent_holding, text=d.text,
                 evidence=[JudgmentPassage(case_id=d.case_id, quote=d.quote)])
           for i, d in enumerate(out["value"].precedents, 1)]
    new += [Claim(id=f"S{i}", type=ClaimType.strategy_suggestion, text=d.text, refs=_clean_refs(d.refs))
            for i, d in enumerate(out["value"].strategies, 1)]
    p, s = len(out["value"].precedents), len(out["value"].strategies)
    return {"claims": _dump(claims + new), "redraft_round": 0,
            "trace": _ev(state, "draft", "ok", f"Drafted {p} judgment point(s) and {s} suggestion(s)", out["model"], t0)}


def verify_node(state: BriefState) -> BriefState:
    t0 = time.time()
    claims = _claims(state)
    if not state.get("use_verifier", True):
        # Evaluation baseline only: everything drafted is shown unchecked.
        out = [c.model_copy(update={"status": Status.passed, "reason": "verifier disabled (evaluation baseline)"})
               if c.status == Status.unverified and c.type != ClaimType.statute_mapping else c for c in claims]
        return {"claims": _dump(out), "trace": _ev(state, "verify", "skipped", "Checks switched off (evaluation baseline)", None, t0)}
    judge = make_judge()
    pending = [c for c in claims if c.type == ClaimType.precedent_holding and c.status == Status.unverified and c.attempts == 0]
    done = {c.id: c for c in verify_many(pending, lambda c: verify_precedent(c, store(), judge))}
    for c in done.values():
        c.attempts = 1
    claims = [done.get(c.id, c) for c in claims]
    passed_or_known = [c for c in claims if c.type != ClaimType.strategy_suggestion]
    claims = [verify_strategy(c, passed_or_known, state["fir_text"]) if c.type == ClaimType.strategy_suggestion and c.status == Status.unverified else c
              for c in claims]
    counts = {st.value: sum(c.status == st for c in claims if c.type == ClaimType.precedent_holding) for st in Status}
    return {"claims": _dump(claims),
            "trace": _ev(state, "verify", "ok", f"{counts['passed']} of {sum(counts.values())} judgment point(s) verified", get_llm().models["judge"], t0)}


def redraft_node(state: BriefState) -> BriefState:
    """Ask Super to fix each failed precedent claim once per round (max 2 rounds), then re-verify it."""
    t0 = time.time()
    rnd = state.get("redraft_round", 0) + 1
    claims = _claims(state)
    llm, judge = get_llm(), make_judge()
    by_case = {p["case_id"]: p for p in state["passages"]}
    fixed = []
    for c in claims:
        if c.type != ClaimType.precedent_holding or c.status != Status.failed or c.attempts > settings.precedent_max_redrafts:
            continue
        ev = c.evidence[0] if c.evidence else None
        p = by_case.get(getattr(ev, "case_id", ""))
        if p is None:
            continue
        prompt = (f"Your earlier claim failed a check: {c.reason}.\nClaim: {c.text}\n"
                  f"Rewrite it using only this passage (case_id {p['case_id']}). The quote must be 1-3 consecutive sentences "
                  f"copied character-for-character from the passage where the court states or applies a legal principle. "
                  f"The text must state that principle in your own plain words; never copy the quote and never retell the facts. "
                  f"If the passage states no legal principle, quote the sentence closest to one.\n"
                  f"PASSAGE:\n{p['passage']}")
        try:
            d = llm.structured("draft", [{"role": "user", "content": prompt}], DraftPrecedent, max_tokens=4000)["value"]
        except LLMError:
            continue
        nc = Claim(id=c.id, type=ClaimType.precedent_holding, text=d.text, attempts=c.attempts + 1,
                   evidence=[JudgmentPassage(case_id=p["case_id"], quote=d.quote)])
        nc = verify_precedent(nc, store(), judge)
        nc.attempts = c.attempts + 1
        fixed.append(nc)
    fx = {c.id: c for c in fixed}
    claims = [fx.get(c.id, c) for c in claims]
    # Suggestions dropped only because a precedent had not passed yet get a fresh check.
    if any(c.status == Status.passed for c in fixed):
        others = [c for c in claims if c.type != ClaimType.strategy_suggestion]
        claims = [verify_strategy(c.model_copy(update={"status": Status.unverified}), others, state["fir_text"])
                  if c.type == ClaimType.strategy_suggestion and c.status == Status.failed and c.reason.startswith("dropped: relies on")
                  else c for c in claims]
    return {"claims": _dump(claims), "redraft_round": rnd,
            "trace": _ev(state, "redraft", "ok", f"Round {rnd}: re-checked {len(fixed)}, {sum(c.status == Status.passed for c in fixed)} now pass", llm.models["draft"], t0)}


def good_law_node(state: BriefState) -> BriefState:
    t0 = time.time()
    from core import tavily
    claims = _claims(state)
    seen = {}
    for c in claims:
        if c.type == ClaimType.precedent_holding and c.status == Status.passed:
            ev = c.evidence[0]
            seen.setdefault(ev.case_id, ev.title or ev.case_id)
    new = []
    for i, (cid, title) in enumerate(seen.items(), 1):
        name = title.rsplit(" on ", 1)[0]
        try:
            results = tavily.search(f"\"{name}\" overruled OR distinguished OR followed", max_results=5)
            # Keep only results that actually name the case (same rule as audit mode).
            results = [r for r in results if mentions_case(r, ExtractedCitation(case_name=name))][:3]
        except Exception as e:
            results = None
            logger.warning("tavily failed: %s", e)
        g = good_law_claim(f"G{i}", name, results)
        g.refs = [cid]
        new.append(g)
    return {"claims": _dump(claims + new),
            "trace": _ev(state, "good_law", "ok", f"Searched for later cases on {len(seen)} judgment(s)", "tavily", t0)}


def render_node(state: BriefState) -> BriefState:
    """Deterministic templates over passed claims, then the output lint."""
    t0 = time.time()
    claims = _claims(state)
    passed = [c for c in claims if c.status == Status.passed]
    sections: List[Dict[str, Any]] = []

    def section(title, ctype, fmt):
        items = [{"claim_id": c.id, "text": fmt(c)} for c in passed if c.type == ctype]
        if items:
            sections.append({"title": title, "type": ctype.value, "items": items})

    section("Facts stated in the FIR", ClaimType.fact, lambda c: f"The FIR states: \"{c.text}\"")
    section("Statutes", ClaimType.statute_mapping, lambda c: c.text)
    section("Precedents", ClaimType.precedent_holding,
            lambda c: f"{c.evidence[0].title or c.evidence[0].case_id}: {c.text.rstrip('. ')}. The judgment says: \"{c.evidence[0].quote}\"")
    section("Later treatment (web search)", ClaimType.good_law_status, lambda c: c.text)
    section("Strategy suggestions", ClaimType.strategy_suggestion, lambda c: c.text)

    # Lint allow-list: FIR + source evidence only (not the model-written claim text).
    allowed = [state["fir_text"]]
    for c in passed:
        if c.type in (ClaimType.statute_mapping, ClaimType.good_law_status):
            allowed.append(c.text)
        for e in c.evidence:
            allowed += [getattr(e, a, "") or "" for a in ("text", "quote", "title", "snippet", "new_section", "old_section")]
    drops = []
    for sec in sections:
        kept = []
        for it in sec["items"]:
            res = lint_text(it["text"], allowed)
            if res.drops:
                drops += [{"claim_id": it["claim_id"], "sentence": d.sentence, "unknown": d.unknown} for d in res.drops]
            if res.text:
                kept.append({**it, "text": res.text})
        sec["items"] = kept
    sections = [s for s in sections if s["items"]]
    for d in drops:
        logger.info("lint dropped sentence from %s: %s", d["claim_id"], d["unknown"])

    flagged = [{"claim_id": c.id, "type": c.type.value, "text": c.text, "status": c.status.value, "reason": c.reason}
               for c in claims if c.status != Status.passed]
    brief = {"abstained": bool(state.get("abstained")), "sections": sections, "flagged": flagged, "lint_drops": drops,
             "notice": "Not legal advice. Check every source before relying on it."}
    if state.get("abstained"):
        brief["abstain_reason"] = "not enough precedent found"
    return {"brief": brief, "trace": _ev(state, "render", "ok",
                                          f"{sum(len(s['items']) for s in sections)} point(s) in the brief, {len(flagged)} left out, {len(drops)} sentence(s) removed in the final check", None, t0)}


# --- graph ------------------------------------------------------------------

def _after_intake(state):
    return "render" if state.get("error") else "statutes"


def _after_retrieve(state):
    return "render" if state.get("abstained") else "draft"


def _after_verify(state):
    if not state.get("use_verifier", True):
        return "good_law"
    retry = any(c["type"] == "precedent_holding" and c["status"] == "failed" and c.get("attempts", 0) <= settings.precedent_max_redrafts
                for c in state.get("claims", []))
    return "redraft" if retry and state.get("redraft_round", 0) < settings.precedent_max_redrafts else "good_law"


def build_graph():
    from langgraph.graph import END, START, StateGraph
    g = StateGraph(BriefState)
    for name, fn in [("intake", intake_node), ("statutes", statutes_node), ("retrieve", retrieve_node),
                     ("draft", draft_node), ("verify", verify_node), ("redraft", redraft_node),
                     ("good_law", good_law_node), ("render", render_node)]:
        g.add_node(name, fn)
    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", _after_intake, {"render": "render", "statutes": "statutes"})
    g.add_edge("statutes", "retrieve")
    g.add_conditional_edges("retrieve", _after_retrieve, {"render": "render", "draft": "draft"})
    g.add_edge("draft", "verify")
    g.add_conditional_edges("verify", _after_verify, {"redraft": "redraft", "good_law": "good_law"})
    g.add_conditional_edges("redraft", _after_verify, {"redraft": "redraft", "good_law": "good_law"})
    g.add_edge("good_law", "render")
    g.add_edge("render", END)
    return g.compile()


def initial_state(fir_text: str, perspective: str = "defense", use_verifier: bool = True) -> BriefState:
    return {"fir_text": fir_text, "perspective": perspective, "use_verifier": use_verifier,
            "claims": [], "trace": [], "redraft_round": 0, "abstained": False}
