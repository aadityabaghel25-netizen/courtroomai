"""
Shared test helpers.

MOCK DATA NOTICE: FIXTURE_JUDGMENT and the stub judges below are synthetic test
doubles. They exist only in tests and are never presented as real law.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.claims import JudgeVerdict  # noqa: E402
from core.judgments import Judgment, JudgmentStore  # noqa: E402
from core.normalize import normalize  # noqa: E402

FIXTURE_JUDGMENT = Judgment(
    case_id="MOCK-0001",
    title="Mock Petitioner vs State Of Testland on 1 January, 2020",
    court="MOCK High Court (synthetic test fixture)",
    date="2020-01-01",
    source_url="https://example.invalid/mock-0001",
    citations=["(2020) 1 MOCK 1"],
    text=normalize(
        "Mock Petitioner vs State Of Testland. "
        "The petitioner sought anticipatory bail. "
        "We hold that anticipatory bail may be granted where the accused has joined the investigation and there is no risk of flight. "
        "The prosecution argued that the offence was grave. "
        "The appeal is allowed."
    ),
)

FIR_TEXT = (
    "FIR No. 112/2023, P.S. Sample Nagar. On 14.03.2023 at about 9 pm the complainant Ram Lal reported that "
    "the accused snatched his mobile phone near the bus stand and ran away. Sections 379 and 356 IPC."
)



def stub_judge(verdict: str, quote: str, model: str = "MOCK-judge"):
    """MOCK: a judge test double returning a fixed verdict."""
    def _j(prompt: str):
        return {"value": JudgeVerdict(verdict=verdict, quote=quote, reason="mock"), "model": model, "fallback": None}
    return _j


def has_live_keys() -> bool:
    from core.config import REQUIRED_ENV
    return all(os.getenv(k) for k in REQUIRED_ENV)
