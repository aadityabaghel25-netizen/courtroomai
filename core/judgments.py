"""
Judgment store: full judgment text and metadata keyed by case ID.

Built by scripts/build_judgments.py from data/raw/*.json (Indian Kanoon) into
data/judgments/judgments.jsonl. Text is stored already HTML-stripped and
normalised, so quote checks are a plain substring test.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from core.config import settings
from core.normalize import contains_verbatim, find_span


@dataclass
class Judgment:
    case_id: str
    title: str
    court: str
    date: str
    source_url: str
    text: str  # normalised plain text
    citations: List[str] = field(default_factory=list)  # equivalent reporter citations


class JudgmentStore:
    def __init__(self, judgments: Iterable[Judgment] = ()):
        self._by_id: Dict[str, Judgment] = {j.case_id: j for j in judgments}

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "JudgmentStore":
        path = path or settings.judgments_path
        items = []
        if path.exists():
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        items.append(Judgment(**json.loads(line)))
        return cls(items)

    def __len__(self) -> int:
        return len(self._by_id)

    def exists(self, case_id: str) -> bool:
        return bool(case_id) and str(case_id) in self._by_id

    def get(self, case_id: str) -> Optional[Judgment]:
        return self._by_id.get(str(case_id)) if case_id else None

    def all(self):
        return self._by_id.values()

    def quote_in(self, case_id: str, quote: str) -> bool:
        j = self.get(case_id)
        return j is not None and contains_verbatim(j.text, quote)

    def window(self, case_id: str, quote: str, full_limit: int, half_window: int) -> Optional[str]:
        """Whole judgment if short, else the text around the quote."""
        j = self.get(case_id)
        if j is None:
            return None
        if len(j.text) <= full_limit:
            return j.text
        span = find_span(j.text, quote)
        if span is None:
            return None
        start = max(0, span[0] - half_window)
        end = min(len(j.text), span[1] + half_window)
        return j.text[start:end]

    def find_by_citation(self, citation: str) -> Optional[Judgment]:
        """Exact match on a reporter citation after dropping spaces, brackets and case."""
        key = _cite_key(citation)
        if not key:
            return None
        for j in self._by_id.values():
            if any(_cite_key(c) == key for c in j.citations):
                return j
        return None

    def find_by_title(self, name: str) -> Optional[Judgment]:
        """Loose lookup for audit mode: case-insensitive containment of party names."""
        key = " ".join(name.lower().replace("vs.", "v").replace("vs", "v").replace("v.", "v").split())
        if not key:
            return None
        for j in self._by_id.values():
            t = " ".join(j.title.lower().replace("vs.", "v").replace("vs", "v").replace("v.", "v").split())
            if key in t:
                return j
        return None


def _cite_key(c: str) -> str:
    c = c.upper().replace("SUPREME COURT", "SC")
    return re.sub(r"[^A-Z0-9]", "", c)
