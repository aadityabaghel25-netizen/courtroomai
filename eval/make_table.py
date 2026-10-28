"""
Regenerate the README results table from the newest eval/results/eval_*.json,
between <!-- EVAL:START --> and <!-- EVAL:END -->. No number is typed by hand.

Usage: python eval/make_table.py [path/to/eval.json]
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START, END = "<!-- EVAL:START -->", "<!-- EVAL:END -->"
C_START, C_END = "<!-- CORPUS:START -->", "<!-- CORPUS:END -->"


def corpus_block():
    """Library and statute-table sizes, counted from the data files (not typed)."""
    import csv
    import sqlite3
    jl = ROOT / "data" / "judgments" / "judgments.jsonl"
    judgments = sum(1 for line in open(jl, encoding="utf-8") if line.strip()) if jl.exists() else 0
    with_cites = sum(1 for line in open(jl, encoding="utf-8") if '"citations": ["' in line) if jl.exists() else 0
    db = ROOT / "data" / "chroma_db" / "chroma.sqlite3"
    chunks = sqlite3.connect(f"file:{db}?mode=ro", uri=True).execute("select count(*) from embeddings").fetchone()[0] if db.exists() else 0
    mp = ROOT / "data" / "statutes" / "ipc_bns_map.csv"
    rows = list(csv.DictReader(open(mp, encoding="utf-8"))) if mp.exists() else []
    by = lambda a: sum(1 for r in rows if r["old_act"] == a)
    agree = sum(1 for r in rows if r.get("ik_agrees") == "yes")
    differ = sum(1 for r in rows if r.get("ik_agrees") == "no")
    return "\n".join([C_START,
        f"- Judgment library: **{judgments} judgments** ({with_cites} with reporter citations), split into **{chunks} searchable passages**.",
        f"- Statute tables: **{by('IPC')} IPC→BNS** rows from the official CAPT Bhopal correspondence table "
        f"(cross-checked with Indian Kanoon: {agree} agree, {differ} differ and are shown as only partly supported), "
        f"**{by('CrPC')} CrPC→BNSS** and **{by('IEA')} Evidence Act→BSA** rows from Indian Kanoon's per-section notes.",
        "_Counted from `data/` by `eval/make_table.py`._", C_END])


def fmt(m):
    if isinstance(m, dict) and "k" in m:
        if not m["n"]:
            return "n/a (0 cases)"
        ci = m["wilson95"]
        return f"{m['k']}/{m['n']} = {m['pct']}% (95% CI {round(100 * ci[0], 1)}–{round(100 * ci[1], 1)}%)"
    if isinstance(m, dict):
        return ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in m.items())
    return str(m)


LABELS = [
    ("fabricated_citation_catch_rate_brief_verifier_on", "Injected fabricated precedent caught (brief, verifier on)"),
    ("fabricated_citation_shown_brief_verifier_off", "Injected fabricated precedent shown (brief, verifier off)"),
    ("fabricated_citation_catch_rate_audit", "Fabricated citation caught (audit mode)"),
    ("audit_real_citation_resolved", "Real citation resolved to the right judgment (audit mode)"),
    ("audit_accuracy_per_citation", "Audit-mode accuracy per citation (real resolved + fake caught)"),
    ("unsupported_claims_shown_verifier_off", "Unsupported precedent/strategy claims shown, verifier off"),
    ("unsupported_claims_shown_verifier_on", "Unsupported precedent/strategy claims shown, verifier on"),
    ("narrative_leakage_final_output", "Narrative leakage in final output (goal: 0)"),
    ("precedent_claims_passed", "Drafted precedent claims that passed all checks"),
    ("precedent_claims_rejected_or_unverified", "Drafted precedent claims rejected or unverified"),
    ("false_rejection_rate", "False rejection rate"),
    ("context_precision_at_k_topic_labels", "Context precision@k (formula as RAGAS; topic labels, not hand labels)"),
    ("good_law_cases_with_web_results", "Precedents with later-treatment web results"),
    ("median_latency_s_per_brief", "Median latency per brief (s, verifier on)"),
    ("median_tokens_per_brief", "Median Token Factory tokens per brief"),
    ("abstained_cases", "Cases that abstained"),
    ("errored_cases", "Errored runs"),
]


def main():
    files = sorted((ROOT / "eval" / "results").glob("eval_*.json"))
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else (files[-1] if files else None)
    if path is None:
        print("FAIL: no eval results found")
        return 1
    r = json.loads(path.read_text(encoding="utf-8"))
    m = r["metrics"]
    lines = [START,
             f"Source: `eval/results/{path.name}` · git `{r['git_sha']}` · split `{r['split']}` · {r['n_cases']} cases · "
             f"Nano `{r['models']['nano']}`, Super `{r['models']['super']}`, Ultra `{r['models']['ultra']}`",
             "", "| Metric | Result |", "|---|---|"]
    lines += [f"| {label} | {fmt(m.get(key))} |" for key, label in LABELS if key in m]
    t = r.get("abstain_threshold_tuned_on_dev")
    lines += ["", f"Abstention threshold used: `{r['abstain_threshold_used']}`; tuned on dev: `{t}`.", END]
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    if START not in text or END not in text:
        print("FAIL: README markers missing")
        return 1
    new = text[:text.index(START)] + "\n".join(lines) + text[text.index(END) + len(END):]
    if C_START in new and C_END in new:
        new = new[:new.index(C_START)] + corpus_block() + new[new.index(C_END) + len(C_END):]
    readme.write_text(new, encoding="utf-8")
    print(f"OK: README table regenerated from {path.name} (and corpus counts from data/)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
