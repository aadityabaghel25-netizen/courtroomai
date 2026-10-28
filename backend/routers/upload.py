"""
POST /api/upload — PDF upload endpoint.
Parses FIR / legal notice PDFs and returns extracted text + metadata.
"""

import tempfile
import os

from fastapi import APIRouter, UploadFile, File, HTTPException

from backend.models.response_models import UploadResponse, ErrorResponse

router = APIRouter(prefix="/api", tags=["Upload"])


@router.post(
    "/upload",
    response_model=UploadResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Upload and parse a legal PDF",
    description="Upload a FIR, legal notice, or charge sheet PDF. "
                "Returns extracted text with metadata (IPC sections, FIR number).",
)
async def upload_pdf(file: UploadFile = File(...)):
    """
    Upload a PDF file, parse it with pdfplumber, and return extracted text.
    The extracted text can then be sent to /api/analyze for full analysis.
    """
    # Validate file type
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail={"success": False, "error": "Only PDF files are accepted"},
        )

    try:
        from ingestion.pdf_parser import parse_pdf, extract_fir_metadata

        # Save uploaded file to temp location (5 MB cap)
        content = await file.read(5_000_001)
        if len(content) > 5_000_000:
            raise HTTPException(status_code=413, detail={"success": False, "error": "PDF too large (max 5 MB)"})
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            # Parse the PDF
            parsed = parse_pdf(tmp_path)
            metadata = extract_fir_metadata(parsed.text)

            return UploadResponse(
                success=True,
                text=parsed.text,
                num_pages=parsed.num_pages,
                filename=file.filename,
                char_count=parsed.char_count,
                extracted_metadata=metadata,
            )
        finally:
            # Clean up temp file
            os.unlink(tmp_path)

    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=400,
            detail={"success": False, "error": f"File processing error: {e}"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"success": False, "error": f"PDF parsing failed: {e}"},
        )
