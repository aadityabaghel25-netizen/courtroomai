"""
Download the six criminal-law Acts from the Indian Kanoon API (one call per Act)
and split them into sections.

  data/statutes/acts/<code>.json        raw API response (git-ignored)
  data/statutes/sections.jsonl          one line per section: act, section, heading, text, old_refs
  data/statutes/ik_crossref.csv         Indian Kanoon's editorial "[ Similar to Section X from Old CrPC/IPC ]"
                                        notes, as a SECOND source (not part of the Acts)

Act IDs: BNS/BNSS/BSA found by laws-filtered search; IPC/CrPC/Evidence Act read from
the links in our corpus judgments (/doc/1569253/, /doc/445276/, /doc/1953529/).
Indian Kanoon labels these texts: "The original publication document is not available
and this content could not be verified."

Usage: python scripts/fetch_acts.py [--no-download]
"""

import csv
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ACTS = {
    "BNS": 149679501, "BNSS": 91117739, "BSA": 70224818,
    "IPC": 1569253, "CrPC": 445276, "IEA": 1953529,
}
OUT = ROOT / "data" / "statutes"

# "103. Punishment for murder." at the start of a section (number, optional letters, dot, heading, dot)
# Headings may contain abbreviations ("etc.,", "Govt. of"), so a "." followed by "," or a
# lower-case word does not end the heading.
_SEC = re.compile(r"(?:(?<=\s)|^)(\d{1,3}[A-Z]{0,3})\.\s+([A-Z](?:[^.]|\.(?=,|\s?[a-z])){2,200}?)\.(?=\s|—|-)")
_XREF = re.compile(r"\[\s*Similar to Section\s+([0-9A-Za-z, ()and&-]+?)\s+from\s+Old\s+(CrPC|IPC|IEA|Evidence Act|Indian Evidence Act)[^\]]*\]", re.I)


def to_text(raw_html: str) -> str:
    t = re.sub(r"<[^>]+>", " ", raw_html)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def split_sections(act: str, text: str):
    """Split on section headings in increasing numeric order (skips cross-references inside text)."""
    out, last_num = [], 0
    matches = list(_SEC.finditer(text))
    starts = []
    for m in matches:
        num = int(re.match(r"\d+", m.group(1)).group(0))
        if last_num <= num <= last_num + 20:  # sections appear in order (repealed ones leave gaps); ignore stray numbers
            starts.append(m)
            last_num = num
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        body = text[m.start():end].strip()
        refs = []
        for x in _XREF.finditer(body):
            old_act = "IEA" if "vid" in x.group(2).lower() else ("CrPC" if x.group(2).lower() == "crpc" else x.group(2).upper())
            sec = re.sub(r"(\d)\(([A-Za-z]{1,2})\)", lambda mm: mm.group(1) + mm.group(2).upper(), x.group(1).strip())
            refs.append({"old_act": old_act, "old_section": sec})
        out.append({"act": act, "section": m.group(1), "heading": m.group(2).strip(),
                    "text": _XREF.sub("", body).strip()[:6000], "old_refs": refs})
    return out


def main() -> int:
    download = "--no-download" not in sys.argv
    (OUT / "acts").mkdir(parents=True, exist_ok=True)
    if download:
        from ingestion.kanoon_fetcher import fetch_document  # reads INDIANKANOON_API_TOKEN from .env
        for code, tid in ACTS.items():
            p = OUT / "acts" / f"{code}.json"
            if p.exists():
                print(f"  [SKIP] {code} already downloaded")
                continue
            p.write_text(json.dumps(fetch_document(str(tid)), ensure_ascii=False), encoding="utf-8")
            print(f"  [SAVED] {code} (tid {tid})")
    rows, xrefs = [], []
    for code in ACTS:
        p = OUT / "acts" / f"{code}.json"
        if not p.exists():
            print(f"FAIL: {code} missing")
            return 1
        d = json.loads(p.read_text(encoding="utf-8"))
        secs = split_sections(code, to_text(d.get("doc", "")))
        print(f"{code}: '{d.get('title')}' -> {len(secs)} sections, {sum(1 for s in secs if s['old_refs'])} with an 'Old' cross-reference")
        rows += secs
        xrefs += [(r["old_act"], r["old_section"], code, s["section"], s["heading"]) for s in secs for r in s["old_refs"]]
    with open(OUT / "sections.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT / "ik_crossref.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["old_act", "old_section", "new_act", "new_section", "new_heading"])
        w.writerows(xrefs)
    print(f"OK: {len(rows)} sections -> data/statutes/sections.jsonl; {len(xrefs)} cross-references -> data/statutes/ik_crossref.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
