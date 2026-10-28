"""
Smoke test against a running deployment (local or live).

  python scripts/smoke_test.py --api https://<railway-host> --web https://<vercel-host> [--full]

Checks: health ok, samples are synthetic, an audit request streams to a result,
the web app serves, and its JS bundle contains no key-shaped strings.
--full also runs one brief (costs Token Factory tokens).
Exit code is nonzero on any failure.
"""

import argparse
import json
import re
import sys
import urllib.request

SECRET_PATTERNS = [r"tvly-[A-Za-z0-9-]{10,}", r"v1\.CmQK[A-Za-z0-9_\-.]{20,}", r"TOKEN_FACTORY_API_KEY", r"TAVILY_API_KEY"]


def get(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")


def sse(url, body, timeout=600):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
    steps, result = [], None
    with urllib.request.urlopen(req, timeout=timeout) as r:
        buf = r.read().decode("utf-8")
    for block in buf.split("\n\n"):
        ev = re.search(r"^event: (.*)$", block, re.M)
        data = re.search(r"^data: (.*)$", block, re.M)
        if not ev or not data:
            continue
        payload = json.loads(data.group(1))
        if ev.group(1) == "step":
            steps.append(payload)
        elif ev.group(1) == "result":
            result = payload
        elif ev.group(1) == "error":
            raise RuntimeError(payload)
    return steps, result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--web")
    ap.add_argument("--full", action="store_true")
    a = ap.parse_args()
    api = a.api.rstrip("/")
    fails = 0

    def check(name, fn):
        nonlocal fails
        try:
            detail = fn()
            print(f"OK   {name}: {detail}")
        except Exception as e:
            fails += 1
            print(f"FAIL {name}: {type(e).__name__}: {str(e)[:200]}")

    def health():
        s, t = get(f"{api}/api/health")
        h = json.loads(t)
        assert s == 200 and h["status"] == "ok", h
        return f"vectors={h['vectors_in_db']} judgments={h['judgments_in_store']} models={list(h['models'].values())}"

    def samples():
        s, t = get(f"{api}/api/samples")
        d = json.loads(t)
        assert s == 200 and d and all("SYNTHETIC" in v for v in d.values())
        return f"{len(d)} synthetic samples"

    def audit():
        draft = ("The applicant relies on Swaroop Singh v. State of M.P., 2013 (15) SCC 240, and on "
                 "Imaginary Kumar v. State of Nowhere, (2031) 4 SCC 777 (a deliberately fabricated citation).")
        steps, res = sse(f"{api}/api/audit", {"draft_text": draft})
        verdicts = {v["case_name"]: v["verdict"] for v in res["verdicts"]}
        fake = [v for k, v in verdicts.items() if "Imaginary" in k]
        assert fake and fake[0] != "verified", verdicts
        return f"{len(steps)} steps, verdicts={verdicts}"

    check("health", health)
    check("samples", samples)
    check("audit stream", audit)
    if a.full:
        def brief():
            _, t = get(f"{api}/api/samples")
            fir = json.loads(t)["fir_dowry"]
            steps, res = sse(f"{api}/api/brief", {"fir_text": fir, "perspective": "defense"})
            assert res and res.get("brief") and not res.get("error"), res.get("error")
            return f"{len(steps)} steps, {sum(len(s['items']) for s in res['brief']['sections'])} sentences, {len(res['brief']['flagged'])} flagged"
        check("brief stream", brief)
    if a.web:
        def web():
            s, html = get(a.web)
            assert s == 200 and "<div id=\"root\"" in html
            js = re.findall(r'src="(/assets/[^"]+\.js)"', html)
            leaked = []
            for path in js:
                _, body = get(a.web.rstrip("/") + path)
                leaked += [p for p in SECRET_PATTERNS if re.search(p, body)]
            assert not leaked, f"secret-like strings in bundle: {leaked}"
            return f"HTTP 200, {len(js)} bundle file(s) scanned, no secrets"
        check("web app", web)
    print("ALL OK" if not fails else f"{fails} FAILURE(S)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
