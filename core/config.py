"""
Runtime configuration. Every value comes from the environment; nothing about
providers or model IDs is hard-coded here.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
# Where the judgment library, search index and statute tables live. Defaults to ./data;
# on a host, point DATA_DIR at a mounted volume.
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data")))

REQUIRED_ENV = [
    "TOKEN_FACTORY_API_KEY",
    "TOKEN_FACTORY_BASE_URL",
    "NEMOTRON_NANO_MODEL",
    "NEMOTRON_SUPER_MODEL",
    "NEMOTRON_ULTRA_MODEL",
    "TAVILY_API_KEY",
]


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    base_url: str = field(default_factory=lambda: os.getenv("TOKEN_FACTORY_BASE_URL", ""))
    nano_model: str = field(default_factory=lambda: os.getenv("NEMOTRON_NANO_MODEL", ""))
    super_model: str = field(default_factory=lambda: os.getenv("NEMOTRON_SUPER_MODEL", ""))
    ultra_model: str = field(default_factory=lambda: os.getenv("NEMOTRON_ULTRA_MODEL", ""))

    llm_timeout_s: float = field(default_factory=lambda: _float("LLM_TIMEOUT_S", 90.0))
    llm_max_retries: int = field(default_factory=lambda: _int("LLM_MAX_RETRIES", 2))
    verify_concurrency: int = field(default_factory=lambda: _int("VERIFY_CONCURRENCY", 4))
    precedent_max_redrafts: int = 2

    # Judge context: send the whole judgment below this many characters,
    # otherwise a window around the quoted passage.
    judge_full_text_chars: int = field(default_factory=lambda: _int("JUDGE_FULL_TEXT_CHARS", 24000))
    judge_window_chars: int = field(default_factory=lambda: _int("JUDGE_WINDOW_CHARS", 6000))

    # Spend control. Prices are USD per 1M tokens and must be set from the
    # Token Factory pricing page; unset prices make cost tracking report None.
    daily_spend_cap_usd: float = field(default_factory=lambda: _float("DAILY_SPEND_CAP_USD", 3.0))

    # Tuned on the dev split only by eval/run_eval.py (eval/results/eval_20261028T025542Z.json,
    # max-of-two-query reranking: threshold 1.3651). All 9 dev cases are on topics the library
    # covers, so the tuner had no off-topic examples and set the threshold 1 below the lowest
    # dev score. Re-tune after the corpus or retrieval changes.
    abstain_rerank_threshold: float = field(default_factory=lambda: _float("ABSTAIN_RERANK_THRESHOLD", 1.3651))

    max_web_fetches: int = field(default_factory=lambda: _int("MAX_WEB_FETCHES", 5))
    retrieval_timeout_s: float = field(default_factory=lambda: _float("RETRIEVAL_TIMEOUT_S", 60.0))

    judgments_path: Path = DATA_DIR / "judgments" / "judgments.jsonl"
    statute_map_path: Path = DATA_DIR / "statutes" / "ipc_bns_map.csv"
    chroma_dir: Path = DATA_DIR / "chroma_db"
    prompts_dir: Path = ROOT / "prompts"
    logs_dir: Path = ROOT / "logs"


settings = Settings()
