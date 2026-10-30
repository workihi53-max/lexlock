"""Тесты офлайн-обновлений (lexlock.updater)."""

from __future__ import annotations

import base64
import hashlib
import json
import zipfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from lexlock import updater


@pytest.fixture
def keypair(monkeypatch):
    """Свежая пара ключей; публичный ключ подставляется в updater."""
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    monkeypatch.setattr(updater, "PUBLIC_KEY_B64", base64.b64encode(pub).decode())
    return key


def _make_bundle(path, files: dict[str, bytes], key, version: str = "0.2.4"):
    manifest = {
        "version": version,
        "notes": "",
        "files": {rel: hashlib.sha256(data).hexdigest() for rel, data in files.items()},
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    signature = key.sign(manifest_bytes)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest_bytes)
        zf.writestr("signature", signature)
        for rel, data in files.items():
            zf.writestr("payload/" + rel, data)
    return path


def test_verify_bundle_ok(tmp_path, keypair):
    bundle = _make_bundle(tmp_path / "u.lexlock", {"lexlock/agent.py": b"new"}, keypair)
    manifest = updater.verify_bundle(bundle)
    assert manifest["version"] == "0.2.4"
    assert manifest["files"]["lexlock/agent.py"] == hashlib.sha256(b"new").hexdigest()


def test_verify_bundle_wrong_signature(tmp_path, keypair):
    other = Ed25519PrivateKey.generate()
    bundle = _make_bundle(tmp_path / "u.lexlock", {"a.txt": b"x"}, other)
    with pytest.raises(updater.UpdaterError):
        updater.verify_bundle(bundle)


def test_verify_bundle_tampered_file(tmp_path, keypair):
    # Хеш в манифесте посчитан для "orig", а в payload лежит "tampered".
    manifest = {"version": "0.2.4", "files": {"a.txt": hashlib.sha256(b"orig").hexdigest()}}
    manifest_bytes = json.dumps(manifest).encode("utf-8")
    signature = keypair.sign(manifest_bytes)
    bundle = tmp_path / "bad.lexlock"
    with zipfile.ZipFile(bundle, "w") as zf:
        zf.writestr("manifest.json", manifest_bytes)
        zf.writestr("signature", signature)
        zf.writestr("payload/a.txt", b"tampered")
    with pytest.raises(updater.UpdaterError):
        updater.verify_bundle(bundle)


def test_verify_bundle_path_traversal(tmp_path, keypair):
    manifest = {"version": "0.2.4", "files": {"../evil.py": "abc"}}
    manifest_bytes = json.dumps(manifest).encode("utf-8")
    signature = keypair.sign(manifest_bytes)
    bundle = tmp_path / "traversal.lexlock"
    with zipfile.ZipFile(bundle, "w") as zf:
        zf.writestr("manifest.json", manifest_bytes)
        zf.writestr("signature", signature)
        zf.writestr("payload/../evil.py", b"x")
    with pytest.raises(updater.UpdaterError):
        updater.verify_bundle(bundle)


def test_apply_bundle_with_backup(tmp_path, keypair):
    root = tmp_path / "root"
    (root / "lexlock").mkdir(parents=True)
    (root / "lexlock" / "agent.py").write_text("OLD", encoding="utf-8")
    bundle = _make_bundle(
        tmp_path / "u.lexlock", {"lexlock/agent.py": b"NEW"}, keypair, version="0.2.4"
    )
    result = updater.apply_bundle(bundle, root)
    assert (root / "lexlock" / "agent.py").read_bytes() == b"NEW"
    backup = root / ".lexlock_backup" / "0.2.4" / "lexlock" / "agent.py"
    assert backup.read_bytes() == b"OLD"
    assert result["version"] == "0.2.4"


def test_apply_bundle_same_version_rejected(tmp_path, keypair):
    root = tmp_path / "root"
    root.mkdir()
    bundle = _make_bundle(tmp_path / "u.lexlock", {"a.txt": b"x"}, keypair, version="0.2.4")
    updater.apply_bundle(bundle, root)
    with pytest.raises(updater.UpdaterError):
        updater.apply_bundle(bundle, root)
