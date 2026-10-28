"""
Environment check. Confirms every required variable is present and makes one
cheap live call per service. Prints OK/FAIL per check, never any value.
Exit code is nonzero if anything fails.

  Token Factory: GET {base}/models, and every configured Nemotron ID is in the list
  Tavily:        one-result search

Usage: python scripts/check_env.py
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import REQUIRED_ENV  # noqa: E402  (loads .env)


def _http(url, headers, body=None, timeout=20):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())


def main() -> int:
    failures = 0

    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
    for k in REQUIRED_ENV:
        print(f"{'OK  ' if k not in missing else 'FAIL'} env {k} {'present' if k not in missing else 'missing'}")
    failures += len(missing)

    # Token Factory
    try:
        status, data = _http(os.environ["TOKEN_FACTORY_BASE_URL"].rstrip("/") + "/models",
                             {"Authorization": f"Bearer {os.environ['TOKEN_FACTORY_API_KEY']}"})
        ids = {m.get("id") for m in data.get("data", [])}
        print(f"OK   token_factory list models (HTTP {status}, {len(ids)} models)")
        for var in ("NEMOTRON_NANO_MODEL", "NEMOTRON_SUPER_MODEL", "NEMOTRON_ULTRA_MODEL"):
            ok = os.getenv(var) in ids
            failures += not ok
            print(f"{'OK  ' if ok else 'FAIL'} token_factory {var} {'in live model list' if ok else 'NOT in live model list'}")
    except (KeyError, urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as e:
        failures += 1
        print(f"FAIL token_factory list models ({type(e).__name__}{': HTTP ' + str(e.code) if hasattr(e, 'code') else ''})")

    # Tavily
    try:
        status, data = _http("https://api.tavily.com/search",
                             {"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}", "Content-Type": "application/json"},
                             {"query": "Supreme Court of India anticipatory bail", "max_results": 1})
        n = len(data.get("results", []))
        ok = n >= 1
        failures += not ok
        print(f"{'OK  ' if ok else 'FAIL'} tavily search (HTTP {status}, {n} result)")
    except (KeyError, urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as e:
        failures += 1
        print(f"FAIL tavily search ({type(e).__name__}{': HTTP ' + str(e.code) if hasattr(e, 'code') else ''})")

    print("ALL OK" if failures == 0 else f"{failures} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
