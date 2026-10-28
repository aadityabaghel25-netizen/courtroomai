"""
Fetch the full text of a judgment that is not in our library, using Tavily Extract.

Only full-judgment pages on trusted hosts are fetched; blogs, news and summaries are
never used because they can misquote. The fetched page must look like the cited case
(both parties named near the top, judgment-length text) before any check runs on it.

Live checks on 2026-10-28: basic extract failed on indiankanoon.org ("Failed to fetch url");
extract_depth "advanced" returned the full judgment in 4.3 s, and three known verbatim
quotes matched after cleaning (see FEEDBACK.md).
"""

import json
import os
import re
import time
import urllib.request
from typing import Dict, Optional
from urllib.parse import urlparse

from core.llm import CallRecord, usage_log
from core.normalize import normalize

TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"

# host -> path rule. Only pages that carry a whole judgment.
TRUSTED = [
    (re.compile(r"(^|\.)indiankanoon\.org$"), re.compile(r"^/doc/\d+/?$")),
    (re.compile(r"(^|\.)sci\.gov\.in$"), re.compile(r".+")),
    (re.compile(r"(^|\.)ecourts\.gov\.in$"), re.compile(r".+")),
    (re.compile(r"(^|\.)nic\.in$"), re.compile(r".+")),
]
MIN_JUDGMENT_CHARS = 3000

_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_MARK = re.compile(r"(\*\*|__|^#+\s|^>\s|`)", re.M)


def is_trusted(url: str) -> bool:
    try:
        u = urlparse(url)
    except ValueError:
        return False
    return u.scheme in ("http", "https") and any(h.search(u.hostname or "") and p.match(u.path or "/") for h, p in TRUSTED)


def clean_markdown(text: str) -> str:
    """Strip markdown that Tavily adds (links, images, emphasis) so quotes can be matched."""
    text = _MD_IMAGE.sub(" ", text or "")
    text = _MD_LINK.sub(r"\1", text)
    return normalize(_MD_MARK.sub("", text))


def extract(url: str, timeout: float = 45.0) -> Optional[str]:
    """Full page text via Tavily Extract (advanced). Returns cleaned text or None. Raises on HTTP error."""
    body = {"urls": [url], "extract_depth": "advanced"}
    req = urllib.request.Request(TAVILY_EXTRACT_URL, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}", "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        usage_log.add(CallRecord(role="extract", model="tavily", ok=True, latency_s=round(time.time() - t0, 3)))
    except Exception as e:
        usage_log.add(CallRecord(role="extract", model="tavily", ok=False, latency_s=round(time.time() - t0, 3),
                                 error=f"{type(e).__name__}: {str(e)[:200]}"))
        raise
    res = data.get("results") or []
    raw = res[0].get("raw_content") if res else None
    return clean_markdown(raw) if raw else None


def looks_like_the_judgment(text: str, party_sides) -> bool:
    """Judgment-length text whose opening names every distinctive party word."""
    if not text or len(text) < MIN_JUDGMENT_CHARS or not party_sides:
        return False
    head = text[:4000].lower()
    return all(all(w in head for w in side) for side in party_sides)


def host(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")


_TITLE = re.compile(r"([A-Z][^\[\]!|\n]{2,160}? (?:vs\.?|v\.|versus) [^\[\]!|\n]{2,120}? on \d{1,2} \w+,? \d{4})")
_COURT = re.compile(r"^(Supreme Court of India|(?:[A-Z][\w.&()-]*\s){0,4}High Court(?:\s?\([^)]*\))?|(?:[A-Z][\w.&()-]*\s){0,3}District Court)\s+")


def page_title(text: str):
    """(title, court) from the top of a judgment page, without site navigation text."""
    m = _TITLE.search(text[:3000])
    if not m:
        return "", ""
    title = m.group(1).strip()
    c = _COURT.match(title)
    if c:
        return title[c.end():].strip(), c.group(1).strip()
    return title, ""


def fetch_judgment(results, party_sides, extractor=extract) -> Optional[Dict[str, str]]:
    """First trusted result whose extracted text is the cited judgment, or None."""
    for r in results:
        url = r.get("url", "")
        if not is_trusted(url):
            continue
        text = extractor(url)
        if text and looks_like_the_judgment(text, party_sides):
            title, court = page_title(text)
            return {"url": url, "text": text, "title": title or r.get("title", ""), "court": court, "host": host(url)}
    return None
