"""
Embedder — converts chunks to vectors and stores in Chroma.
Uses BAAI/bge-base-en-v1.5 — free, strong on legal/technical English.
Run this AFTER chunker.py has produced chunks.
"""
import os
from pathlib import Path
from typing import List

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from ingestion.chunker import Chunk, load_and_chunk_all

CHROMA_DIR = "data/chroma_db"
COLLECTION_NAME = "courtroom_judgments"
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
BATCH_SIZE = 64  # embed in batches to avoid OOM

def get_chroma_collection():
    """Get or create Chroma collection."""
    client = chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(anonymized_telemetry=False)
    )
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    return collection
def embed_and_store(chunks: List[Chunk]):
    """
    Embed all chunks and store in Chroma with metadata.
    Skips chunks already in the DB (idempotent — safe to re-run).
    """
    print(f"[EMBEDDER] Loading model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)

    collection = get_chroma_collection()
    existing_ids = set(collection.get()["ids"])
    print(f"[EMBEDDER] Existing vectors in DB: {len(existing_ids)}")

    # Filter out already-embedded chunks
    new_chunks = []
    for i, chunk in enumerate(chunks):
        chunk_id = f"{chunk.metadata['doc_id']}_chunk_{chunk.metadata['chunk_index']}"
        if chunk_id not in existing_ids:
            new_chunks.append((chunk_id, chunk))

    if not new_chunks:
        print("[EMBEDDER] Nothing new to embed. DB is up to date.")
        return

    print(f"[EMBEDDER] Embedding {len(new_chunks)} new chunks...")

    # Batch processing
    for batch_start in range(0, len(new_chunks), BATCH_SIZE):
        batch = new_chunks[batch_start: batch_start + BATCH_SIZE]
        ids = [item[0] for item in batch]
        texts = [item[1].text for item in batch]
        metadatas = [item[1].metadata for item in batch]

        # BGE models need this prefix for retrieval tasks
        texts_with_prefix = [f"Represent this legal document: {t}" for t in texts]
        embeddings = model.encode(texts_with_prefix, show_progress_bar=True).tolist()

        collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        print(f"  [BATCH] Stored {batch_start + len(batch)}/{len(new_chunks)}")

    print(f"[EMBEDDER] Done. Total vectors in DB: {collection.count()}")

def run_full_pipeline():
    """One command to chunk everything and embed it."""
    chunks = load_and_chunk_all()
    embed_and_store(chunks)

if __name__ == "__main__":
    run_full_pipeline()
