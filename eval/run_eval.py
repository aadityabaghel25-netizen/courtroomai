"""
Evaluation: every case with the verifier OFF and ON, on live Token Factory + Tavily.

Per case: intake -> statutes -> retrieve -> draft run ONCE; then
  OFF: drafted claims shown unchecked (baseline), rendered + linted in report mode
  ON : verify -> redraft (max 2) -> good-law -> render with lint
One FABRICATED precedent claim (labelled "injected_fake", case ID that does not
exist) is added to the drafted claims in every case before the branch.
Audit mode runs on each case's draft (one real corpus citation, one labelled fake).

Writes eval/results/eval_<ts>.json (git SHA, model IDs, counts, percentages with
Wilson 95% intervals) and eval/results/human_check_<ts>.csv (up to 20 passed
precedent claims with their source passages, for hand labelling).

Usage: python eval/run_eval.py [--split dev|test|all] [--limit N]
"""

import argparse
import copy
import csv
import json
import math
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import pipeline as P  # noqa: E402
from core.audit import run_audit  # noqa: E402
from core.claims import Claim, ClaimType, JudgmentPassage, Status  # noqa: E402
from core.config import settings  # noqa: E402
from core.lint import lint_text  # noqa: E402
from core.llm import usage_log  # noqa: E402

RESULTS = ROOT / "eval" / "results"


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def rate(k, n):
    return {"k": k, "n": n, "pct": round(100 * k / n, 1) if n else None, "wilson95": wilson(k, n)}


def context_precision(retrieved, relevant):
    """RAGAS-style context precision@k: mean of precision@i over ranks i that are relevant."""
    hits, s = 0, 0.0
    for i, cid in enumerate(retrieved, 1):
        if cid in relevant:
            hits += 1
            s += hits / i
    return s / hits if hits else 0.0


def apply(state, delta):
    state.update(delta)
    return state


def tokens_since(mark):
    recs = usage_log.records[mark:]
    return sum(r.prompt_tokens + r.completion_tokens for r in recs), sum(1 for r in recs if not r.ok)


def run_case(case):
    t0 = time.time()
    mark = len(usage_log.records)
    st = P.initial_state(case["fir"], "defense", True)
    apply(st, P.intake_node(st))
    if st.get("error"):
        return {"id": case["id"], "error": st["error"]}
    apply(st, P.statutes_node(st))
    apply(st, P.retrieve_node(st))
    retrieved = [p["case_id"] for p in st["passages"]]
    row = {"id": case["id"], "split": case["split"], "category": case["category"],
           "top_rerank": st["top_rerank"], "retrieved": retrieved,
           "context_precision": context_precision(retrieved, set(case["relevant_case_ids"])),
           "any_relevant_retrieved": any(r in case["relevant_case_ids"] for r in retrieved)}
    if st.get("abstained"):
        row["abstained"] = True
        return row
    apply(st, P.draft_node(st))
    fake = Claim(id="PX", type=ClaimType.precedent_holding,
                 text="Bail must be granted as of right in every case of this kind.",
                 evidence=[JudgmentPassage(case_id=f"FAKE-{case['id']}", quote="Bail must be granted as of right in every case of this kind.")])
    st["claims"] = st["claims"] + [fake.model_dump(mode="json")]

    # OFF branch
    off = copy.deepcopy(st)
    off["use_verifier"] = False
    apply(off, P.verify_node(off))
    apply(off, P.render_node(off))
    off_shown = [c for c in off["claims"] if c["status"] == "passed" and c["type"] in ("precedent_holding", "strategy_suggestion")]

    # ON branch
    on = copy.deepcopy(st)
    apply(on, P.verify_node(on))
    while P._after_verify(on) == "redraft":
        apply(on, P.redraft_node(on))
    apply(on, P.good_law_node(on))
    apply(on, P.render_node(on))
    latency = time.time() - t0
    on_by_id = {c["id"]: c for c in on["claims"]}

    # unsupported claims shown: OFF shows everything drafted; "unsupported" = its ON status is not passed
    off_unsupported = sum(1 for c in off_shown if on_by_id.get(c["id"], {}).get("status") != "passed")
    on_shown = [c for c in on["claims"] if c["status"] == "passed" and c["type"] in ("precedent_holding", "strategy_suggestion")]

    # narrative leakage: re-lint the FINAL rendered text against FIR + source evidence
    allowed = [case["fir"]]
    for c in on["claims"]:
        if c["status"] != "passed":
            continue
        if c["type"] in ("statute_mapping", "good_law_status"):
            allowed.append(c["text"])
        for e in c.get("evidence", []):
            allowed += [str(e.get(a) or "") for a in ("text", "quote", "title", "snippet", "new_section", "old_section")]
    final_text = " ".join(it["text"] for s in on["brief"]["sections"] for it in s["items"])
    leaks = lint_text(final_text, allowed).drops

    precedents = [c for c in on["claims"] if c["type"] == "precedent_holding" and c["id"] != "PX"]
    toks, failed_calls = tokens_since(mark)
    row.update({
        "abstained": False,
        "fake_injected_caught_on": on_by_id["PX"]["status"] != "passed",
        "fake_injected_shown_off": any(c["id"] == "PX" for c in off_shown),
        "off_shown": len(off_shown), "off_unsupported_shown": off_unsupported,
        "off_lint_drops": len(off["brief"]["lint_drops"]),
        "on_shown": len(on_shown), "on_unsupported_shown": sum(1 for c in on_shown if c["status"] != "passed"),
        "on_lint_drops": len(on["brief"]["lint_drops"]), "final_leaks": len(leaks),
        "leak_examples": [d.unknown for d in leaks[:3]],
        "precedents_drafted": len(precedents),
        "precedent_status": {s.value: sum(c["status"] == s.value for c in precedents) for s in Status},
        "good_law_with_results": sum(1 for c in on["claims"] if c["type"] == "good_law_status" and c["status"] == "passed"),
        "good_law_searched": sum(1 for c in on["claims"] if c["type"] == "good_law_status"),
        "latency_s": round(latency, 1), "tokens": toks, "failed_llm_calls": failed_calls,
        "passed_precedents": [{"claim_id": c["id"], "text": c["text"], "case_id": c["evidence"][0]["case_id"],
                               "title": c["evidence"][0].get("title"), "quote": c["evidence"][0].get("quote"),
                               "judge_quote": c["evidence"][0].get("judge_quote")}
                              for c in precedents if c["status"] == "passed"],
    })
    return row


def run_audit_case(case):
    out = run_audit(case["audit_draft"], P.store())
    real = next(c for c in case["audit_citations"] if not c["fake"])
    fake = next(c for c in case["audit_citations"] if c["fake"])
    vs = out.get("verdicts", [])

    def match(v, c):
        return c["case_name"].split(" vs ")[0].split(" v. ")[0].lower()[:12] in (v["case_name"] or "").lower()

    v_real = next((v for v in vs if match(v, real)), None)
    v_fake = next((v for v in vs if match(v, fake)), None)
    return {"id": case["id"],
            "real_extracted": v_real is not None,
            "real_resolved": bool(v_real and v_real.get("case_id") == real["case_id"]),
            "real_verdict": v_real and v_real["verdict"],
            "fake_extracted": v_fake is not None,
            "fake_verdict": v_fake and v_fake["verdict"],
            "fake_caught": v_fake is None or v_fake["verdict"] in ("not_found", "found_online_unverified", "unverified")}


def tune_threshold(rows):
    """On dev only: the rerank threshold that best separates cases with/without a relevant retrieval."""
    pts = [(r["top_rerank"], r["any_relevant_retrieved"]) for r in rows if r.get("top_rerank") is not None]
    if not pts:
        return None
    best = (-1, None)
    for t in sorted({p[0] for p in pts} | {min(p[0] for p in pts) - 1}):
        acc = sum((s >= t) == rel for s, rel in pts) / len(pts)
        if acc > best[0]:
            best = (acc, t)
    return {"threshold": best[1], "dev_accuracy": round(best[0], 3), "n": len(pts)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="all", choices=["dev", "test", "all"])
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    cases = [json.loads(l) for l in open(ROOT / "eval" / "cases.jsonl", encoding="utf-8")]
    cases = [c for c in cases if a.split == "all" or c["split"] == a.split]
    if a.limit:
        cases = cases[:a.limit]
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    started = datetime.now(timezone.utc)
    rows, audits = [], []
    for c in cases:
        print(f"[{c['id']}] brief...", flush=True)
        try:
            r = run_case(c)
        except Exception as e:  # record, never hide
            r = {"id": c["id"], "error": f"{type(e).__name__}: {e}"[:300]}
        rows.append(r)
        print(f"[{c['id']}] {json.dumps({k: r.get(k) for k in ('error', 'abstained', 'fake_injected_caught_on', 'precedent_status', 'final_leaks', 'latency_s', 'tokens')})}", flush=True)
        try:
            au = run_audit_case(c)
        except Exception as e:
            au = {"id": c["id"], "error": f"{type(e).__name__}: {e}"[:300]}
        audits.append(au)
        print(f"[{c['id']}] audit {json.dumps(au)}", flush=True)

    ok = [r for r in rows if not r.get("error") and not r.get("abstained")]
    au_ok = [x for x in audits if not x.get("error")]
    prec_total = sum(sum(r["precedent_status"].values()) for r in ok)
    metrics = {
        "fabricated_citation_catch_rate_brief_verifier_on": rate(sum(r["fake_injected_caught_on"] for r in ok), len(ok)),
        "fabricated_citation_shown_brief_verifier_off": rate(sum(r["fake_injected_shown_off"] for r in ok), len(ok)),
        "fabricated_citation_catch_rate_audit": rate(sum(x["fake_caught"] for x in au_ok), len(au_ok)),
        "audit_real_citation_resolved": rate(sum(x["real_resolved"] for x in au_ok), len(au_ok)),
        "audit_accuracy_per_citation": rate(sum(x["real_resolved"] for x in au_ok) + sum(x["fake_caught"] for x in au_ok), 2 * len(au_ok)),
        "unsupported_claims_shown_verifier_off": rate(sum(r["off_unsupported_shown"] for r in ok), sum(r["off_shown"] for r in ok)),
        "unsupported_claims_shown_verifier_on": rate(sum(r["on_unsupported_shown"] for r in ok), sum(r["on_shown"] for r in ok)),
        "narrative_leakage_final_output": {"sentences_with_unknown_entities": sum(r["final_leaks"] for r in ok), "cases": len(ok)},
        "lint_drops_verifier_off": sum(r["off_lint_drops"] for r in ok),
        "lint_drops_verifier_on": sum(r["on_lint_drops"] for r in ok),
        "precedent_claims_passed": rate(sum(r["precedent_status"]["passed"] for r in ok), prec_total),
        "precedent_claims_rejected_or_unverified": rate(prec_total - sum(r["precedent_status"]["passed"] for r in ok), prec_total),
        "false_rejection_rate": "needs hand labels (see human_check CSV)",
        "context_precision_at_k_topic_labels": round(statistics.mean(r["context_precision"] for r in rows if "context_precision" in r), 3) if rows else None,
        "good_law_cases_with_web_results": rate(sum(r["good_law_with_results"] for r in ok), sum(r["good_law_searched"] for r in ok)),
        "median_latency_s_per_brief": statistics.median(r["latency_s"] for r in ok) if ok else None,
        "median_tokens_per_brief": statistics.median(r["tokens"] for r in ok) if ok else None,
        "abstained_cases": sum(1 for r in rows if r.get("abstained")),
        "errored_cases": sum(1 for r in rows if r.get("error")) + sum(1 for x in audits if x.get("error")),
    }
    tuned = tune_threshold([r for r in rows if r.get("split") == "dev"])
    RESULTS.mkdir(parents=True, exist_ok=True)
    ts = started.strftime("%Y%m%dT%H%M%SZ")
    result = {"timestamp": started.isoformat(), "git_sha": sha, "split": a.split, "n_cases": len(cases),
              "models": {"nano": settings.nano_model, "super": settings.super_model, "ultra": settings.ultra_model},
              "abstain_threshold_used": settings.abstain_rerank_threshold, "abstain_threshold_tuned_on_dev": tuned,
              "metrics": metrics, "cases": rows, "audit": audits}
    (RESULTS / f"eval_{ts}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with open(RESULTS / f"human_check_{ts}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case", "claim_id", "case_id", "title", "claim_text", "quote", "judge_quote", "hand_label_supported(yes/no)", "notes"])
        n = 0
        for r in ok:
            for p in r["passed_precedents"]:
                if n < 20:
                    w.writerow([r["id"], p["claim_id"], p["case_id"], p["title"], p["text"], p["quote"], p["judge_quote"], "", ""])
                    n += 1
    print(json.dumps(metrics, indent=2))
    print(f"wrote eval/results/eval_{ts}.json and human_check_{ts}.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
