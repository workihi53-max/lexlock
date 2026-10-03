"""Тесты подбора релевантных фрагментов (RAG-lite)."""

from __future__ import annotations

from vanya.rag import select_relevant, split_blocks


def test_short_text_unchanged():
    assert select_relevant("короткий текст", "вопрос", 100) == "короткий текст"


def test_split_blocks():
    assert split_blocks("a\n\n b \n\n") == ["a", "b"]


def test_selects_relevant_block_and_preserves_order():
    text = "шапка договора\n\n" + ("блок про неустойку " * 50) + "\n\n" + ("мусор " * 50)
    out = select_relevant(text, "какая неустойка предусмотрена?", 400)
    assert len(out) <= 400
    assert "неустойку" in out  # релевантный блок выбран
    assert out.startswith("шапка")  # первый блок и порядок сохранены
    assert "мусор" not in out


def test_no_query_terms_falls_back_to_truncation():
    text = "abcdef " * 100
    assert select_relevant(text, "", 50) == text[:50]


def test_no_matching_block_falls_back_to_start():
    text = "первый блок\n\n" + ("второй " * 100)
    out = select_relevant(text, "совершенно другое", 30)
    assert len(out) <= 30
    assert out.startswith("первый")
