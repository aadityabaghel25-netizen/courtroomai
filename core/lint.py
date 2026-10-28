"""
Output lint. Extracts every case name, citation, section number, date and number
from rendered text; each must appear in the passed-claim set or the FIR,
otherwise the whole sentence is dropped and the drop is logged.
"""

import re
from dataclasses import dataclass, field
from typing import Iterable, List

from core.normalize import normalize

_CASE_NAME = re.compile(
    r"\b([A-Z][\w.&'-]*(?:\s+(?:of|and|&|the|[A-Z][\w.&'-]*))*)\s+(?:v\.|vs\.?|versus|v)\s+"
    r"([A-Z][\w.&'-]*(?:\s+(?:of|and|&|the|[A-Z][\w.&'-]*))*)"
)
_CITATION = re.compile(
    r"\(\s*\d{4}\s*\)\s*\d+\s*[A-Z][A-Za-z.]*\s*\d+"      # (2014) 8 SCC 273
    r"|\bAIR\s+\d{4}\s+[A-Z][A-Za-z.]*\s+\d+"              # AIR 1980 SC 1579
    r"|\b\d{4}\s+SCC\s+OnLine\s+[A-Z][A-Za-z]*\s+\d+"       # 2021 SCC OnLine SC 123
    r"|\b\d{4}\s+(?:INSC|SCR|Cri\s?LJ|CrLJ)\s+\d+"
)
_SECTION = re.compile(r"\b(?:Sections?|Sec\.|S\.|u/s)\s*(\d+[A-Z]?(?:\(\d+\))?)", re.IGNORECASE)
_DATE = re.compile(
    r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b"
    r"|\b\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*,?\s+\d{4}\b"
    r"|\b\d{4}-\d{2}-\d{2}\b"
)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[(\"'])")


@dataclass
class Drop:
    sentence: str
    unknown: List[str]


@dataclass
class LintResult:
    text: str
    drops: List[Drop] = field(default_factory=list)


def _canon(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", normalize(s).lower()).strip()


def extract_entities(sentence: str) -> List[str]:
    ents: List[str] = []
    for m in _CASE_NAME.finditer(sentence):
        ents.append(m.group(0))
    ents += _CITATION.findall(sentence)
    ents += [f"section {s}" for s in _SECTION.findall(sentence)]
    ents += _DATE.findall(sentence)
    ents += _NUMBER.findall(sentence)
    return ents


def _known(entity: str, allowed_canon: str, allowed_numbers: set) -> bool:
    if re.fullmatch(r"[\d.,]+", entity):
        return entity.replace(",", "") in allowed_numbers
    if entity.startswith("section "):
        return entity.split(" ", 1)[1].upper().split("(")[0] in allowed_numbers
    if re.search(r"\s(v\.|vs\.?|versus|v)\s", entity):
        # Case names: both sides must appear; the second side is matched on its first word.
        left, right = re.split(r"\s+(?:v\.|vs\.?|versus|v)\s+", entity, maxsplit=1)
        return _canon(left) in allowed_canon and _canon(right).split(" ")[0] in allowed_canon
    return _canon(entity) in allowed_canon


# Tokens ending in "." that do not end a sentence in Indian legal writing.
_ABBREV = re.compile(
    r"(?:\b(?:v|vs|No|Nos|Sec|S|Ss|Ors|Anr|Hon'ble|Mr|Mrs|Ms|Dr|Smt|Shri|J|JJ|Cr|Crl|Art|Para|para|p|pp|viz|i\.e|e\.g|etc|cf|Govt|St|Jr|Ltd|Co|Pvt)|\b[A-Z])\.$"
)


def split_sentences(text: str) -> List[str]:
    parts = [s for s in _SENTENCE.split(text.strip()) if s.strip()]
    merged: List[str] = []
    for p in parts:
        if merged and _ABBREV.search(merged[-1]):
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    return merged


def lint_text(text: str, allowed_sources: Iterable[str]) -> LintResult:
    allowed = " ".join(allowed_sources)
    allowed_canon = " " + _canon(allowed) + " "
    allowed_numbers = {n.replace(",", "") for n in _NUMBER.findall(allowed)}
    allowed_numbers |= {m.upper() for m in re.findall(r"\b\d+[A-Z]\b", allowed, re.IGNORECASE)}
    kept, drops = [], []
    for sent in split_sentences(text):
        unknown = [e for e in extract_entities(sent) if not _known(e, allowed_canon, allowed_numbers)]
        if unknown:
            drops.append(Drop(sentence=sent, unknown=unknown))
        else:
            kept.append(sent)
    return LintResult(text=" ".join(kept), drops=drops)
