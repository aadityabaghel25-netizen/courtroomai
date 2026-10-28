"""
Text normalisation shared by every verbatim check.

The rule from the spec: a quote matches a source only after whitespace and
Unicode normalisation. Nothing else (no lowercasing, no punctuation folding).
Stored judgments are Indian Kanoon HTML, so HTML is converted to text first;
that conversion is applied to the source only, never to the quote.
"""

import html
import re
import unicodedata

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def html_to_text(raw: str) -> str:
    """Strip tags and decode entities. Block tags become spaces so words never fuse."""
    text = _TAG.sub(" ", raw or "")
    return html.unescape(text)


def normalize(text: str) -> str:
    """Unicode NFKC + collapse all whitespace runs to one space + strip."""
    text = unicodedata.normalize("NFKC", text or "")
    return _WS.sub(" ", text).strip()


def contains_verbatim(haystack_normalized: str, needle: str) -> bool:
    """True only if the normalised needle is a non-empty substring of the normalised haystack."""
    n = normalize(needle)
    return bool(n) and n in haystack_normalized


def find_span(haystack_normalized: str, needle: str):
    """Return (start, end) offsets of the normalised needle in the normalised haystack, or None."""
    n = normalize(needle)
    if not n:
        return None
    i = haystack_normalized.find(n)
    return None if i < 0 else (i, i + len(n))
