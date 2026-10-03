"""Тесты агента и LLM-сценариев (мок-LLM, без Ollama)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vanya.agent import Agent
from vanya.config import Config
from vanya.llm import LLM, ChatResult, LLMError, ToolCall
from vanya import scenarios


def _cfg() -> Config:
    return Config(
        model="qwen2.5:3b",
        ollama_url="http://127.0.0.1:1",
        workspace=Path("/tmp/vanya_test_ws"),
        port=8765,
        offline=True,
        max_ctx_chars=12000,
    )


class _FakeLLM:
    """Возвращает заранее заданные ответы; запоминает вызовы."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages, tools=None):
        self.calls.append((messages, tools))
        if self.responses:
            return self.responses.pop(0)
        return ChatResult(content="", tool_calls=[])


class _ErrorLLM:
    def chat(self, messages, tools=None):
        raise LLMError("Модель недоступна: Ollama не запущена")


class _BoomLLM:
    def chat(self, messages, tools=None):
        raise RuntimeError("boom")


class _FailingLLM:
    """LLM, у которой падают и chat, и json_chat (для сценариев)."""

    def __init__(self, config=None, timeout=300.0):
        pass

    def chat(self, messages, tools=None):
        raise LLMError("Модель недоступна: Ollama не запущена")

    def json_chat(self, messages, schema_hint=""):
        raise LLMError("Модель недоступна: Ollama не запущена")


def _ws(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("VANYA_WORKSPACE", str(ws))
    return ws


# --- цикл агента ---


def test_agent_loop_tool_then_final(tmp_path, monkeypatch):
    _ws(tmp_path, monkeypatch)
    fake = _FakeLLM(
        [
            ChatResult(content="", tool_calls=[ToolCall(name="list_files", arguments={})]),
            ChatResult(content="Готово, файлы показаны", tool_calls=[]),
        ]
    )
    events = list(Agent(llm=fake).run("покажи файлы"))
    kinds = [e.kind for e in events]
    assert "status" in kinds
    assert "tool_call" in kinds
    assert "tool_result" in kinds
    assert kinds[-1] == "final"
    assert events[-1].data["answer"] == "Готово, файлы показаны"
    # два обращения к модели: вызов инструмента и финальный ответ
    assert len(fake.calls) == 2


def test_agent_tool_result_error_path(tmp_path, monkeypatch):
    _ws(tmp_path, monkeypatch)
    fake = _FakeLLM(
        [
            ChatResult(
                content="",
                tool_calls=[ToolCall(name="read_document", arguments={"filename": "nope.txt"})],
            ),
            ChatResult(content="Не получилось", tool_calls=[]),
        ]
    )
    events = list(Agent(llm=fake).run("прочитай"))
    tool_results = [e for e in events if e.kind == "tool_result"]
    assert tool_results
    assert tool_results[0].data["ok"] is False


def test_agent_error_path():
    events = list(Agent(llm=_ErrorLLM()).run("привет"))
    assert events[-1].kind == "error"
    assert "Ollama" in events[-1].data["message"]


def test_agent_generic_exception_path():
    events = list(Agent(llm=_BoomLLM()).run("привет"))
    assert events[-1].kind == "error"


def test_agent_run_sync_returns_last_event():
    events = list(Agent(llm=_ErrorLLM()).run("привет"))
    last = Agent(llm=_ErrorLLM()).run_sync("привет")
    assert last.kind == events[-1].kind


# --- json_chat ---


def test_json_chat_strips_fences():
    llm = LLM(config=_cfg())
    llm.chat = lambda messages: ChatResult(content='```json\n{"risks": []}\n```')
    assert llm.json_chat([]) == {"risks": []}


def test_json_chat_finds_first_object_among_text():
    llm = LLM(config=_cfg())
    llm.chat = lambda messages: ChatResult(
        content='Вот результат: {"summary": "ок", "risks": [{"x": 1}]} и всё'
    )
    assert llm.json_chat([])["summary"] == "ок"


def test_json_chat_nested_braces():
    llm = LLM(config=_cfg())
    llm.chat = lambda messages: ChatResult(content='{"a": {"b": {"c": 1}}}')
    assert llm.json_chat([]) == {"a": {"b": {"c": 1}}}


def test_json_chat_invalid_raises():
    llm = LLM(config=_cfg())
    llm.chat = lambda messages: ChatResult(content="здесь нет JSON")
    with pytest.raises(LLMError):
        llm.json_chat([])


# --- сценарии с LLM ---


def test_find_risks_fallback(tmp_path, monkeypatch):
    ws = _ws(tmp_path, monkeypatch)
    (ws / "dog.txt").write_text(
        "Договор с автопролонгацией, односторонним отказом и штрафом.",
        encoding="utf-8",
    )
    monkeypatch.setattr(scenarios, "LLM", _FailingLLM)
    result = scenarios.find_risks("dog.txt")
    assert result["ok"] is True
    assert result["fallback"] is True
    assert len(result["risks"]) >= 3
    assert set(result["risks"][0].keys()) == {"punkt", "risk", "level", "recommendation"}


def test_find_risks_fallback_no_keywords(tmp_path, monkeypatch):
    ws = _ws(tmp_path, monkeypatch)
    (ws / "dog.txt").write_text("Обычный договор без подозрительных слов.", encoding="utf-8")
    monkeypatch.setattr(scenarios, "LLM", _FailingLLM)
    result = scenarios.find_risks("dog.txt")
    assert result["fallback"] is True
    assert len(result["risks"]) == 1  # общий пункт «явных рисков нет»


def test_ask_llm_failure_returns_error(tmp_path, monkeypatch):
    ws = _ws(tmp_path, monkeypatch)
    (ws / "dog.txt").write_text("текст договора", encoding="utf-8")
    monkeypatch.setattr(scenarios, "LLM", _FailingLLM)
    result = scenarios.ask("dog.txt", "какой срок оплаты?")
    assert result["ok"] is False
    assert "error" in result


class _CountingRiskLLM:
    """Успешный json_chat; считает вызовы, чтобы проверить кэш."""

    def __init__(self) -> None:
        self.calls = 0

    def json_chat(self, messages, schema_hint=""):
        self.calls += 1
        return {
            "summary": "ок",
            "risks": [
                {"punkt": "1", "risk": "риск", "level": "низкий",
                 "recommendation": "проверить"}
            ],
        }


def test_find_risks_cached_on_second_call(tmp_path, monkeypatch):
    ws = _ws(tmp_path, monkeypatch)
    (ws / "dog.txt").write_text("Договор про неустойку.", encoding="utf-8")
    fake = _CountingRiskLLM()
    monkeypatch.setattr(scenarios, "LLM", lambda config=None: fake)

    first = scenarios.find_risks("dog.txt")
    assert first["cached"] is False
    second = scenarios.find_risks("dog.txt")
    assert second["cached"] is True
    assert second["risks"] == first["risks"]
    assert fake.calls == 1  # модель вызвана один раз


class _CountingAskLLM:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        return ChatResult(content="Сумма — 100 000 ₽", tool_calls=[])


def test_ask_cached_on_second_call(tmp_path, monkeypatch):
    ws = _ws(tmp_path, monkeypatch)
    (ws / "dog.txt").write_text("Договор на 100 000 рублей.", encoding="utf-8")
    fake = _CountingAskLLM()
    monkeypatch.setattr(scenarios, "LLM", lambda config=None: fake)

    first = scenarios.ask("dog.txt", "какая сумма?")
    assert first["ok"] is True and first["cached"] is False
    second = scenarios.ask("dog.txt", "какая сумма?")
    assert second["cached"] is True
    assert fake.calls == 1
