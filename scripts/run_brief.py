"""
Run brief mode end to end from the command line.

Usage: python scripts/run_brief.py samples/fir_snatching.txt [--perspective defense|prosecution] [--no-verify]
Writes the final state to runs/brief_<name>_<ts>.json and prints the trace and brief.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.pipeline import build_graph, initial_state  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fir")
    ap.add_argument("--perspective", default="defense", choices=["defense", "prosecution"])
    ap.add_argument("--no-verify", action="store_true")
    a = ap.parse_args()
    fir = Path(a.fir).read_text(encoding="utf-8")
    graph = build_graph()
    t0 = time.time()
    final = {}
    for update in graph.stream(initial_state(fir, a.perspective, not a.no_verify), stream_mode="updates"):
        for node, delta in update.items():
            final.update(delta)
            if delta.get("trace"):
                ev = delta["trace"][-1]
                print(f"[{ev['step']:9}] {ev['status']:8} {ev.get('elapsed_s')}s  model={ev.get('model')}  {ev['detail']}")
    print(f"total {time.time() - t0:.1f}s")
    brief = final.get("brief", {})
    for sec in brief.get("sections", []):
        print(f"\n## {sec['title']}")
        for it in sec["items"]:
            print(f"- [{it['claim_id']}] {it['text']}")
    print(f"\nFlagged ({len(brief.get('flagged', []))}):")
    for f in brief.get("flagged", []):
        print(f"- [{f['claim_id']}] {f['status']}: {f['reason']}")
    print(f"Lint drops: {len(brief.get('lint_drops', []))}")
    out = ROOT / "runs" / f"brief_{Path(a.fir).stem}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(final, indent=2, default=str))
    print(f"wrote {out.relative_to(ROOT)}")
    if final.get("error"):
        print(f"ERROR: {final['error']}")
        return 1
    return 0 if brief else 1


if __name__ == "__main__":
    sys.exit(main())
