"""Тесты чек-листов договоров и сценария check_contract."""

from __future__ import annotations

from vanya import checklists, scenarios


def test_detect_contract_type():
    assert checklists.detect_contract_type(
        "Договор поставки товара, поставщик обязуется"
    ) == "поставка"
    assert checklists.detect_contract_type(
        "Аренда помещения, арендодатель передаёт"
    ) == "аренда"


def test_detect_defaults_to_uslugi():
    assert checklists.detect_contract_type("некий текст без маркеров") == "услуги"


def test_evaluate_presence():
    items = checklists.evaluate("Цена договора и срок оплаты, подписан акт", "услуги")
    by_code = {item["code"]: item for item in items}
    assert by_code["cena"]["present"] is True
    assert by_code["otvet"]["present"] is False  # нет ответственности


def test_check_contract_scenario(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("VANYA_WORKSPACE", str(ws))
    (ws / "d.txt").write_text(
        "Договор оказания услуг. Цена и срок оплаты. Акт сдачи-приёмки.",
        encoding="utf-8",
    )
    result = scenarios.check_contract("d.txt")
    assert result["ok"] is True
    assert result["contract_type"] == "услуги"
    assert 0 <= result["score"] <= 100
    assert "ответственность" in " ".join(result["missing"]).lower()


def test_check_contract_explicit_type(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("VANYA_WORKSPACE", str(ws))
    (ws / "d.txt").write_text("произвольный текст", encoding="utf-8")
    result = scenarios.check_contract("d.txt", "заём")
    assert result["contract_type"] == "заём"


def test_check_contract_read_error(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("VANYA_WORKSPACE", str(ws))
    result = scenarios.check_contract("нет.txt")
    assert result["ok"] is False
