"""
POST /api/brief  — FIR -> verified brief, steps streamed as server-sent events.
POST /api/audit  — pasted draft -> verdict per citation, steps streamed as SSE.

Event stream: `event: step` (trace events), then one `event: result`, or `event: error`.
"""

import asyncio
import json
import logging
import threading
from typing import AsyncIterator, Literal

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from backend.guards import check_rate, check_size, check_spend

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Brief and audit"])


class BriefRequest(BaseModel):
    fir_text: str = Field(min_length=40, max_length=20000)
    perspective: Literal["defense", "prosecution"] = "defense"


class AuditRequest(BaseModel):
    draft_text: str = Field(min_length=40, max_length=20000)


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def _stream_from_thread(work) -> AsyncIterator[str]:
    """Run blocking `work(emit)` in a thread and yield its events as SSE."""
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    def emit(kind, data):
        loop.call_soon_threadsafe(q.put_nowait, (kind, data))

    def run():
        try:
            emit("result", work(lambda ev: emit("step", ev)))
        except Exception as e:  # never leak tracebacks to clients
            logger.exception("request failed")
            emit("error", {"detail": f"internal error ({type(e).__name__})"})
        finally:
            emit("_done", None)

    threading.Thread(target=run, daemon=True).start()
    yield _sse("step", {"step": "start", "status": "ok", "detail": "request accepted"})
    while True:
        kind, data = await q.get()
        if kind == "_done":
            break
        yield _sse(kind, data)


async def _parse(request: Request, model):
    check_rate(request)
    body = await check_size(request)
    check_spend()
    try:
        return model.model_validate_json(body)
    except ValidationError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=[{"loc": x["loc"], "msg": x["msg"]} for x in e.errors()])


@router.post("/brief")
async def brief(request: Request):
    req = await _parse(request, BriefRequest)

    def work(emit):
        from core.pipeline import build_graph, initial_state
        final = {}
        for update in build_graph().stream(initial_state(req.fir_text, req.perspective), stream_mode="updates"):
            for _node, delta in update.items():
                final.update(delta)
                if delta.get("trace"):
                    emit(delta["trace"][-1])
        return {"brief": final.get("brief", {}), "claims": final.get("claims", []),
                "trace": final.get("trace", []), "error": final.get("error")}

    return StreamingResponse(_stream_from_thread(work), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/audit")
async def audit(request: Request):
    req = await _parse(request, AuditRequest)

    def work(emit):
        from core.audit import run_audit
        from core.pipeline import store
        return run_audit(req.draft_text, store(), on_event=emit)

    return StreamingResponse(_stream_from_thread(work), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
