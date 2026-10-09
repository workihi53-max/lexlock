"""Конфигурация приложения из переменных окружения."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Корень репозитория и папка шаблонов (нужны сценариям и инструментам).
REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "templates"

DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_PORT = 8765
DEFAULT_MAX_CTX = 12000


@dataclass(frozen=True)
class Config:
    model: str
    ollama_url: str
    workspace: Path
    port: int
    offline: bool
    max_ctx_chars: int


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> Config:
    """Читает настройки из окружения, подставляя значения по умолчанию."""
    model = os.environ.get("LEXLOCK_MODEL", DEFAULT_MODEL)
    ollama_url = os.environ.get("LEXLOCK_OLLAMA_URL", DEFAULT_OLLAMA_URL)
    workspace = Path(os.environ.get("LEXLOCK_WORKSPACE", REPO_ROOT / "workspace"))
    port = int(os.environ.get("LEXLOCK_PORT", DEFAULT_PORT))
    offline = _env_bool("LEXLOCK_OFFLINE", True)
    max_ctx_chars = int(os.environ.get("LEXLOCK_MAX_CTX", DEFAULT_MAX_CTX))
    return Config(
        model=model,
        ollama_url=ollama_url,
        workspace=workspace,
        port=port,
        offline=offline,
        max_ctx_chars=max_ctx_chars,
    )
