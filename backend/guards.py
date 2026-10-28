"""
Request guards: body size limit, per-IP rate limit, daily spend cap.

Spend cap: computed from the persisted token log (logs/llm_calls.jsonl).
Cost in USD is computed only when per-model prices are configured
(TF_PRICE_IN_<ROLE> / TF_PRICE_OUT_<ROLE>, USD per 1M tokens); otherwise the
cap falls back to DAILY_TOKEN_CAP total tokens. Prices are never guessed.
"""

import json
import os
import threading
import time
from collections import defaultdict, deque
from datetime import date
from typing import Dict, Optional, Tuple

from fastapi import HTTPException, Request

from core.config import settings

MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", 40_000))
RATE_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", 4))
RATE_PER_DAY = int(os.getenv("RATE_LIMIT_PER_DAY", 40))
DAILY_TOKEN_CAP = int(os.getenv("DAILY_TOKEN_CAP", 3_000_000))

_lock = threading.Lock()
_hits: Dict[str, deque] = defaultdict(deque)


def client_ip(request: Request) -> str:
    # Cloud Run / Railway append the real client address last; earlier entries are client-supplied.
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[-1].strip() if fwd else (request.client.host if request.client else "unknown")


def check_rate(request: Request) -> None:
    ip = client_ip(request)
    now = time.time()
    with _lock:
        q = _hits[ip]
        while q and now - q[0] > 86400:
            q.popleft()
        last_min = sum(1 for t in q if now - t < 60)
        if last_min >= RATE_PER_MIN or len(q) >= RATE_PER_DAY:
            raise HTTPException(status_code=429, detail="Rate limit reached. Please try again later.")
        q.append(now)


async def check_size(request: Request) -> bytes:
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail=f"Request too large (max {MAX_BODY_BYTES} bytes).")
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail=f"Request too large (max {MAX_BODY_BYTES} bytes).")
    return body


def _price(role: str) -> Optional[Tuple[float, float]]:
    i, o = os.getenv(f"TF_PRICE_IN_{role.upper()}"), os.getenv(f"TF_PRICE_OUT_{role.upper()}")
    try:
        return (float(i), float(o)) if i and o else None
    except ValueError:
        return None


def spend_today() -> Dict[str, Optional[float]]:
    """Tokens and (if prices are configured) USD spent today, from the call log."""
    path = settings.logs_dir / "llm_calls.jsonl"
    tokens, usd, priced = 0, 0.0, True
    if path.exists():
        today = date.today().isoformat()
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not r.get("ts", "").startswith(today) or r.get("model") == "tavily":
                    continue
                pt, ct = r.get("prompt_tokens", 0), r.get("completion_tokens", 0)
                tokens += pt + ct
                p = _price(r.get("role", ""))
                if p is None:
                    priced = False
                else:
                    usd += (pt * p[0] + ct * p[1]) / 1e6
    return {"tokens": tokens, "usd": round(usd, 4) if priced and tokens else (0.0 if not tokens else None)}


def check_spend() -> None:
    s = spend_today()
    if s["usd"] is not None and s["usd"] >= settings.daily_spend_cap_usd:
        raise HTTPException(status_code=503, detail="Daily usage cap reached. The demo resets tomorrow (UTC).")
    if s["tokens"] >= DAILY_TOKEN_CAP:
        raise HTTPException(status_code=503, detail="Daily usage cap reached. The demo resets tomorrow (UTC).")
