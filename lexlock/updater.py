"""Офлайн-обновления: проверка подписи и применение подписанного пакета.

Ответ на главный вопрос критики — «как доставлять обновления, если агент не имеет
доступа в сеть». Схема «air-gapped» (безсетевой канал), как в кошельках/HSM:

    * приложение и модель НИКОГДА не выходят в сеть (enforce_offline патчит socket);
    * обновление — это ПОДПИСАННЫЙ пакет-файл ``*.lexlock``, который пользователь
      скачивает сам (браузер, флешка, корпоративный портал) — вне нашего приложения;
    * проверка подписи и применение идут полностью офлайн по встроенному ОТКРЫТОМУ
      ключу. Закрытый ключ (Ed25519) хранится только у вендора и в пакет не попадает.

Формат пакета (обычный zip-архив):
    manifest.json  — {"version": "...", "notes": "...", "files": {"путь": "sha256", ...}}
    signature      — Ed25519-подпись над байтами manifest.json (raw)
    payload/путь   — файлы для замены, пути относительно корня проекта

Проверка двухступенчатая: сначала подпись manifest.json, затем sha256 каждого файла
сверяется с манифестом. Только после этого файлы применяются, а старые версии
сохраняются в ``.lexlock_backup/<version>/``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

# Открытый ключ вендора (Ed25519, 32 байта, base64). Закрытый ключ — только у вендора.
PUBLIC_KEY_B64 = "wHdUbqtIQUcrlGu5suNeAUCAWdCr8cuuU2XbdQMltXM="

MANIFEST_NAME = "manifest.json"
SIGNATURE_NAME = "signature"
PAYLOAD_PREFIX = "payload/"
BACKUP_DIR = ".lexlock_backup"
STATE_FILE = ".lexlock_update"


class UpdaterError(RuntimeError):
    """Пакет обновления не прошёл проверку или не может быть применён."""


def public_key_bytes() -> bytes:
    return base64.b64decode(PUBLIC_KEY_B64)


def _ed25519_class():
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except ImportError as exc:  # pragma: no cover — зависит от окружения
        raise UpdaterError(
            "Не установлена библиотека cryptography — обновите зависимости"
        ) from exc
    return Ed25519PublicKey


def verify_signature(message: bytes, signature: bytes) -> bool:
    """Проверяет Ed25519-подпись встроенным открытым ключом. Ошибки — False."""
    try:
        key = _ed25519_class().from_public_bytes(public_key_bytes())
        key.verify(signature, message)
        return True
    except Exception:  # noqa: BLE001 — неверная подпись/битый ключ
        return False


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_relative(path: str) -> str:
    """Только относительный путь без '..' и абсолютных маршрутов."""
    p = Path(path)
    if p.is_absolute() or ".." in p.parts or path.startswith("/"):
        raise UpdaterError(f"Недопустимый путь в манифесте: {path!r}")
    return p.as_posix()


def read_bundle(path: str | Path) -> tuple[bytes, bytes, dict]:
    """Возвращает (manifest_bytes, signature_bytes, manifest_dict)."""
    try:
        with zipfile.ZipFile(path) as zf:
            manifest_bytes = zf.read(MANIFEST_NAME)
            signature_bytes = zf.read(SIGNATURE_NAME)
            manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise UpdaterError(f"Не удалось прочитать пакет обновления: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        raise UpdaterError("Манифест повреждён: отсутствует поле files")
    return manifest_bytes, signature_bytes, manifest


def verify_bundle(path: str | Path) -> dict:
    """Проверяет подпись манифеста и sha256 всех файлов. Возвращает манифест."""
    manifest_bytes, signature_bytes, manifest = read_bundle(path)

    if not verify_signature(manifest_bytes, signature_bytes):
        raise UpdaterError("Подпись пакета недействительна — обновление отклонено")

    files: dict[str, str] = manifest["files"]
    if not files:
        raise UpdaterError("Манифест пуст: нет файлов для обновления")

    try:
        with zipfile.ZipFile(path) as zf:
            for rel, expected_hash in files.items():
                safe = _safe_relative(rel)
                data = zf.read(PAYLOAD_PREFIX + safe)
                if sha256(data) != expected_hash:
                    raise UpdaterError(f"Контрольная сумма не совпала: {rel}")
    except UpdaterError:
        raise
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise UpdaterError(f"Пакет обновления повреждён: {exc}") from exc

    return manifest


def current_version(root: str | Path) -> str | None:
    """Читает применённую версию из служебного файла, если он есть."""
    state = Path(root) / STATE_FILE
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
        return data.get("version") if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def apply_bundle(path: str | Path, root: str | Path) -> dict:
    """Проверяет пакет и применяет его к корню проекта. Старые файлы — в backup."""
    manifest = verify_bundle(path)
    version = str(manifest.get("version") or "unknown")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)

    if version == current_version(root):
        raise UpdaterError(f"Версия {version} уже установлена")

    backup = root / BACKUP_DIR / version
    backup.mkdir(parents=True, exist_ok=True)

    applied: list[str] = []
    with zipfile.ZipFile(path) as zf:
        for rel in manifest["files"]:
            safe = _safe_relative(rel)
            target = root / safe
            if target.exists():
                dest = backup / safe
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, dest)
            target.parent.mkdir(parents=True, exist_ok=True)
            data = zf.read(PAYLOAD_PREFIX + safe)
            target.write_bytes(data)
            applied.append(safe)

    (root / STATE_FILE).write_text(
        json.dumps({"version": version, "files": applied}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "version": version,
        "notes": manifest.get("notes", ""),
        "applied": applied,
        "backup": str(backup),
    }
