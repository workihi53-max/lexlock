"""Тесты OCR: без установленного Tesseract, на заглушках."""

from __future__ import annotations

import pytest

from lexlock import docs, ocr


def test_available_false_when_missing(monkeypatch):
    monkeypatch.setattr(ocr.shutil, "which", lambda name: None)
    assert ocr.available() is False


def test_ocr_image_without_tesseract_raises(monkeypatch):
    monkeypatch.setattr(ocr.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError):
        ocr.ocr_image("scan.png")


def test_needs_ocr():
    assert ocr.needs_ocr("") is True
    assert ocr.needs_ocr("короткий") is True
    assert ocr.needs_ocr("достаточно длинный текст для текстового слоя PDF") is False


def test_read_document_image_uses_ocr(tmp_path, monkeypatch):
    img = tmp_path / "scan.png"
    img.write_bytes(b"\x89PNG\r\n")
    monkeypatch.setattr(docs.ocr, "ocr_image", lambda p, lang=ocr.DEFAULT_LANG: "текст со скана")
    assert docs.read_document(img) == "текст со скана"


def test_read_document_scanned_pdf_uses_ocr(tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(docs, "_read_pdf", lambda p: "")
    monkeypatch.setattr(docs.ocr, "available", lambda: True)
    monkeypatch.setattr(docs.ocr, "ocr_pdf", lambda p: "OCR страницы")
    assert docs.read_document(pdf) == "OCR страницы"


def test_read_document_pdf_without_ocr_keeps_text(tmp_path, monkeypatch):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(docs, "_read_pdf", lambda p: "обычный текстовый слой договора")
    monkeypatch.setattr(docs.ocr, "available", lambda: True)
    assert docs.read_document(pdf) == "обычный текстовый слой договора"
