"""
Typed claim schema. Every sentence the advocate sees is rendered from one of these.

Status semantics (fail closed):
  passed      the type-specific check succeeded against a source
  weak        partial support (precedent judge said "partial")
  failed      the check ran and the claim is contradicted / absent from the source
  unverified  the check could not complete (timeout, parse error, missing source)
"""

from enum import Enum
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    fact = "fact"
    statute_mapping = "statute_mapping"
    precedent_holding = "precedent_holding"
    good_law_status = "good_law_status"
    strategy_suggestion = "strategy_suggestion"
    outcome_count = "outcome_count"


class Status(str, Enum):
    passed = "passed"
    weak = "weak"
    failed = "failed"
    unverified = "unverified"


class FirSpan(BaseModel):
    kind: Literal["fir_span"] = "fir_span"
    start: int
    end: int
    text: str


class JudgmentPassage(BaseModel):
    kind: Literal["judgment_passage"] = "judgment_passage"
    case_id: str
    quote: str
    title: Optional[str] = None
    court: Optional[str] = None
    date: Optional[str] = None
    source_url: Optional[str] = None
    judge_verdict: Optional[str] = None
    judge_quote: Optional[str] = None
    judge_model: Optional[str] = None


class MappingRow(BaseModel):
    kind: Literal["mapping_row"] = "mapping_row"
    row_id: str
    old_act: str
    old_section: str
    new_act: str
    new_section: str
    source: str


class WebResult(BaseModel):
    kind: Literal["web_result"] = "web_result"
    url: str
    title: str = ""
    snippet: str = ""


Evidence = Union[FirSpan, JudgmentPassage, MappingRow, WebResult]


class Claim(BaseModel):
    id: str
    type: ClaimType
    text: str
    evidence: List[Evidence] = Field(default_factory=list)
    status: Status = Status.unverified
    reason: str = "not yet verified"
    # strategy_suggestion only: IDs of passed claims it relies on
    refs: List[str] = Field(default_factory=list)
    attempts: int = 0
    judge_agreement: Optional[str] = None  # stretch; e.g. "4 of 5"


# --- Model-facing drafts -------------------------------------------------
# What Super is allowed to emit. The verifier turns these into Claims.

class DraftClaim(BaseModel):
    type: Literal["fact", "precedent_holding", "strategy_suggestion"]
    text: str = Field(min_length=3, max_length=1200)
    # fact: verbatim FIR excerpt. precedent_holding: verbatim judgment quote.
    quote: Optional[str] = None
    case_id: Optional[str] = None
    refs: List[str] = Field(default_factory=list)


class DraftClaims(BaseModel):
    claims: List[DraftClaim]


class DraftPrecedent(BaseModel):
    """A precedent claim as Super must write it: every field required."""
    case_id: str = Field(min_length=1)
    quote: str = Field(min_length=20, max_length=1500)
    text: str = Field(min_length=10, max_length=800)


class DraftStrategy(BaseModel):
    text: str = Field(min_length=10, max_length=800)
    refs: List[str] = Field(min_length=1)


class DraftOutput(BaseModel):
    precedents: List[DraftPrecedent] = Field(max_length=8)
    strategies: List[DraftStrategy] = Field(max_length=5)


# --- Judge output --------------------------------------------------------

class JudgeVerdict(BaseModel):
    verdict: Literal["supports", "partial", "contradicts", "not_addressed"]
    quote: str = ""
    reason: str = ""
