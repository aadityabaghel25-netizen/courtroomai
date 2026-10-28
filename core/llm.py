"""
Token Factory LLM layer: one OpenAI-compatible client, a role-based model router,
timeouts, retries with backoff, Ultra -> Super fallback for judging, per-call
token/latency logging, and validated JSON output with at most one repair.

Roles:
  extract  -> Nano   (FIR intake, citation extraction)   temperature 0
  draft    -> Super  (claim drafting)
  judge    -> Ultra  (precedent judge), falls back to Super  temperature 0
"""

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from core.config import settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

ROLE_TEMPERATURE = {"extract": 0.0, "draft": 0.2, "judge": 0.0}

# Extra request fields per role. Nano with thinking on spent its whole budget on
# reasoning and returned no content (42-90 s, finish=length); with
# chat_template_kwargs.enable_thinking=False it answered the same intake prompt in
# 2.0 s / 494 tokens (live test 2026-10-27, see FEEDBACK.md). The judge keeps reasoning.
ROLE_EXTRA_BODY = {"extract": {"chat_template_kwargs": {"enable_thinking": False}}}


class LLMError(Exception):
    """Any failure to obtain a validated model output. Callers must fail closed."""


@dataclass
class CallRecord:
    role: str
    model: str
    ok: bool
    latency_s: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    fallback_from: Optional[str] = None
    error: Optional[str] = None
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class UsageLog:
    """Thread-safe call log. Appends JSONL to logs/llm_calls.jsonl for the spend cap."""

    def __init__(self, persist: bool = True):
        self._lock = threading.Lock()
        self.persist = persist
        self.records: List[CallRecord] = []

    def add(self, rec: CallRecord):
        with self._lock:
            self.records.append(rec)
            if not self.persist:
                return
            try:
                settings.logs_dir.mkdir(parents=True, exist_ok=True)
                with open(settings.logs_dir / "llm_calls.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec.__dict__) + "\n")
            except OSError as e:  # logging must never break a request
                logger.warning("could not write usage log: %s", e)

    def tokens_today(self) -> Dict[str, int]:
        """Sum tokens per model for today (UTC) from the persisted log."""
        totals: Dict[str, int] = {}
        path = settings.logs_dir / "llm_calls.jsonl"
        if not path.exists():
            return totals
        today = date.today().isoformat()
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("ts", "").startswith(today):
                    totals[r["model"]] = totals.get(r["model"], 0) + r.get("prompt_tokens", 0) + r.get("completion_tokens", 0)
        return totals


usage_log = UsageLog()


def extract_json(content: str) -> Any:
    """Parse JSON from a model reply: raw, fenced, or the outermost {...}. Raises ValueError."""
    if not content or not content.strip():
        raise ValueError("empty model reply")
    s = content.strip()
    # Reasoning models may emit a <think> block before the answer.
    s = re.sub(r"<think>[\s\S]*?</think>", "", s).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", s)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    a, b = s.find("{"), s.rfind("}")
    if a != -1 and b > a:
        try:
            return json.loads(s[a:b + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"no valid JSON in model reply: {s[:160]!r}")


def parse_validated(content: str, schema: Type[T]) -> T:
    """JSON parse + pydantic validation. Raises ValueError on either failure."""
    data = extract_json(content)
    try:
        return schema.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"schema validation failed: {e.errors()[:3]}") from e


class TokenFactoryLLM:
    def __init__(self, client=None, log: Optional[UsageLog] = None):
        self._client = client  # injected in tests; created lazily otherwise
        # An injected (test) client never writes to the persisted spend log.
        self.log = log or (UsageLog(persist=False) if client is not None else usage_log)
        self.models = {
            "extract": settings.nano_model,
            "draft": settings.super_model,
            "judge": settings.ultra_model,
        }

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI  # OpenAI-compatible SDK pointed at Token Factory
            import os
            self._client = OpenAI(
                base_url=settings.base_url,
                api_key=os.getenv("TOKEN_FACTORY_API_KEY"),
                timeout=settings.llm_timeout_s,
                max_retries=0,  # retries handled here so they are logged
            )
        return self._client

    def _call(self, role: str, model: str, messages, temperature: float, max_tokens: int,
              response_format: Optional[dict], fallback_from: Optional[str] = None) -> str:
        last_err: Optional[Exception] = None
        for attempt in range(settings.llm_max_retries + 1):
            t0 = time.time()
            try:
                kwargs = dict(model=model, messages=messages, temperature=temperature, max_tokens=max_tokens)
                if role in ROLE_EXTRA_BODY:
                    kwargs["extra_body"] = ROLE_EXTRA_BODY[role]
                if response_format:
                    kwargs["response_format"] = response_format
                resp = self.client.chat.completions.create(**kwargs)
                usage = getattr(resp, "usage", None)
                self.log.add(CallRecord(
                    role=role, model=model, ok=True, latency_s=round(time.time() - t0, 3),
                    prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    fallback_from=fallback_from,
                ))
                return resp.choices[0].message.content or ""
            except Exception as e:  # network, rate limit, 5xx, timeout
                last_err = e
                self.log.add(CallRecord(role=role, model=model, ok=False,
                                         latency_s=round(time.time() - t0, 3),
                                         fallback_from=fallback_from, error=f"{type(e).__name__}: {str(e)[:300]}"))
                if attempt < settings.llm_max_retries:
                    time.sleep(1.5 * (2 ** attempt))
        raise LLMError(f"{model} failed after {settings.llm_max_retries + 1} attempts: {last_err}")

    def complete(self, role: str, messages, max_tokens: int = 2048, response_format: Optional[dict] = None,
                 temperature: Optional[float] = None) -> Dict[str, Any]:
        """Return {"content", "model", "fallback"}; raises LLMError when every route fails."""
        temp = ROLE_TEMPERATURE[role] if temperature is None else temperature
        model = self.models[role]
        try:
            return {"content": self._call(role, model, messages, temp, max_tokens, response_format),
                    "model": model, "fallback": None}
        except LLMError:
            if role not in ("judge", "extract"):
                raise
            # Judge: Ultra -> Super. Extract: Nano -> Super. The fallback is recorded in the output.
            fb = self.models["draft"]
            logger.warning("%s model %s failed; falling back to %s", role, model, fb)
            return {"content": self._call(role, fb, messages, temp, max_tokens, response_format, fallback_from=model),
                    "model": fb, "fallback": f"{model} -> {fb}"}

    def structured(self, role: str, messages, schema: Type[T], max_tokens: int = 2048,
                   temperature: Optional[float] = None) -> Dict[str, Any]:
        """
        Validated structured output. Token Factory accepts response_format
        json_schema on all three Nemotron models (scripts/probe_structured.py),
        so the pydantic schema is sent as a constraint; the reply is still
        validated with pydantic, repaired at most once, then LLMError
        (callers turn that into "unverified").
        Returns {"value": schema instance, "model", "fallback", "repaired"}.
        """
        rf = {"type": "json_schema",
              "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()}}
        out = self.complete(role, messages, max_tokens=max_tokens, response_format=rf, temperature=temperature)
        try:
            return {"value": parse_validated(out["content"], schema), "model": out["model"],
                    "fallback": out["fallback"], "repaired": False}
        except ValueError as first:
            repair = messages + [
                {"role": "assistant", "content": out["content"][:4000]},
                {"role": "user", "content": f"Your reply was invalid ({first}). Reply again with only a JSON object matching the requested schema."},
            ]
            out2 = self.complete(role, repair, max_tokens=max_tokens, response_format=rf, temperature=temperature)
            try:
                return {"value": parse_validated(out2["content"], schema), "model": out2["model"],
                        "fallback": out2["fallback"] or out["fallback"], "repaired": True}
            except ValueError as second:
                if role == "extract" and out2["model"] != self.models["draft"]:
                    # Nano produced unusable JSON twice: one attempt with Super, recorded as a fallback.
                    fb = self.models["draft"]
                    logger.warning("extract output invalid twice on %s; falling back to %s", out2["model"], fb)
                    content = self._call(role, fb, messages, ROLE_TEMPERATURE[role] if temperature is None else temperature,
                                         max_tokens, rf, fallback_from=out2["model"])
                    try:
                        return {"value": parse_validated(content, schema), "model": fb,
                                "fallback": f"{out2['model']} -> {fb}", "repaired": True}
                    except ValueError as third:
                        raise LLMError(f"invalid structured output after repair and fallback: {third}") from third
                raise LLMError(f"invalid structured output after one repair: {second}") from second


_llm: Optional[TokenFactoryLLM] = None


def get_llm() -> TokenFactoryLLM:
    global _llm
    if _llm is None:
        _llm = TokenFactoryLLM()
    return _llm
