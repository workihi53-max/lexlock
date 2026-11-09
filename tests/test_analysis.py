"""Тесты точных задач: классификация, паспорт документа, очистка OCR."""

from __future__ import annotations

from lexlock import analysis, scenarios
from lexlock.llm import LLMError


def test_classify_document_types():
    assert analysis.classify_document("Договор оказания услуг, стороны обязуются.") == "договор"
    assert analysis.classify_document("Серия паспорта 45 12, номер 123456, кем выдан.") == "паспорт"
    assert analysis.classify_document("ИНН 7712345678, КПП 771234567, ОГРН 1123.") == "реквизиты"
    assert analysis.classify_document("Настоящей доверенностью уполномочиваю.") == "доверенность"
    assert analysis.classify_document("Истец, ответчик, арбитражный суд.") == "исковое заявление"
    assert analysis.classify_document("Акт сдачи-приёмки выполненных работ.") == "акт"
    assert analysis.classify_document("Просто произвольный текст.") == "иное"


def test_document_passport_extracts_fields():
    text = (
        "Договор № 001 от 12.05.2025\n"
        "1. Предмет договора\n"
        "1.1. Исполнитель обязуется оказать услуги по разработке ПО.\n"
        "Полное наименование: ООО «Ромашка»\n"
        "Сумма договора: 100 000 рублей"
    )
    p = analysis.document_passport(text)
    assert p["type"] == "договор"
    assert p["number"] == "001"
    assert p["date"] == "12.05.2025"
    assert "ООО «Ромашка»" in p["parties"]
    assert "100 000 рублей" in p["sum"]
    assert "Исполнитель обязуется" in p["subject"]


def test_clean_ocr_text_deterministic():
    dirty = "ДОГОВОР №\n001\n\n\nИсполни-\nтель обязуется   оказать  услуги."
    cleaned, model_used = analysis.clean_ocr_text(dirty)
    assert model_used is False
    assert "Исполнитель" in cleaned
    assert "  " not in cleaned
    assert "\n\n\n" not in cleaned


def test_clean_ocr_text_with_model(tmp_path, monkeypatch):
    class EchoLLM:
        def chat(self, messages, tools=None):
            return type("R", (), {"content": "Исправленный текст"})

    monkeypatch.setattr(analysis, "LLM", None)
    # Через прямой вызов с фейковой моделью.
    cleaned, model_used = analysis.clean_ocr_text("сырой текст", llm=EchoLLM())
    assert model_used is True
    assert cleaned == "Исправленный текст"


def test_clean_ocr_text_model_failure_falls_back():
    class FailingLLM:
        def chat(self, messages, tools=None):
            raise LLMError("модель недоступна")

    cleaned, model_used = analysis.clean_ocr_text("Договор\nтекст", llm=FailingLLM())
    assert model_used is False
    assert "Договор" in cleaned


def test_recognize_document_deterministic(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("LEXLOCK_WORKSPACE", str(ws))
    (ws / "doc.txt").write_text(
        "Договор № 7. Предмет: услуги. Полное наименование: ООО «Тест».",
        encoding="utf-8",
    )
    result = scenarios.recognize_document("doc.txt")
    assert result["ok"] is True
    assert result["ocr"] is False
    assert result["type"] == "договор"
    assert any("Тест" in p for p in result["parties"])
