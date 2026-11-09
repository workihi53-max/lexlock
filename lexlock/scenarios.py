"""Высокоуровневые сценарии: заполнение договора, риски, вопрос по документу."""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import analysis, cache, checklists, docs, extract, ocr, prompts, rag
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


# Поля, которые модель может дозаполнять. Структурные/идентификационные поля
# (даты, ИНН, ОГРН, счета, паспорт, сумма) исключены: их надёжно достаёт только
# регулярка, а маленькая модель склонна их выдумывать (галлюцинации). Модель
# дозаполняет только свободный текст, где ошибка не критична для документа.
_LLM_FILLABLE = {
    "familiya", "imya", "otchestvo", "fio",
    "pasport_vydan", "adres_registracii",
    "organizaciya", "yuridicheskiy_adres", "bank",
    "dolzhnost", "telefon", "email",
}

# Нормализация уровня риска: маленькая модель пишет «нижкий», «mid», «high» и т.п.
_LEVEL_ALIASES = (
    ("высок", "высокий"), ("high", "высокий"),
    ("сред", "средний"), ("mid", "средний"),
    ("низк", "низкий"), ("нижк", "низкий"), ("низ", "низкий"), ("low", "низкий"),
)


def _norm_level(level: str) -> str:
    s = (level or "").strip().lower()
    for prefix, canon in _LEVEL_ALIASES:
        if s.startswith(prefix):
            return canon
    return "низкий"


def _llm_extract_enabled() -> bool:
    """Дозаполнение реквизитов моделью — опционально (по умолчанию выключено)."""
    return os.environ.get("LEXLOCK_LLM_EXTRACT", "0").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _llm_fill_missing(cfg, text: str, found: dict, log: list[str]) -> list[str]:
    """Просит модель заполнить ненайденные поля. Ошибки не роняют сценарий."""
    missing = [f for f in extract.missing_fields(found) if f in _LLM_FILLABLE]
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
            text = docs.read_document(docs.safe_workspace_path(cfg.workspace, source_filename))
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
    try:
        out_path = docs.safe_workspace_path(cfg.workspace, out_name)
        docs.fill_docx(template, found, out_path)
    except (ValueError, OSError) as exc:
        return {"ok": False, "error": f"Не удалось сохранить договор: {exc}"}
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


RISK_SIDES = {"neutral": "Общий анализ", "customer": "Заказчик", "contractor": "Исполнитель"}


def find_risks(filename: str, side: str = "neutral") -> dict:
    """Детерминированный поиск рисков по явным условиям договора.

    Свободный «юридический анализ» моделью убран: маленькая локальная модель
    галлюцинирует в рассуждениях о праве. Осталась только проверка по явным
    маркерам опасных условий (пролонгация, односторонний отказ, неустойка и т.п.),
    без учёта стороны (эвристика стороне не различает её интересы — честно).
    """
    if side not in RISK_SIDES:
        raise ValueError("Неизвестная сторона договора")
    cfg = load_config()
    log = [f"Читаю документ: {filename}"]
    try:
        text = docs.read_document(docs.safe_workspace_path(cfg.workspace, filename))
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Не удалось прочитать документ: {exc}",
            "summary": "",
            "risks": [],
            "log": [f"Ошибка чтения документа: {exc}"],
            "fallback": False,
        }
    return {
        "ok": True,
        "summary": "Проверка по явным условиям договора (детерминированно, без модели).",
        "side": side,
        "risks": _heuristic_risks(text),
        "log": log,
        "fallback": False,
        "cached": False,
    }


def ask(filename: str, question: str) -> dict:
    """Ответ на вопрос по документу; при сбое модели — {"ok": False, "error": ...}."""
    cfg = load_config()
    try:
        text = docs.read_document(docs.safe_workspace_path(cfg.workspace, filename))
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
    sources = [
        {"filename": filename, "score": hit["score"], "snippet": hit["snippet"]}
        for hit in rag.search(text, question, top=3)
    ]
    result = {"ok": True, "answer": answer, "sources": sources}
    cache.put(cfg.workspace, key, result)
    return {**result, "cached": False}


def search_documents(query: str) -> dict:
    """Поиск по всем документам рабочей папки (RAG-lite) с указанием источника."""
    cfg = load_config()
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "Пустой запрос"}
    if not cfg.workspace.is_dir():
        return {"ok": True, "query": query, "matches": []}
    matches: list[dict] = []
    for item in sorted(cfg.workspace.iterdir()):
        if not item.is_file() or item.is_symlink():
            continue
        try:
            text = docs.read_document(item)
        except Exception:
            continue
        for hit in rag.search(text, query):
            matches.append(
                {"filename": item.name, "score": hit["score"], "snippet": hit["snippet"]}
            )
    matches.sort(key=lambda m: -m["score"])
    return {"ok": True, "query": query, "matches": matches[:10]}


def summarize(filename: str) -> dict:
    """«Паспорт» документа: тип, стороны, дата, номер, сумма, предмет (без LLM).

    Свободное резюме моделью убрано — маленькая модель галлюцинирует. Вместо него
    детерминированное извлечение структурированных полей.
    """
    cfg = load_config()
    try:
        text = docs.read_document(docs.safe_workspace_path(cfg.workspace, filename))
    except Exception as exc:
        return {"ok": False, "error": f"Не удалось прочитать документ: {exc}"}
    return {"ok": True, "filename": filename, **analysis.document_passport(text)}


