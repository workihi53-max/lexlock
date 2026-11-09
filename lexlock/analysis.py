"""Точные задачи по документам: классификация, паспорт документа, очистка OCR.

Здесь нет свободного «юридического анализа» модели. Маленькая локальная модель
(qwen2.5:1.5b/3b) надёжно справляется с ограниченным набором задач, но галлюцинирует
в свободных рассуждениях о праве. Поэтому в этом модуле — только то, что работает
точно и предсказуемо:

- классификация типа документа (детерминированно, по маркерам);
- «паспорт» документа — извлечение структурированных полей (стороны, дата, номер,
  сумма, предмет) регулярками;
- очистка распознанного OCR-текста (исправление артефактов без изменения смысла).

Правило: никакого свободного текста «что думает модель». Либо детерминированный
вывод, либо честное «не определено».
"""

from __future__ import annotations

import re
from datetime import datetime

from . import extract
from .llm import LLM, LLMError

# --- классификация типа документа ----------------------------------------------
# Маркеры проверяются в нижнем регистре; порядок важен (специфичное раньше).
_DOC_TYPES: list[tuple[str, list[str]]] = [
    ("паспорт", ["серия паспорта", "номер паспорта", "кем выдан", "дата рождения",
                 "код подразделения", "паспорт гражданина"]),
    ("реквизиты", ["инн", "кпп", "огрн", "расчётный счёт", "расчетный счет",
                   "бик", "корреспондентский счёт", "корреспондентский счет"]),
    ("доверенность", ["доверенност", "доверяю", "уполномочиваю"]),
    ("исковое заявление", ["исковое заявлен", "истец", "ответчик", "арбитражный суд",
                           "суд общей юрисдикции"]),
    ("претензия", ["претензи", "требовани"]),
    ("счёт", ["счёт на оплат", "счет на оплат", "платёжное поручени"]),
    ("договор", ["договор", "соглашение", "стороны обязуются", "исполнитель обязуется",
                 "поставщик обязуется", "арендодатель обязуется"]),
    ("акт", ["акт приёмк", "акт приемк", "акт сдачи", "акт сверки",
             "акт выполненных работ"]),
]


def classify_document(text: str) -> str:
    """Возвращает тип документа по ключевым маркерам; иначе «иное»."""
    lowered = (text or "").lower()
    for name, markers in _DOC_TYPES:
        if any(m in lowered for m in markers):
            return name
    return "иное"


# --- паспорт документа ----------------------------------------------------------

_SUBJECT_HEADER_RE = re.compile(
    r"(?:предмет(?:\s+договора)?|1[\.\)]\s*предмет)\s*[:\n]\s*",
    re.IGNORECASE,
)
_NUM_HEADER_RE = re.compile(r"^\d+(?:\.\d+)*[\.\)]\s")


def _extract_subject(text: str) -> str:
    """Вытаскивает первый абзац раздела «Предмет» (до заголовка/пустой строки)."""
    m = _SUBJECT_HEADER_RE.search(text)
    if not m:
        return ""
    out: list[str] = []
    for line in text[m.end():].split("\n"):
        stripped = line.strip()
        if not stripped:
            break
        if _NUM_HEADER_RE.match(stripped) and out:
            break
        out.append(stripped)
        if len(out) >= 3:
            break
    return " ".join(" ".join(out).split())[:300]


