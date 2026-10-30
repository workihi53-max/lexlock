#!/usr/bin/env python3
"""Создаёт подписанный пакет обновления ``*.lexlock`` (инструмент вендора).

Закрытый ключ есть только у вендора. Пакет проверяется на стороне клиента
модулем ``lexlock/updater.py`` (офлайн, по встроенному открытому ключу).

Примеры:
    python scripts/make_update.py --gen-key --key update_key.pem
    python scripts/make_update.py --private-key update_key.pem --version 0.2.4 \\
        --out dist/lexlock-0.2.4.lexlock --note "исправления установщика"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Каталоги/файлы, которые попадают в обновление (по белому списку).
INCLUDE = ["lexlock", "app", "scripts", "templates", "pyproject.toml"]
SKIP = {"__pycache__"}


def _crypto():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    return Ed25519PrivateKey, serialization


def _collect(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for entry in INCLUDE:
        p = root / entry
        if p.is_file():
            files[entry] = p.read_bytes()
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if not f.is_file():
                    continue
                if any(part in SKIP for part in f.parts):
                    continue
                if f.suffix in {".pyc", ".pyo"}:
                    continue
                rel = f.relative_to(root).as_posix()
                files[rel] = f.read_bytes()
    return files


def gen_key(key_path: str) -> int:
    Ed25519PrivateKey, serialization = _crypto()
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    Path(key_path).write_bytes(pem)
    import base64

    pub = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    print(f"Закрытый ключ сохранён: {key_path}")
    print("Открытый ключ (вставьте в lexlock/updater.py PUBLIC_KEY_B64):")
    print(base64.b64encode(pub).decode())
    return 0


def build(private_key_path: str, version: str, out: str, note: str) -> int:
    Ed25519PrivateKey, serialization = _crypto()
    try:
        key = serialization.load_pem_private_key(
            Path(private_key_path).read_bytes(), password=None
        )
    except (OSError, ValueError) as exc:
        print(f"Не удалось прочитать закрытый ключ: {exc}", file=sys.stderr)
        return 1

    files = _collect(ROOT)
    if not files:
        print("Нечего упаковывать: белый список INCLUDE пуст.", file=sys.stderr)
        return 1

    manifest = {
        "version": version,
        "notes": note,
        "files": {rel: hashlib.sha256(data).hexdigest() for rel, data in files.items()},
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    signature = key.sign(manifest_bytes)

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest_bytes)
        zf.writestr("signature", signature)
        for rel, data in files.items():
            zf.writestr("payload/" + rel, data)

    print(f"Пакет создан: {out_path}")
    print(f"Версия: {version} | файлов: {len(files)} | размер: {out_path.stat().st_size} байт")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Подписанный пакет обновления .lexlock")
    ap.add_argument("--gen-key", action="store_true", help="сгенерировать пару ключей")
    ap.add_argument("--key", default="update_key.pem", help="файл ключа (для --gen-key)")
    ap.add_argument("--private-key", help="закрытый ключ вендора (PEM)")
    ap.add_argument("--version", help="версия обновления")
    ap.add_argument("--out", help="путь к .lexlock")
    ap.add_argument("--note", default="", help="описание изменений")
    args = ap.parse_args()

    if args.gen_key:
        return gen_key(args.key)

    missing = [n for n, v in (("--private-key", args.private_key),
                              ("--version", args.version),
                              ("--out", args.out)) if not v]
    if missing:
        ap.error("нужны аргументы: " + ", ".join(missing))
    return build(args.private_key, args.version, args.out, args.note)


if __name__ == "__main__":
    sys.exit(main())
