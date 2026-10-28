"""
Pydantic response models for CourtroomAI API.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class IPCSection(BaseModel):
    section: str
    title: str
    explanation: str
    applies_to: str
    max_punishment: str = ""


class VerifiedCitation(BaseModel):
    verdict: str
    confidence: float
    reason: str
    title: str
    court: str
    date: str
    passage_preview: str


class PrimaryArgument(BaseModel):
    argument: str
    supporting_citation: str = ""
    strength: str


class Strategy(BaseModel):
    executive_summary: str = ""
    key_legal_issues: List[str] = []
    primary_arguments: List[PrimaryArgument] = []
    counter_arguments_to_anticipate: List[str] = []
    recommended_next_steps: List[str] = []
    overall_case_strength: str = ""
    risk_factors: List[str] = []


class AnalyzeResponse(BaseModel):
    """POST /api/analyze response."""
    success: bool = True
    strategy: Dict[str, Any] = {}
    ipc_sections: List[Dict[str, Any]] = []
    verified_citations: List[Dict[str, Any]] = []
    raw_response: str = ""
    processing_time: float = 0.0
    num_steps: int = 0


class VerifyResponse(BaseModel):
    """POST /api/verify response."""
    success: bool = True
    results: List[VerifiedCitation] = []
    total_verified: int = 0
    total_rejected: int = 0


class UploadResponse(BaseModel):
    """POST /api/upload response."""
    success: bool = True
    text: str
    num_pages: int
    filename: str
    char_count: int
    extracted_metadata: Dict[str, Any] = {}


class HealthResponse(BaseModel):
    """GET /api/health response."""
    status: str = "healthy"
    vector_count: int = 0
    raw_documents: int = 0
    uptime_seconds: float = 0.0


class ErrorResponse(BaseModel):
    """Standard error response."""
    success: bool = False
    error: str
    detail: str = ""