def document_passport(text: str) -> dict:
    """Детерминированный «паспорт» документа: тип, стороны, дата, номер, сумма.

    Ничего не додумывает: если поле не найдено — его просто нет в результате.
    """
    found = extract.extract_requisites(text)
    parties: list[str] = []
    org = found.get("organizaciya")
    if org:
        parties.append(org)
    fio = found.get("fio")
    if fio:
        parties.append(fio)

    number = found.get("nomer_dogovora")
    if not number:
        m = re.search(r"№\s*([\d/.\-]+)", text)
        if m:
            number = m.group(1)

    date = found.get("data_dogovora")
    if not date:
        m = re.search(r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b", text)
        if m:
            date = m.group(1)

    return {
        "type": classify_document(text),
        "parties": parties,
        "date": date or "",
        "number": number or "",
        "sum": found.get("summa", ""),
        "subject": _extract_subject(text),
    }


# --- очистка OCR-текста ---------------------------------------------------------

OCR_CLEAN_PROMPT = (
    "Ты — система очистки текста после оптического распознавания (OCR) со скана. "
    "Тебе дают распознанный русский текст. Исправь ТОЛЬКО технические дефекты "
    "распознавания: объедини слова, разорванные переносами строк; убери лишние "
    "пробелы и пустые строки; исправь очевидные ошибки распознавания БУКВ "
    "(например, «тп»/«rn», потерянные знаки препинания). "
    "ВАЖНО: НЕ трогай цифры и числа — не меняй их, не переставляй и не добавляй в "
    "них дефисы, пробелы или точки. Номера, коды, счета, БИК, ИНН должны остаться "
    "ровно такими же, как в исходном тексте. "
    "НЕ меняй смысл, НЕ пересказывай, НЕ добавляй отсутствующие данные, НЕ пиши "
    "ничего от себя. Верни ТОЛЬКО исправленный текст, без пояснений и заголовков."
)


def _basic_clean(text: str) -> str:
    s = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    # мягкий перенос «слово-\nслово» → слитно
    s = re.sub(r"([а-яёa-z0-9])-\n([а-яёa-z0-9])", r"\1\2", s, flags=re.IGNORECASE)
    # схлопнуть пробелы и пустые строки
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


# Числовая последовательность: цифры, возможно, с разделителями внутри.
_NUM_RE = re.compile(r"\d[\d\s\-./()]*\d|\d")


def _restore_numbers(original: str, cleaned: str) -> str:
    """Возвращает cleaned, но с числами из original, если модель их переформатировала.

    Маленькая модель при OCR-очистке иногда добавляет дефисы/пробелы внутрь чисел
    (БИК 044525225 -> 044-525-225), что ломает извлечение реквизитов. Здесь мы
    возвращаем исходный вид чисел, если их цифровой «слепок» не изменился.
    """
    def sig(s: str) -> str:
        return re.sub(r"[^\d]", "", s)

    orig = _NUM_RE.findall(original)
    clean = _NUM_RE.findall(cleaned)
    if len(orig) != len(clean):
        return cleaned  # числа потеряны/добавлены — не вмешиваемся
    result = cleaned
    for a, b in zip(orig, clean):
        if sig(a) == sig(b) and a != b:
            result = result.replace(b, a, 1)
    return result


def clean_ocr_text(text: str, llm: LLM | None = None) -> tuple[str, bool]:
    """Очищает OCR-текст: детерминированная предобработка + модель (опционально).

    Возвращает (текст, использовалась_ли_модель). Ошибки модели не роняют вызов —
    тогда остаётся только детерминированная очистка.
    """
    cleaned = _basic_clean(text)
    if llm is None:
        return cleaned, False
    try:
        out = llm.chat(
            [
                {"role": "system", "content": OCR_CLEAN_PROMPT},
                {"role": "user", "content": cleaned},
            ]
        ).content
        if out and out.strip():
            return _restore_numbers(cleaned, out.strip()), True
    except LLMError:
        pass
    return cleaned, False


# --- структура документа --------------------------------------------------------

_HEADING_RE = re.compile(
    r"^(?:глава\s*(\d+)|раздел\s*(\d+)|(\d{1,2}(?:\.\d{1,2})*))\s*[\.\)]?\s+(.+)$",
    re.IGNORECASE,
)


def document_structure(text: str) -> list[dict]:
    """Извлекает заголовки разделов/пунктов документа (оглавление).

    Детерминированно: только строки с нумерацией («1.», «1.1», «Глава 2») и
    коротким текстом (до 70 символов) считаются заголовками. Длинные нумерованные
    абзацы (обычные пункты) отсекаются.
    """
    items: list[dict] = []
    for line in (text or "").split("\n"):
        s = line.strip()
        m = _HEADING_RE.match(s)
        if not m:
            continue
        num = m.group(1) or m.group(2) or m.group(3)
        title = m.group(4).strip()
        if num and len(title) <= 70:
            items.append({"number": num, "title": title})
    return items


# --- нормализация значений ------------------------------------------------------

_DATE_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b")


def normalize_date(value: str) -> str:
    """Приводит дату к формату ДД.ММ.ГГГГ; если не дата — возвращает как есть."""
    s = (value or "").strip()
    m = _DATE_RE.search(s)
    if not m:
        return s
    d, mo, y = m.group(1), m.group(2), m.group(3)
    if len(y) == 2:
        yy = int(y)
        pivot = datetime.now().year % 100  # 00..pivot -> 20xx, иначе 19xx
        y = f"20{yy:02d}" if yy <= pivot else f"19{yy:02d}"
    return f"{int(d):02d}.{int(mo):02d}.{y}"
