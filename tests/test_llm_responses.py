"""Поведение HTTP-клиента при повреждённых и пустых ответах Ollama."""
import httpx
import pytest

from lexlock.llm import LLM, LLMError


@pytest.mark.parametrize('body', [
    b'not json', b'[]', b'{"message": []}', b'{"message": {}}',
    b'{"message": {"content": 42}}',
    b'{"message": {"tool_calls": ["bad"]}}',
])
def test_bad_http_message_is_llm_error(monkeypatch, body):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    monkeypatch.setattr(LLM, '_client', lambda self: httpx.Client(
        base_url='http://127.0.0.1:11434', transport=transport))
    with pytest.raises(LLMError):
        LLM().chat([{'role': 'user', 'content': 'Вопрос'}])


def test_tool_only_response_is_not_empty(monkeypatch):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        'message': {'content': '', 'tool_calls': [
            {'function': {'name': 'list_files', 'arguments': {}}}
        ]}
    }))
    monkeypatch.setattr(LLM, '_client', lambda self: httpx.Client(
        base_url='http://127.0.0.1:11434', transport=transport))
    assert LLM().chat([]).tool_calls[0].name == 'list_files'
