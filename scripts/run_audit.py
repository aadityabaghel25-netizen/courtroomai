"""
Run audit mode end to end from the command line.

Usage: python scripts/run_audit.py samples/draft_audit_demo.txt
Writes runs/audit_<name>_<ts>.json.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.audit import run_audit  # noqa: E402
from core.judgments import JudgmentStore  # noqa: E402


def main():
    path = Path(sys.argv[1])
    out = run_audit(path.read_text(encoding="utf-8"), JudgmentStore.load(),
                    on_event=lambda e: print(f"[{e['step']:8}] {e['status']:6} {e.get('elapsed_s')}s model={e.get('model')} {e['detail']}"))
    for v in out.get("verdicts", []):
        print(f"\n#{v['index']} {v['case_name']} | {v['citation']}\n   cited for: {v['proposition'][:140]}\n   VERDICT: {v['verdict']} — {v['label']}\n   reason: {v['reason'][:200]}")
    dest = ROOT / "runs" / f"audit_{path.stem}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0 if out.get("verdicts") is not None and not out.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
