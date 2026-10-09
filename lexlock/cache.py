"""Дисковый кэш результатов LLM по хешу содержимого.

Повторный анализ того же документа мгновенный. Каталог — <workspace>/.lexlock_cache.
Отключается переменной окружения LEXLOCK_CACHE=0. Ошибки кэша никогда не ломают
основной сценарий: при любой проблеме он просто работает без кэша.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def enabled() -> bool:
    raw = os.environ.get("LEXLOCK_CACHE", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def cache_dir(workspace: str | Path) -> Path:
    return Path(workspace) / ".lexlock_cache"


def make_key(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def get(workspace: str | Path, key: str) -> dict | None:
    if not enabled():
        return None
    try:
        path = cache_dir(workspace) / f"{key}.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, ValueError):
        return None
    return None


def put(workspace: str | Path, key: str, value: dict) -> None:
    if not enabled():
        return
    try:
        folder = cache_dir(workspace)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / f".{key}.tmp"
        tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        tmp.replace(folder / f"{key}.json")
    except OSError:
        pass
