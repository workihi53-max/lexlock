"""Работа с Ollama через HTTP API (только 127.0.0.1)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterator

import httpx

from .config import Config, load_config


@dataclass
class ToolCall:
    name: str
    arguments: dict


@dataclass
class ChatResult:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMError(RuntimeError):
    """Ошибка обращения к модели (недоступна, неверный ответ и т.п.)."""


def _parse_arguments(raw) -> dict:
    """Аргументы вызова инструмента приходят либо dict, либо JSON-строкой."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _first_json_object(text: str) -> dict:
    """Находит первый сбалансированный {...}-блок и разбирает его в JSON."""
    start = text.find("{")
    if start == -1:
        raise ValueError("нет JSON-объекта в ответе")
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("не найден закрывающий JSON-блок")


class LLM:
    def __init__(self, config: Config | None = None, timeout: float = 300.0) -> None:
        self.config = config or load_config()
        self.timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.config.ollama_url, timeout=self.timeout)

    def _model_present(self, names: list[str]) -> bool:
        model = self.config.model
        base = model.split(":")[0]
        return model in names or any(n.split(":")[0] == base for n in names)

    def available(self) -> bool:
        try:
            with self._client() as client:
                resp = client.get("/api/tags")
                resp.raise_for_status()
                models = resp.json().get("models", [])
            return self._model_present([m.get("name", "") for m in models])
        except (httpx.HTTPError, ValueError):
            return False

    def health(self) -> dict:
        try:
            with self._client() as client:
                resp = client.get("/api/tags", timeout=5.0)
                if resp.status_code != 200:
                    return {
                        "ok": False,
                        "model": self.config.model,
                        "installed": False,
                        "error": f"Ollama вернула статус {resp.status_code}",
                    }
                models = resp.json().get("models", [])
            names = [m.get("name", "") for m in models]
            installed = self._model_present(names)
            if not installed:
                return {
                    "ok": False,
                    "model": self.config.model,
                    "installed": False,
                    "error": "Модель не установлена",
                }
            return {
                "ok": True,
                "model": self.config.model,
                "installed": True,
                "error": None,
            }
        except httpx.ConnectError:
            return {
                "ok": False,
                "model": self.config.model,
                "installed": False,
                "error": "Модель недоступна: Ollama не запущена",
            }
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "ok": False,
                "model": self.config.model,
                "installed": False,
                "error": f"Ошибка обращения к Ollama: {exc}",
            }

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResult:
        payload: dict = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        try:
            with self._client() as client:
                resp = client.post("/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.ConnectError as exc:
            raise LLMError("Модель недоступна: Ollama не запущена") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Ошибка обращения к Ollama: {exc}") from exc

        message = data.get("message", {}) or {}
        content = message.get("content", "") or ""
        tool_calls = [
            ToolCall(
                name=(tc.get("function", {}) or {}).get("name", ""),
                arguments=_parse_arguments((tc.get("function", {}) or {}).get("arguments")),
            )
            for tc in (message.get("tool_calls") or [])
        ]
        return ChatResult(content=content, tool_calls=tool_calls)

    def stream(self, messages: list[dict]) -> Iterator[str]:
        payload = {"model": self.config.model, "messages": messages, "stream": True}
        try:
            with self._client() as client:
                with client.stream("POST", "/api/chat", json=payload) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        piece = (chunk.get("message", {}) or {}).get("content", "")
                        if piece:
                            yield piece
        except httpx.ConnectError as exc:
            raise LLMError("Модель недоступна: Ollama не запущена") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Ошибка обращения к Ollama: {exc}") from exc

    def json_chat(self, messages: list[dict], schema_hint: str = "") -> dict:
        """Просит строгий JSON, устойчиво извлекает первый {...}-блок."""
        instruction = (
            "Отвечай строго в формате JSON, без markdown-разметки и пояснений. "
            "Верни только JSON-объект."
        )
        if schema_hint:
            instruction += f" Схема ответа: {schema_hint}"
        msgs = [{"role": "system", "content": instruction}, *messages]
        raw = self.chat(msgs).content
        text = (raw or "").strip()
        # Снимаем возможные markdown-обёртки.
        text = text.removeprefix("```json").removeprefix("```")
        text = text.removesuffix("```").strip()
        try:
            obj = _first_json_object(text)
        except (ValueError, json.JSONDecodeError) as exc:
            raise LLMError("Модель вернула некорректный JSON") from exc
        if not isinstance(obj, dict):
            raise LLMError("Модель вернула не JSON-объект")
        return obj
