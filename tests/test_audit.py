"""Тесты журнала аудита с защитой от подделки (lexlock.audit)."""

from __future__ import annotations

import json

from lexlock import audit


def test_record_and_verify_clean(tmp_path):
    audit.record("tool", {"tool": "list_files"}, root=tmp_path)
    audit.record("tool", {"tool": "read_document"}, root=tmp_path)
    result = audit.verify(root=tmp_path)
    assert result["ok"] is True
    assert result["entries"] == 2


def test_verify_detects_tampering(tmp_path):
    audit.record("tool", {"tool": "list_files"}, root=tmp_path)
    audit.record("tool", {"tool": "read_document"}, root=tmp_path)
    path = audit.audit_dir(tmp_path) / audit.AUDIT_FILE
    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["action"] = "evil"
    lines[0] = json.dumps(first, ensure_ascii=False, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = audit.verify(root=tmp_path)
    assert result["ok"] is False
    assert result["broken_at"] == 1


def test_verify_empty_dir(tmp_path):
    result = audit.verify(root=tmp_path)
    assert result["ok"] is True
    assert result["entries"] == 0


def test_record_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("LEXLOCK_AUDIT", "0")
    assert audit.record("tool", {"tool": "x"}, root=tmp_path) is None
    assert audit.verify(root=tmp_path)["entries"] == 0
