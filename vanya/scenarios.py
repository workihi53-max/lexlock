"""Высокоуровневые сценарии: заполнение договора, риски, вопрос по документу."""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import cache, checklists, docs, extract, prompts, rag
from .config import TEMPLATES_DIR, load_config
from .llm import LLM, LLMError

_SOURCE_HEADER = re.compile(r"=== (.+?) ===")

# Маркеры — устойчивые «корни» ключевых слов, чтобы ловить падежные формы.
_RISK_RULES: list[tuple[list[str], str, str, str, str]] = [
    (
        ["автопролонгац"],
        "автопролонгация",
        "высокий",
        "Автопролонгация договора без явного права стороны на отказ.",
        "Предусмотреть явный срок уведомления об отказе от пролонгации.",
    ),
    (
        ["односторонн"],
        "односторонний отказ",
        "высокий",
        "Право на односторонний отказ или изменение условий без согласования.",
        "Ограничить основания одностороннего отказа и уведомить заранее.",
    ),
    (
        ["срок оплат", "сроки оплат"],
        "срок оплаты",
        "средний",
        "Срок оплаты не определён или сформулирован слишком широко.",
        "Зафиксировать конкретный срок и порядок оплаты.",
    ),
    (
        ["пеня", "пени", "пеней"],
        "пеня",
        "средний",
        "Условие о пене за просрочку, размер требует проверки.",
        "Проверить размер пени на соразмерность (ст. 333 ГК РФ).",
    ),
    (
        ["неустойк"],
        "неустойка",
        "средний",
        "Условие о неустойке, размер требует проверки.",
        "Проверить размер неустойки на соразмерность (ст. 333 ГК РФ).",
    ),
    (
        ["штраф"],
        "штраф",
        "средний",
        "Условие о штрафах, основания и размеры требуют проверки.",
        "Проверить основания начисления и размеры штрафов.",
    ),
    (
        ["подсудност"],
        "подсудность",
        "низкий",
        "Оговорка о подсудности споров.",
        "Проверить, не ущемляет ли оговорка права стороны.",
    ),
]


def _llm_extract_enabled() -> bool:
    """Дозаполнение реквизитов моделью — опционально (по умолчанию выключено)."""
    return os.environ.get("VANYA_LLM_EXTRACT", "0").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _llm_fill_missing(cfg, text: str, found: dict, log: list[str]) -> list[str]:
    """Просит модель заполнить ненайденные поля. Ошибки не роняют сценарий."""
    missing = extract.missing_fields(found)
    if not missing:
        return []
    try:
        llm = LLM(cfg)
        data = llm.json_chat(
            [
                {"role": "system", "content": prompts.EXTRACT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Нужные поля: {missing}\n\nТекст договора:\n\n"
                        f"{text[: cfg.max_ctx_chars]}"
                    ),
                },
            ],
            schema_hint=prompts.extract_schema(missing),
        )
    except LLMError as exc:
        log.append(f"Дозаполнение моделью недоступно: {exc}")
        return []
    filled: list[str] = []
    for name in missing:
        value = data.get(name) if isinstance(data, dict) else None
        if isinstance(value, str) and value.strip():
            found[name] = value.strip()
            filled.append(name)
    if filled:
        log.append("Модель дозаполнила поля: " + ", ".join(filled))
    return filled


def fill_contract(source_filename: str | None = None, out_name: str | None = None) -> dict:
    """Детерминированный конвейер: чтение → извлечение → заполнение шаблона.

    Работает без LLM. Пустой source_filename (None / "" / "-") — режим «пакет».
    """
    cfg = load_config()
    package_mode = source_filename in (None, "", "-")
    log = []
    sources: list[str] = []
    model_fields: list[str] = []
    try:
        if package_mode:
            log.append("Режим «пакет»: читаю все документы рабочей папки")
            text = docs.read_folder(cfg.workspace)
            sources = _SOURCE_HEADER.findall(text)
        else:
            log.append(f"Читаю источник: {source_filename}")
            text = docs.read_document(cfg.workspace / source_filename)
            sources = [source_filename]
    except Exception as exc:
        log.append(f"Ошибка чтения источника: {exc}")
        return {
            "ok": False,
            "error": f"Не удалось прочитать источник: {exc}",
            "fields": {},
            "missing": list(extract.FIELDS),
            "model_fields": model_fields,
            "log": log,
            "package_mode": package_mode,
            "sources": sources,
        }

    found = extract.extract_requisites(text)
    if _llm_extract_enabled():
        model_fields = _llm_fill_missing(cfg, text, found, log)
    missing = extract.missing_fields(found)
    log.append(f"Найдено реквизитов: {len(found)}")

    template = TEMPLATES_DIR / "dogovor_template.docx"
    if not template.exists():
        log.append("Шаблон договора не найден")
        return {
            "ok": False,
            "error": "Шаблон договора не найден",
            "fields": found,
            "missing": missing,
            "model_fields": model_fields,
            "log": log,
            "package_mode": package_mode,
            "sources": sources,
        }

    if out_name is None:
        out_name = "dogovor.docx" if package_mode else Path(source_filename).stem + "_dogovor.docx"
    out_path = cfg.workspace / out_name
    docs.fill_docx(template, found, out_path)
    log.append(f"Договор сохранён: {out_name}")
    return {
        "ok": True,
        "out_path": str(out_path),
        "fields": found,
        "missing": missing,
        "model_fields": model_fields,
        "log": log,
        "package_mode": package_mode,
        "sources": sources,
    }


