"""Minimal Tavily Search client over HTTPS (no SDK). Errors propagate; callers fail closed."""

import json
import os
import time
import urllib.request
from typing import Dict, List

from core.llm import CallRecord, usage_log

TAVILY_URL = "https://api.tavily.com/search"


def search(query: str, max_results: int = 3, timeout: float = 20.0) -> List[Dict]:
    body = {"query": query, "max_results": max_results, "search_depth": "basic"}
    req = urllib.request.Request(TAVILY_URL, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}", "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        usage_log.add(CallRecord(role="search", model="tavily", ok=True, latency_s=round(time.time() - t0, 3)))
    except Exception as e:
        usage_log.add(CallRecord(role="search", model="tavily", ok=False, latency_s=round(time.time() - t0, 3),
                                 error=f"{type(e).__name__}: {str(e)[:200]}"))
        raise
    return [{"url": x.get("url", ""), "title": x.get("title", ""), "content": x.get("content", "")}
            for x in data.get("results", [])]
