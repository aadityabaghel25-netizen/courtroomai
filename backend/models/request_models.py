"""
Pydantic request models for CourtroomAI API.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    """POST /api/analyze — main pipeline input."""
    fir_text: str = Field(
        ...,
        min_length=20,
        description="FIR text, legal notice, or case description to analyze",
        json_schema_extra={"example": "FIR No. 234/2024. Under Sections 302, 120B IPC..."}
    )
    perspective: str = Field(
        default="defense",
        description="Legal perspective: 'defense' or 'prosecution'",
        pattern="^(defense|prosecution)$",
    )


class PassageInput(BaseModel):
    """A single passage for standalone citation verification."""
    passage: str
    title: str = "Unknown"
    court: str = "Unknown Court"
    date: str = "Unknown Date"
    doc_id: str = ""


class VerifyRequest(BaseModel):
    """POST /api/verify — standalone citation verification."""
    argument: str = Field(
        ...,
        min_length=10,
        description="The legal argument to verify citations against",
    )
    passages: List[PassageInput] = Field(
        ...,
        min_length=1,
        description="List of passages to verify",
    )
