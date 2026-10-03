"""Тесты веб-слоя: без Ollama, функции vanya замоканы через monkeypatch."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.server as server


class FakeLLM:
    def __init__(self, config=None, timeout=300.0):
        pass

    def health(self):
        return {"ok": False, "model": "qwen2.5:3b", "installed": False,
                "error": "Ollama недоступна"}


class FakeEvent:
    def __init__(self, kind, data):
        self.kind = kind
        self.data = data


def make_config(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        model="qwen2.5:3b",
        ollama_url="http://127.0.0.1:11434",
        workspace=tmp_path / "workspace",
        port=8765,
        offline=False,
        max_ctx_chars=12000,
    )


@pytest.fixture
def cfg(tmp_path):
    return make_config(tmp_path)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server.vanya_llm, "LLM", FakeLLM)
    monkeypatch.setattr(server.vanya_offline, "enforce_offline", lambda: None)
    app = server.create_app(make_config(tmp_path))
    with TestClient(app) as c:
        yield c


def fake_scenarios(**fns) -> SimpleNamespace:
    base = {
        "fill_contract": lambda src, out_name=None: {"ok": True},
        "find_risks": lambda filename: {"ok": True, "summary": "", "risks": []},
        "ask": lambda filename, question: {"ok": True, "answer": ""},
    }
    base.update(fns)
    return SimpleNamespace(**base)


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


# --- статика и health ----------------------------------------------------------

def test_root_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Ваня" in r.text


def test_static_file_served(client):
    r = client.get("/static/index.html")
    assert r.status_code == 200
    assert "Офлайн-режим" in r.text


def test_health_reports_ollama_down(client, cfg):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["ollama"] is False
    assert data["model"] == "qwen2.5:3b"
    assert data["model_installed"] is False
    assert data["offline"] is False
    assert data["workspace"] == str(cfg.workspace)


# --- файлы ----------------------------------------------------------------------

def test_upload_and_list(client, cfg):
    files = [("files", ("a.txt", b"hello", "text/plain")),
             ("files", ("b.txt", b"world", "text/plain"))]
    r = client.post("/api/upload", files=files)
    assert r.status_code == 200
    assert set(r.json()["saved"]) == {"a.txt", "b.txt"}
    assert (cfg.workspace / "a.txt").read_bytes() == b"hello"

    r = client.get("/api/files")
    assert r.status_code == 200
    names = {f["name"] for f in r.json()["files"]}
    assert {"a.txt", "b.txt"} <= names


def test_upload_sanitizes_traversal_name(client, cfg, tmp_path):
    r = client.post("/api/upload",
                    files=[("files", ("../../evil.txt", b"x", "text/plain"))])
    assert r.status_code == 200
    assert r.json()["saved"] == ["evil.txt"]
    assert (cfg.workspace / "evil.txt").exists()
    assert not (tmp_path / "evil.txt").exists()


def test_upload_missing_field_is_rejected(client):
    r = client.post("/api/upload")
    assert r.status_code == 422


def test_upload_too_large_is_413_and_not_saved(client, cfg, monkeypatch):
    monkeypatch.setattr(server, "MAX_UPLOAD_BYTES", 5)
    r = client.post("/api/upload",
                    files=[("files", ("big.txt", b"123456", "text/plain"))])
    assert r.status_code == 413
    assert "big.txt" in r.json()["detail"]
    assert not (cfg.workspace / "big.txt").exists()


def test_download_existing_file(client, cfg):
    (cfg.workspace / "doc.txt").write_text("содержимое", encoding="utf-8")
    r = client.get("/api/download/doc.txt")
    assert r.status_code == 200
    assert r.content.decode("utf-8") == "содержимое"


def test_download_missing_file_404(client):
    r = client.get("/api/download/нет.txt")
    assert r.status_code == 404
    assert "не найден" in r.json()["detail"]


@pytest.mark.parametrize("name", [
    "..",
    ".",
    "../etc/passwd",
    "a/b",
    "..\\..\\windows\\win.ini",
    "/etc/passwd",
    "",
])
def test_download_traversal_rejected(client, name):
    r = client.get("/api/download/" + name.replace("\\", "%5C").replace("/", "%2F")
                   if ("/" in name or "\\" in name) else "/api/download/" + name)
    assert r.status_code in (400, 404)


def test_download_symlink_rejected(client, cfg, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("секрет", encoding="utf-8")
    (cfg.workspace / "link.txt").symlink_to(outside)
    r = client.get("/api/download/link.txt")
    assert r.status_code == 400
    assert "символьн" in r.json()["detail"]


def test_scenario_rejects_traversal(client, monkeypatch):
    monkeypatch.setattr(server, "vanya_scenarios", fake_scenarios())
    for url, body in [
        ("/api/scenario/fill", {"filename": "../../etc/passwd"}),
        ("/api/scenario/risks", {"filename": "../x"}),
        ("/api/scenario/export_risks", {"filename": "../x"}),
        ("/api/scenario/checklist", {"filename": "../x"}),
        ("/api/scenario/ask", {"filename": "/etc/passwd", "question": "что тут?"}),
    ]:
        r = client.post(url, json=body)
        assert r.status_code == 400
        assert isinstance(r.json()["detail"], str)


# --- сценарии --------------------------------------------------------------------

def test_scenario_fill_returns_download_name(client, monkeypatch):
    monkeypatch.setattr(server, "vanya_scenarios", fake_scenarios(
        fill_contract=lambda src, out_name=None: {
            "ok": True, "out_path": "workspace/dogovor_1.docx",
            "fields": {"fio": "Иванов Иван Иванович"},
            "missing": ["inn"], "log": ["шаблон заполнен"],
        }))
    r = client.post("/api/scenario/fill", json={"filename": "a.txt"})
    assert r.status_code == 200
    data = r.json()
    assert data["missing"] == ["inn"]
    assert data["download_name"] == "dogovor_1.docx"


def test_scenario_fill_not_ok_is_400(client, monkeypatch):
    monkeypatch.setattr(server, "vanya_scenarios", fake_scenarios(
        fill_contract=lambda src, out_name=None: {"ok": False, "error": "нет шаблона"}))
    r = client.post("/api/scenario/fill", json={"filename": "a.txt"})
    assert r.status_code == 400
    assert "нет шаблона" in r.json()["detail"]


def test_scenario_fill_package_mode_without_filename(client, monkeypatch):
    captured = {}

    def fake_fill(source_filename=None, out_name=None):
        captured["source"] = source_filename
        return {"ok": True, "out_path": "workspace/paket_dogovor.docx",
                "fields": {"fio": "Иванов Иван Иванович"}, "missing": [],
                "package_mode": True, "sources": ["a.txt", "b.txt"],
                "log": ["режим пакета"]}

    monkeypatch.setattr(server, "vanya_scenarios",
                        fake_scenarios(fill_contract=fake_fill))

    r = client.post("/api/scenario/fill", json={})
    assert r.status_code == 200
    assert captured["source"] in (None, "")
    data = r.json()
    assert data["package_mode"] is True
    assert data["sources"] == ["a.txt", "b.txt"]
    assert data["download_name"] == "paket_dogovor.docx"

    r2 = client.post("/api/scenario/fill", json={"filename": ""})
    assert r2.status_code == 200
    assert captured["source"] in (None, "")


def test_scenario_fill_rejects_traversal(client, monkeypatch):
    monkeypatch.setattr(server, "vanya_scenarios", fake_scenarios())
    r = client.post("/api/scenario/fill", json={"filename": "../../etc/passwd"})
    assert r.status_code == 400
    assert "путь" in r.json()["detail"]


def test_scenario_risks(client, monkeypatch):
    monkeypatch.setattr(server, "vanya_scenarios", fake_scenarios(
        find_risks=lambda filename: {
            "ok": True, "summary": "договор рискованный", "fallback": True,
            "risks": [{"punkt": "3.1", "risk": "нет ответственности",
                       "level": "высокий", "recommendation": "добавить"}],
        }))
    r = client.post("/api/scenario/risks", json={"filename": "a.txt"})
    assert r.status_code == 200
    data = r.json()
    assert data["fallback"] is True
    assert data["risks"][0]["level"] == "высокий"


def test_scenario_ask(client, monkeypatch):
    monkeypatch.setattr(server, "vanya_scenarios", fake_scenarios(
        ask=lambda filename, question: {"ok": True, "answer": "Сумма — 100 000 ₽"}))
    r = client.post("/api/scenario/ask",
                    json={"filename": "a.txt", "question": "какая сумма?"})
    assert r.status_code == 200
    assert r.json()["answer"] == "Сумма — 100 000 ₽"


def test_scenario_export_risks(client, monkeypatch):
    monkeypatch.setattr(server, "vanya_scenarios", fake_scenarios(
        export_risks=lambda filename: {
            "ok": True, "download_name": filename + "_risks.docx",
            "risks": [{"punkt": "1", "risk": "риск"}],
        }))
    r = client.post("/api/scenario/export_risks", json={"filename": "a.txt"})
    assert r.status_code == 200
    assert r.json()["download_name"] == "a.txt_risks.docx"


def test_scenario_checklist(client, monkeypatch):
    monkeypatch.setattr(server, "vanya_scenarios", fake_scenarios(
        check_contract=lambda filename, contract_type=None: {
            "ok": True, "contract_type": "услуги", "score": 75,
            "items": [{"code": "cena", "item": "цена", "present": True}],
            "missing": [],
        }))
    r = client.post("/api/scenario/checklist", json={"filename": "a.txt"})
    assert r.status_code == 200
    assert r.json()["contract_type"] == "услуги"
    assert r.json()["score"] == 75


def test_scenario_ask_empty_question_400(client, monkeypatch):
    monkeypatch.setattr(server, "vanya_scenarios", fake_scenarios())
    r = client.post("/api/scenario/ask", json={"filename": "a.txt", "question": "  "})
    assert r.status_code == 400


def test_scenario_exception_is_500(client, monkeypatch):
    def boom(filename, question):
        raise RuntimeError("ядро упало")
    monkeypatch.setattr(server, "vanya_scenarios", fake_scenarios(ask=boom))
    r = client.post("/api/scenario/ask",
                    json={"filename": "a.txt", "question": "что?"})
    assert r.status_code == 500
    assert "ядро упало" in r.json()["detail"]


# --- чат (SSE) --------------------------------------------------------------------

def test_chat_streams_events(client, monkeypatch):
    events = [
        FakeEvent("status", {"message": "думаю"}),
        FakeEvent("token", {"text": "При"}),
        FakeEvent("token", {"text": "вет"}),
        FakeEvent("tool_call", {"name": "list_files", "arguments": {}}),
        FakeEvent("tool_result", {"name": "list_files", "result": ["a.txt"]}),
        FakeEvent("final", {"answer": "Привет"}),
    ]
    monkeypatch.setattr(server, "vanya_agent", SimpleNamespace(
        Agent=lambda llm=None, max_steps=6, system=None: SimpleNamespace(
            run=lambda message, history=None: iter(events))))
    r = client.post("/api/chat", json={"message": "привет"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    kinds = [e["kind"] for e in parse_sse(r.text)]
    assert kinds == ["status", "token", "token", "tool_call", "tool_result", "final"]
    assert ": done" in r.text


def test_chat_streams_error_event(client, monkeypatch):
    events = [FakeEvent("error", {"message": "Ollama недоступна"})]
    monkeypatch.setattr(server, "vanya_agent", SimpleNamespace(
        Agent=lambda llm=None, max_steps=6, system=None: SimpleNamespace(
            run=lambda message, history=None: iter(events))))
    r = client.post("/api/chat", json={"message": "привет"})
    assert r.status_code == 200
    parsed = parse_sse(r.text)
    assert parsed[0]["kind"] == "error"
    assert "Ollama" in parsed[0]["data"]["message"]
    assert ": done" in r.text


def test_chat_survives_agent_exception(client, monkeypatch):
    def boom(message, history=None):
        raise RuntimeError("ядро упало")

    monkeypatch.setattr(server, "vanya_agent", SimpleNamespace(
        Agent=lambda llm=None, max_steps=6, system=None: SimpleNamespace(run=boom)))
    r = client.post("/api/chat", json={"message": "привет"})
    assert r.status_code == 200
    parsed = parse_sse(r.text)
    assert parsed[0]["kind"] == "error"
    assert "ядро упало" in parsed[0]["data"]["message"]
    assert ": done" in r.text


def test_chat_empty_message_400(client):
    r = client.post("/api/chat", json={"message": "   "})
    assert r.status_code == 400
