"""
Build data/judgments/judgments.jsonl from data/raw/*.json (Indian Kanoon API dumps).

Each line: case_id, title, court, date, source_url, text (HTML stripped + normalised).
Bare-act files are skipped: they are statute text, not judgments.

Usage: python scripts/build_judgments.py
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import ROOT, settings  # noqa: E402
from core.normalize import html_to_text, normalize  # noqa: E402

RAW = ROOT / "data" / "raw"
_EQUIV = re.compile(r"Equivalent citations:(.*?)(?:Author:|Bench:|Cites \d|$)")


def equivalent_citations(text: str):
    """Reporter citations Indian Kanoon lists at the top of the judgment, if any."""
    m = _EQUIV.search(text[:3000])
    if not m:
        return []
    return [c.strip() for c in m.group(1).split(",") if re.search(r"\d", c) and c.strip()]


def main() -> int:
    files = sorted(p for p in RAW.glob("*.json") if not p.name.startswith("bare_act_"))
    if not files:
        print(f"FAIL: no judgment files in {RAW}")
        return 1
    settings.judgments_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(settings.judgments_path, "w", encoding="utf-8") as out:
        for p in files:
            d = json.loads(p.read_text(encoding="utf-8"))
            case_id = str(d.get("tid") or d.get("_meta", {}).get("doc_id") or p.stem)
            text = normalize(html_to_text(d.get("doc", "")))
            if not text:
                continue
            out.write(json.dumps({
                "case_id": case_id,
                "title": d.get("title") or d.get("_meta", {}).get("title", ""),
                "court": d.get("docsource", ""),
                "date": d.get("publishdate", ""),
                "source_url": f"https://indiankanoon.org/doc/{case_id}/",
                "citations": equivalent_citations(text),
                "text": text,
            }, ensure_ascii=False) + "\n")
            n += 1
    print(f"OK: wrote {n} judgments to {settings.judgments_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
