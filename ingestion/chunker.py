"""
Legal-aware document chunker.
Legal docs need overlap-aware chunking — arguments must not split mid-sentence.
Standard 512-token fixed splits will break legal reasoning chains.
"""

import json
from pathlib import Path
from typing import List
from dataclasses import dataclass

@dataclass
class Chunk:
    text: str
    metadata: dict  # court, date, doc_id, chunk_index, ipc_sections

def chunk_judgment(doc: dict, chunk_size: int = 500, overlap: int = 100) -> List[Chunk]:
    """
    Chunk a single judgment from Indian Kanoon JSON.
    Splits on sentence boundaries, not arbitrary token counts.
    """
    meta = doc.get("_meta", {})
    full_text = doc.get("doc", "") or doc.get("judgement", "") or ""

    if not full_text:
        return []

    # Split into sentences first — preserve legal argument integrity
    import re
    sentences = re.split(r"(?<=[.!?])\s+", full_text)

    chunks = []
    current_chunk = []
    current_len = 0
    chunk_index = 0

    for sentence in sentences:
        sentence_len = len(sentence.split())

        if current_len + sentence_len > chunk_size and current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(Chunk(
                text=chunk_text,
                metadata={
                    "doc_id": meta.get("doc_id", ""),
                    "title": meta.get("title", ""),
                    "court": meta.get("court", ""),
                    "date": meta.get("date", ""),
                    "query_category": meta.get("query_category", ""),
                    "chunk_index": chunk_index,
                    "source": "indian_kanoon",
                }
            ))
            chunk_index += 1

            # Overlap — keep last N words for context continuity
            overlap_text = " ".join(" ".join(current_chunk).split()[-overlap:])
            current_chunk = [overlap_text, sentence]
            current_len = len(overlap_text.split()) + sentence_len
        else:
            current_chunk.append(sentence)
            current_len += sentence_len

    # Don't forget the last chunk
    if current_chunk:
        chunks.append(Chunk(
            text=" ".join(current_chunk),
            metadata={
                "doc_id": meta.get("doc_id", ""),
                "title": meta.get("title", ""),
                "court": meta.get("court", ""),
                "date": meta.get("date", ""),
                "query_category": meta.get("query_category", ""),
                "chunk_index": chunk_index,
                "source": "indian_kanoon",
            }
        ))

    return chunks


def load_and_chunk_all(raw_dir: str = "data/raw") -> List[Chunk]:
    """
    Load all JSONs from raw dir and chunk them.
    Run this after kanoon_fetcher.py has populated data/raw/
    """
    raw_path = Path(raw_dir)
    all_chunks = []

    json_files = list(raw_path.glob("*.json"))
    print(f"[CHUNKER] Found {len(json_files)} documents")

    for filepath in json_files:
        with open(filepath, "r", encoding="utf-8") as f:
            doc = json.load(f)
        chunks = chunk_judgment(doc)
        all_chunks.extend(chunks)

    print(f"[CHUNKER] Total chunks created: {len(all_chunks)}")
    return all_chunks


if __name__ == "__main__":
    chunks = load_and_chunk_all()
    if chunks:
        print(f"\nSample chunk text (first 200 chars):")
        print(chunks[0].text[:200])
        print(f"\nSample chunk metadata:")
        print(chunks[0].metadata)
