"""
CourtroomAI — FastAPI Backend
AI co-pilot for Indian advocates.

Endpoints:
  POST /api/brief    — FIR -> verified brief (SSE)
  POST /api/audit    — pasted draft -> verdict per citation (SSE)
  POST /api/upload   — PDF upload + parsing
  GET  /api/samples  — synthetic sample FIRs for the demo
  GET  /api/health   — system health check
"""

import os
import time
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# Track server start time for uptime reporting
_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Pre-load heavy models on startup so first request isn't slow.
    This runs once when the server starts.
    """
    print("[SERVER] Starting CourtroomAI backend...")
    print("[SERVER] Pre-loading models (this takes ~30s on first run)...")

    # Pre-warm the retriever (loads embedding model + Chroma + BM25 index)
    try:
        from core.pipeline import _retrieval_models, store
        _retrieval_models()
        print(f"[SERVER] Models loaded. Judgments in store: {len(store())}")
    except Exception as e:
        print(f"[SERVER] Warning: Could not pre-load models: {e}")
        print("[SERVER] Models will load on first request instead.")

    yield  # Server is running

    print("[SERVER] Shutting down CourtroomAI backend.")


# ─────────────────────────────────────────────
# App initialization
# ─────────────────────────────────────────────
app = FastAPI(
    title="CourtroomAI",
    description=(
        "AI co-pilot for Indian advocates. Takes a FIR or legal notice as input, "
        "retrieves verified precedents from Indian Kanoon, identifies IPC sections, "
        "and generates a structured case strategy with citation verification."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — allow React frontend and Vercel deployments
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Include routers
# ─────────────────────────────────────────────
from backend.routers.brief import router as brief_router
from backend.routers.upload import router as upload_router

app.include_router(brief_router)
app.include_router(upload_router)


@app.get("/api/samples", tags=["Demo"])
async def samples():
    """Synthetic sample FIRs (fictional people) for the demo button."""
    from core.config import ROOT
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted((ROOT / "samples").glob("fir_*.txt"))}


# ─────────────────────────────────────────────
# Health check (inline — too simple for its own router)
# ─────────────────────────────────────────────
@app.get("/api/health", tags=["Health"])
async def health_check():
    """Health: vector count, judgment store size, configured model IDs, today's usage."""
    import chromadb
    from backend.guards import spend_today
    from core.config import settings
    from core.pipeline import store

    try:
        vectors = chromadb.PersistentClient(path=str(settings.chroma_dir)).get_collection("courtroom_judgments").count()
    except Exception:
        vectors = None
    return {
        "status": "ok" if vectors and len(store()) else "degraded",
        "vectors_in_db": vectors,
        "judgments_in_store": len(store()),
        "models": {"nano": settings.nano_model, "super": settings.super_model, "ultra": settings.ultra_model},
        "usage_today": spend_today(),
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


# ─────────────────────────────────────────────
# Root redirect
# ─────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    return {
        "app": "CourtroomAI",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }
