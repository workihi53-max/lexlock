"""Журнал аудита с защитой от подделки (hash-цепочка).

Отвечает на критику «действительно ли вы обеспечиваете кибербезопасность»:
каждое действие агента/сценария пишется в append-only журнал, каждая запись
содержит хеш предыдущей. Любую правку/удаление строки можно обнаружить функцией
``verify()`` — цепочка хешей «разорвётся».

Журнал — это обычный JSONL (``<workspace>/.lexlock_audit/audit.jsonl``), без сети
и внешних сервисов. Включён по умолчанию, отключается ``LEXLOCK_AUDIT=0``.
Сбой записи никогда не ломает основной сценарий.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from .config import load_config

AUDIT_DIR = ".lexlock_audit"
AUDIT_FILE = "audit.jsonl"


def enabled() -> bool:
    raw = os.environ.get("LEXLOCK_AUDIT", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def audit_dir(root: str | Path | None = None) -> Path:
    base = Path(root) if root is not None else load_config().workspace
    return base / AUDIT_DIR


def _canonical(entry: dict) -> bytes:
    return json.dumps(
        entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _last_hash(path: Path) -> str:
    """Хеш последней записи (для связывания цепочки). Битая строка — пусто."""
    try:
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not lines:
            return ""
        return json.loads(lines[-1]).get("hash", "")
    except (OSError, ValueError):
        return ""


def record(action: str, detail: dict | None = None, root: str | Path | None = None) -> dict | None:
    """Добавляет запись в журнал. Возвращает запись или None, если журнал выключен."""
    if not enabled():
        return None
    folder = audit_dir(root)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / AUDIT_FILE
        prev = _last_hash(path)
        entry_without_hash = {
            "seq": _next_seq(path),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "action": action,
            "detail": detail or {},
            "prev": prev,
        }
        digest = _sha256(_canonical(entry_without_hash))
        entry = {**entry_without_hash, "hash": digest}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        return entry
    except OSError:
        return None


def _next_seq(path: Path) -> int:
    try:
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except OSError:
        return 1
    return len(lines) + 1


def entries(root: str | Path | None = None) -> list[dict]:
    """Все записи журнала (для чтения)."""
    path = audit_dir(root) / AUDIT_FILE
    try:
        out: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out
    except (OSError, ValueError):
        return []


def verify(root: str | Path | None = None) -> dict:
    """Проверяет целостность журнала. Возвращает {ok, broken_at, entries}."""
    path = audit_dir(root) / AUDIT_FILE
    result: dict = {"ok": True, "broken_at": None, "entries": 0}
    if not path.is_file():
        return result
    prev = ""
    seq = 0
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            result.update(ok=False, broken_at=idx)
            return result
        stored_hash = entry.pop("hash", None)
        if not stored_hash or _sha256(_canonical(entry)) != stored_hash:
            result.update(ok=False, broken_at=idx)
            return result
        if entry.get("prev") != prev:
            result.update(ok=False, broken_at=idx)
            return result
        prev = stored_hash
        seq = idx
    result["entries"] = seq
    return result