def _heuristic_risks(text: str) -> list[dict]:
    lowered = text.lower()
    risks: list[dict] = []
    for markers, punkt, level, risk, recommendation in _RISK_RULES:
        if any(marker in lowered for marker in markers):
            risks.append(
                {
                    "punkt": punkt,
                    "risk": risk,
                    "level": level,
                    "recommendation": recommendation,
                }
            )
    if not risks:
        risks.append(
            {
                "punkt": "общие",
                "risk": "Явных рисков по ключевым словам не обнаружено.",
                "level": "низкий",
                "recommendation": "Проверить договор вручную.",
            }
        )
    return risks


def find_risks(filename: str) -> dict:
    """Анализ рисков через LLM; при недоступности модели — эвристика (fallback=True)."""
    cfg = load_config()
    log = [f"Читаю документ: {filename}"]
    try:
        text = docs.read_document(cfg.workspace / filename)
    except Exception as exc:
        return {
            "ok": False,
            "summary": "",
            "risks": [],
            "log": [f"Ошибка чтения документа: {exc}"],
            "fallback": True,
        }

    snippet = rag.select_relevant(text, prompts.RISK_QUERY, cfg.max_ctx_chars)
    key = cache.make_key(cfg.model, "risks", text, str(cfg.max_ctx_chars))
    cached = cache.get(cfg.workspace, key)
    if cached is not None:
        log.append("Риски взяты из кэша")
        return {**cached, "log": log, "cached": True}

    llm = LLM(cfg)
    messages = [
        {"role": "system", "content": prompts.RISK_SYSTEM_PROMPT},
        {"role": "user", "content": f"Проанализируй договор:\n\n{snippet}"},
    ]
    try:
        data = llm.json_chat(messages, schema_hint=prompts.RISK_SCHEMA)
        risks = data.get("risks", []) if isinstance(data, dict) else []
        summary = data.get("summary", "") if isinstance(data, dict) else ""
        if not risks:
            raise LLMError("Модель не вернула список рисков")
        payload = {"ok": True, "summary": summary, "risks": risks, "fallback": False}
        cache.put(cfg.workspace, key, payload)
        log.append("Риски получены от модели")
        return {**payload, "log": log, "cached": False}
    except LLMError as exc:
        log.append(f"Модель недоступна, использую эвристику: {exc}")
        return {
            "ok": True,
            "summary": "Эвристический анализ (модель недоступна).",
            "risks": _heuristic_risks(text),
            "log": log,
            "fallback": True,
            "cached": False,
        }


def ask(filename: str, question: str) -> dict:
    """Ответ на вопрос по документу; при сбое модели — {"ok": False, "error": ...}."""
    cfg = load_config()
    try:
        text = docs.read_document(cfg.workspace / filename)
    except Exception as exc:
        return {"ok": False, "error": f"Не удалось прочитать документ: {exc}"}

    snippet = rag.select_relevant(text, question, cfg.max_ctx_chars)
    key = cache.make_key(cfg.model, "ask", text, question)
    cached = cache.get(cfg.workspace, key)
    if cached is not None:
        return {**cached, "cached": True}

    llm = LLM(cfg)
    messages = [
        {"role": "system", "content": prompts.ASK_SYSTEM_PROMPT},
        {"role": "user", "content": f"Документ:\n\n{snippet}\n\nВопрос: {question}"},
    ]
    try:
        answer = llm.chat(messages).content
    except LLMError as exc:
        return {"ok": False, "error": str(exc)}
    result = {"ok": True, "answer": answer}
    cache.put(cfg.workspace, key, result)
    return {**result, "cached": False}


def export_risks(filename: str) -> dict:
    """Прогоняет анализ рисков и сохраняет отчёт в .docx рядом в workspace."""
    analysis = find_risks(filename)
    if not analysis.get("ok"):
        return analysis
    cfg = load_config()
    out_name = Path(filename).stem + "_risks.docx"
    out_path = cfg.workspace / out_name
    docs.write_risk_report(
        out_path,
        filename,
        str(analysis.get("summary", "")),
        list(analysis.get("risks", [])),
    )
    return {
        "ok": True,
        "out_path": str(out_path),
        "download_name": out_name,
        "risks": analysis.get("risks", []),
        "fallback": analysis.get("fallback", False),
    }


def check_contract(filename: str, contract_type: str | None = None) -> dict:
    """Проверка договора по чек-листу. Тип определяется автоматически или задан."""
    cfg = load_config()
    try:
        text = docs.read_document(cfg.workspace / filename)
    except Exception as exc:
        return {"ok": False, "error": f"Не удалось прочитать документ: {exc}"}
    ctype = contract_type if contract_type in checklists.CHECKLISTS else None
    if ctype is None:
        ctype = checklists.detect_contract_type(text)
    items = checklists.evaluate(text, ctype)
    missing = [item["item"] for item in items if not item["present"]]
    found = len(items) - len(missing)
    score = round(found / len(items) * 100) if items else 0
    return {
        "ok": True,
        "contract_type": ctype,
        "items": items,
        "missing": missing,
        "score": score,
    }
