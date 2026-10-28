"""
PDF Parser for FIR / Legal Notice documents
Uses pdfplumber — handles complex legal PDF layouts better than PyPDF2.
"""

import pdfplumber
from pathlib import Path
from dataclasses import dataclass


@dataclass
class ParsedDocument:
    text: str
    num_pages: int
    filename: str
    char_count: int


def parse_pdf(pdf_path: str) -> ParsedDocument:
    """
    Parse a legal PDF (FIR, legal notice, charge sheet).
    Returns clean text with page structure preserved.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    full_text = []

    with pdfplumber.open(pdf_path) as pdf:
        num_pages = len(pdf.pages)

        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                # Add page marker — useful for citation references later
                full_text.append(f"\n[PAGE {i+1}]\n{text.strip()}")

    combined = "\n".join(full_text)

    return ParsedDocument(
        text=combined,
        num_pages=num_pages,
        filename=path.name,
        char_count=len(combined),
    )


def parse_text_input(raw_text: str) -> ParsedDocument:
    """
    Handle plain text input (when user pastes FIR text directly).
    Wraps in same ParsedDocument format for uniform downstream handling.
    """
    return ParsedDocument(
        text=raw_text.strip(),
        num_pages=1,
        filename="text_input",
        char_count=len(raw_text),
    )


def extract_fir_metadata(text: str) -> dict:
    """
    Best-effort extraction of structured fields from FIR text.
    These become metadata tags in Chroma for filtered retrieval.
    Not perfect — just gets you 80% of the way there.
    """
    import re

    metadata = {
        "fir_number": None,
        "police_station": None,
        "sections_mentioned": [],
        "date": None,
    }

    # IPC sections — matches patterns like "Section 302", "u/s 498A", "IPC 420"
    section_pattern = r"(?:Section|Sec\.|u/s|IPC)\s*(\d{1,3}[A-Za-z]?)"
    sections = re.findall(section_pattern, text, re.IGNORECASE)
    metadata["sections_mentioned"] = list(set(sections))

    # FIR number
    fir_pattern = r"FIR\s*No\.?\s*(\d+/\d{4}|\d+)"
    fir_match = re.search(fir_pattern, text, re.IGNORECASE)
    if fir_match:
        metadata["fir_number"] = fir_match.group(1)

    return metadata


if __name__ == "__main__":
    # Quick test with a sample text
    sample = """
    FIR No. 123/2024
    Police Station: Kotwali
    Under Section 302 and 498A IPC
    The accused is alleged to have committed murder.
    """
    doc = parse_text_input(sample)
    meta = extract_fir_metadata(doc.text)
    print(f"Text length: {doc.char_count} chars")
    print(f"Extracted metadata: {meta}")