def compare_documents(a: str, b: str) -> dict:
    """Сравнение двух документов по извлечённым полям (без LLM)."""
    cfg = load_config()
    try:
        text_a = docs.read_document(docs.safe_workspace_path(cfg.workspace, a))
        text_b = docs.read_document(docs.safe_workspace_path(cfg.workspace, b))
    except Exception as exc:
        return {"ok": False, "error": f"Не удалось прочитать документы: {exc}"}
    pa = analysis.document_passport(text_a)
    pb = analysis.document_passport(text_b)
    differences = []
    for field in ("type", "date", "number", "sum"):
        va, vb = pa.get(field), pb.get(field)
        if va != vb:
            differences.append(
                f"{field}: «{va or '—'}» против «{vb or '—'}»"
            )
    return {
        "ok": True,
        "a": a,
        "b": b,
        "differences": differences,
        "a_passport": pa,
        "b_passport": pb,
    }


def recognize_document(filename: str) -> dict:
    """OCR (если скан/изображение) + очистка текста + паспорт документа.

    Черновой разбор русских документов: распознавание через Tesseract, очистка
    артефактов моделью (опционально) и детерминированное извлечение полей.
    """
    cfg = load_config()
    path = docs.safe_workspace_path(cfg.workspace, filename)
    try:
        text = docs.read_document(path)
    except Exception as exc:
        return {"ok": False, "error": f"Не удалось прочитать документ: {exc}"}

    ext = path.suffix.lower()
    was_ocr = ext in ocr.IMAGE_EXT or (ext == ".pdf" and ocr.needs_ocr(text))

    llm = None
    try:
        llm = LLM(cfg)
    except Exception:
        llm = None
    cleaned, model_used = analysis.clean_ocr_text(text, llm)
    passport = analysis.document_passport(cleaned)
    return {
        "ok": True,
        "filename": filename,
        "ocr": was_ocr,
        "cleaned_by_model": model_used,
        "text": cleaned,
        **passport,
    }


def export_risks(filename: str, side: str = "neutral") -> dict:
    """Прогоняет анализ рисков и сохраняет отчёт в .docx рядом в workspace."""
    result = find_risks(filename, side=side)
    if not result.get("ok"):
        return result
    cfg = load_config()
    out_name = Path(filename).stem + "_risks.docx"
    out_path = docs.safe_workspace_path(cfg.workspace, out_name)
    docs.write_risk_report(
        out_path,
        filename,
        f"Сторона: {RISK_SIDES[side]}. " + str(result.get("summary", "")),
        list(result.get("risks", [])),
    )
    return {
        "ok": True,
        "out_path": str(out_path),
        "download_name": out_name,
        "side": side,
        "risks": result.get("risks", []),
        "fallback": result.get("fallback", False),
    }


def check_contract(filename: str, contract_type: str | None = None) -> dict:
    """Проверка договора по чек-листу. Тип определяется автоматически или задан."""
    cfg = load_config()
    try:
        text = docs.read_document(docs.safe_workspace_path(cfg.workspace, filename))
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


def document_structure(filename: str) -> dict:
    """Оглавление документа: нумерованные разделы и пункты (без модели)."""
    cfg = load_config()
    try:
        text = docs.read_document(docs.safe_workspace_path(cfg.workspace, filename))
    except Exception as exc:
        return {"ok": False, "error": f"Не удалось прочитать документ: {exc}"}
    return {
        "ok": True,
        "filename": filename,
        "type": analysis.classify_document(text),
        "sections": analysis.document_structure(text),
    }


# Поля, расхождение которых между документами пакета критично для юриста.
_CONSISTENCY_FIELDS = ("inn", "ogrn", "kpp", "bik", "raschetny_schet", "korr_schet")


def check_consistency() -> dict:
    """Сверка реквизитов между документами рабочей папки (поиск расхождений).

    Полезно юристу: если в договоре ИНН один, а в карточке реквизитов другой —
    это показывается как расхождение. Детерминированно, без модели.
    """
    cfg = load_config()
    docs_data: list[dict] = []
    if cfg.workspace.is_dir():
        for item in sorted(cfg.workspace.iterdir()):
            if not item.is_file() or item.is_symlink():
                continue
            if item.suffix.lower() not in docs.TEXT_EXT | docs._DOCX_PDF_EXT | docs.ODT_EXT:
                continue
            try:
                text = docs.read_document(item)
            except Exception:
                continue
            found = extract.extract_requisites(text)
            docs_data.append({"filename": item.name, "fields": found})

    discrepancies: list[dict] = []
    for field in _CONSISTENCY_FIELDS:
        values: dict[str, list[str]] = {}
        for d in docs_data:
            value = d["fields"].get(field)
            if value:
                values.setdefault(value, []).append(d["filename"])
        if len(values) > 1:
            discrepancies.append(
                {
                    "field": field,
                    "values": [
                        {"value": value, "files": files}
                        for value, files in values.items()
                    ],
                }
            )
    return {
        "ok": True,
        "documents": [d["filename"] for d in docs_data],
        "discrepancies": discrepancies,
    }
