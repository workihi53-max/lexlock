"""Инструменты агента: ровно 6 штук для работы с файлами."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import docs, extract, scenarios
from .config import load_config


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    fn: Callable[..., dict]


def _list_files() -> list[dict]:
    cfg = load_config()
    ws = cfg.workspace
    ws.mkdir(parents=True, exist_ok=True)
    files = []
    for item in sorted(ws.iterdir()):
        if item.is_file():
            files.append(
                {
                    "name": item.name,
                    "size": item.stat().st_size,
                    "ext": item.suffix.lstrip("."),
                }
            )
    return files


def _read_document_tool(filename: str) -> dict:
    cfg = load_config()
    text = docs.read_document(cfg.workspace / filename)
    return {"filename": filename, "text": text}


def _extract_requisites_tool(filename: str) -> dict:
    cfg = load_config()
    text = docs.read_document(cfg.workspace / filename)
    found = extract.extract_requisites(text)
    return {"fields": found, "missing": extract.missing_fields(found)}


def _fill_contract_tool(source_filename: str | None = None, out_name: str | None = None) -> dict:
    return scenarios.fill_contract(source_filename, out_name)


def _find_risks_tool(filename: str) -> dict:
    return scenarios.find_risks(filename)


def _write_report_tool(name: str, content: str) -> dict:
    cfg = load_config()
    path = docs.write_text(cfg.workspace / name, content)
    return {"name": path.name, "path": str(path)}


TOOLS: list[Tool] = [
    Tool(
        name="list_files",
        description="Вернуть список файлов в рабочем пространстве (имя, размер, расширение).",
        parameters={"type": "object", "properties": {}, "required": []},
        fn=_list_files,
    ),
    Tool(
        name="read_document",
        description="Прочитать текстовое содержимое документа из рабочего пространства.",
        parameters={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Имя файла в рабочем пространстве",
                }
            },
            "required": ["filename"],
        },
        fn=_read_document_tool,
    ),
    Tool(
        name="extract_requisites",
        description="Извлечь реквизиты из документа (детерминированно, без модели).",
        parameters={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Имя файла в рабочем пространстве",
                }
            },
            "required": ["filename"],
        },
        fn=_extract_requisites_tool,
    ),
    Tool(
        name="fill_contract",
        description=(
            "Извлечь реквизиты и заполнить шаблон договора, результат сохранить "
            "в рабочее пространство. Если имя исходного файла не указано — "
            "берётся весь пакет документов из рабочей папки."
        ),
        parameters={
            "type": "object",
            "properties": {
                "source_filename": {
                    "type": "string",
                    "description": "Имя исходного файла (необязательно)",
                },
                "out_name": {
                    "type": "string",
                    "description": "Имя выходного файла (необязательно)",
                },
            },
            "required": [],
        },
        fn=_fill_contract_tool,
    ),
    Tool(
        name="find_risks",
        description="Проанализировать договор и вернуть список юридических рисков.",
        parameters={
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Имя файла договора в рабочем пространстве",
                }
            },
            "required": ["filename"],
        },
        fn=_find_risks_tool,
    ),
    Tool(
        name="write_report",
        description="Сохранить текстовый отчёт в рабочее пространство.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Имя файла отчёта"},
                "content": {"type": "string", "description": "Текст отчёта"},
            },
            "required": ["name", "content"],
        },
        fn=_write_report_tool,
    ),
]


def tool_schemas() -> list[dict]:
    """Схемы инструментов в формате Ollama/OpenAI."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in TOOLS
    ]


def dispatch(name: str, arguments: dict) -> dict:
    """Выполняет инструмент. Никогда не бросает исключение наружу."""
    arguments = arguments or {}
    for t in TOOLS:
        if t.name == name:
            try:
                result = t.fn(**arguments)
            except Exception as exc:  # noqa: BLE001 — здесь граница, ловим всё
                return {"ok": False, "error": str(exc)}
            return {"ok": True, "result": result}
    return {"ok": False, "error": f"Неизвестный инструмент: {name}"}
