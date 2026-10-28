"""
Probe Token Factory structured-output support per Nemotron model:
plain, response_format=json_object, response_format=json_schema, tool calling.
Writes logs/probe_structured_<ts>.json. Prints a summary table. Uses tiny prompts.

Usage: python scripts/probe_structured.py
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.config import settings  # noqa: E402

SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["yes", "no"]}},
          "required": ["verdict"], "additionalProperties": False}
MSG = [{"role": "user", "content": 'Is 7 a prime number? Reply as JSON {"verdict": "yes"|"no"}.'}]

MODES = {
    "plain": {},
    "json_object": {"response_format": {"type": "json_object"}},
    "json_schema": {"response_format": {"type": "json_schema", "json_schema": {"name": "v", "schema": SCHEMA, "strict": True}}},
    "tools": {"tools": [{"type": "function", "function": {"name": "answer", "parameters": SCHEMA}}],
              "tool_choice": {"type": "function", "function": {"name": "answer"}}},
}


def call(model, extra):
    body = {"model": model, "messages": MSG, "temperature": 0, "max_tokens": 1500, **extra}
    req = urllib.request.Request(settings.base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {os.environ['TOKEN_FACTORY_API_KEY']}",
                                          "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read().decode())
        m = d["choices"][0]["message"]
        content = m.get("content") or ""
        tool_args = (m.get("tool_calls") or [{}])[0].get("function", {}).get("arguments")
        parsed = None
        for cand in (tool_args, content):
            try:
                if cand:
                    parsed = json.loads(cand)
                    break
            except json.JSONDecodeError:
                pass
        return {"http": 200, "latency_s": round(time.time() - t0, 2), "usage": d.get("usage"),
                "has_reasoning_field": bool(m.get("reasoning_content") or m.get("reasoning")),
                "content_head": content[:160], "tool_args": tool_args, "parsed_json": parsed,
                "valid": isinstance(parsed, dict) and parsed.get("verdict") in ("yes", "no")}
    except urllib.error.HTTPError as e:
        return {"http": e.code, "latency_s": round(time.time() - t0, 2), "error": e.read().decode()[:300], "valid": False}
    except Exception as e:
        return {"http": None, "latency_s": round(time.time() - t0, 2), "error": f"{type(e).__name__}: {e}"[:300], "valid": False}


def main():
    models = {"nano": settings.nano_model, "super": settings.super_model, "ultra": settings.ultra_model}
    out = {"ts": datetime.now(timezone.utc).isoformat(), "base_url_host": settings.base_url.split("/")[2], "results": {}}
    for role, model in models.items():
        for mode, extra in MODES.items():
            r = call(model, extra)
            out["results"][f"{role}:{mode}"] = {"model": model, **r}
            print(f"{role:5} {mode:11} http={r['http']} valid={r['valid']} {r['latency_s']}s "
                  f"tokens={(r.get('usage') or {}).get('total_tokens')} {('ERR ' + r['error'][:90]) if r.get('error') else ''}")
    settings.logs_dir.mkdir(exist_ok=True)
    path = settings.logs_dir / f"probe_structured_{out['ts'][:19].replace(':', '')}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
