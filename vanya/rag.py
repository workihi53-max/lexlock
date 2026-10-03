"""Подбор релевантных фрагментов документа под запрос (RAG-lite, без зависимостей).

Модель получает не первые N символов, а наиболее релевантные под вопрос блоки.
Это заметно повышает качество на длинных договорах, где важный пункт в конце.
"""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[а-яёa-z0-9]{3,}", re.IGNORECASE)

# Частые слова, не несущие смысла для поиска.
_STOP = {
    "что", "как", "это", "для", "или", "его", "она", "они", "the", "and",
    "договор", "документ", "есть", "быть", "который", "которая", "также",
}


def _terms(text: str) -> set[str]:
    """Корни слов (первые 5 букв) — грубо, но ловит падежи без зависимостей."""
    return {
        word.lower()[:5]
        for word in _WORD_RE.findall(text)
        if word.lower() not in _STOP
    }


def split_blocks(text: str) -> list[str]:
    """Делит текст на абзацы по пустым строкам."""
    return [block.strip() for block in re.split(r"\n\s*\n", text or "") if block.strip()]


def select_relevant(text: str, query: str, limit_chars: int) -> str:
    """Возвращает не более limit_chars символов: релевантные блоки + первый блок.

    Порядок фрагментов сохраняется как в документе. Если совпадений нет,
    поведение совпадает с простой обрезкой (первые limit_chars символов).
    """
    text = text or ""
    if limit_chars <= 0 or len(text) <= limit_chars:
        return text

    blocks = split_blocks(text)
    query_terms = _terms(query)
    if not blocks or not query_terms:
        return text[:limit_chars]

    scored: list[tuple[float, int, str]] = []
    for index, block in enumerate(blocks):
        overlap = len(query_terms & _terms(block))
        bonus = 1.0 if index == 0 else 0.0  # в начале обычно реквизиты и стороны
        scored.append((overlap + bonus, index, block))

    chosen: list[tuple[int, str]] = []
    total = 0
    for score, index, block in sorted(scored, key=lambda item: (-item[0], item[1])):
        if score <= 0 and chosen:
            continue  # нерелевантные блоки не добавляем, если уже что-то есть
        room = limit_chars - total
        if room <= 0:
            break
        piece = block if len(block) <= room else block[:room]
        chosen.append((index, piece))
        total += len(piece) + 2  # + разделитель "\n\n"

    chosen.sort(key=lambda item: item[0])
    return "\n\n".join(piece for _, piece in chosen)[:limit_chars]
