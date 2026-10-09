"""Юнит-тесты извлечения реквизитов (lexlock.extract)."""

from __future__ import annotations

import pytest

from lexlock import extract


@pytest.mark.parametrize(
    ("text", "field", "expected"),
    [
        ("ФИО: Иванов Иван Иванович", "fio", "Иванов Иван Иванович"),
        ("Ф.И.О.: Петрова Анна Сергеевна", "fio", "Петрова Анна Сергеевна"),
        ("Фамилия: Иванов", "familiya", "Иванов"),
        ("Фамилия: Салтыков-Щедрин", "familiya", "Салтыков-Щедрин"),
        ("Имя: Иван", "imya", "Иван"),
        ("Отчество: Иванович", "otchestvo", "Иванович"),
        ("Дата рождения: 12.03.1985", "data_rozhdeniya", "12.03.1985"),
        ("родился 05.07.1990 г.р.", "data_rozhdeniya", "05.07.1990"),
        ("Серия: 4512", "pasport_seriya", "4512"),
        ("Серия: 45 12", "pasport_seriya", "4512"),
        ("Номер: 345678", "pasport_nomer", "345678"),
        ("паспорт серия 4512 № 345678", "pasport_nomer", "345678"),
        ("Кем выдан: ОВД района Иваново г. Москвы", "pasport_vydan", "ОВД района Иваново г. Москвы"),
        ("Дата выдачи: 20.04.2005", "pasport_data", "20.04.2005"),
        ("Код подразделения: 123-456", "pasport_kod", "123-456"),
        ("Адрес регистрации: г. Москва, ул. Ленина, д. 5, кв. 10", "adres_registracii", "г. Москва, ул. Ленина, д. 5, кв. 10"),
        ("ИНН: 7701234567", "inn", "7701234567"),
        ("ИНН 123456789012", "inn", "123456789012"),
        ("ОГРН: 1127746123456", "ogrn", "1127746123456"),
        ("ОГРНИП: 304770000123456", "ogrn", "304770000123456"),
        ("КПП: 770101001", "kpp", "770101001"),
        ("Наименование организации: ООО «Ромашка»", "organizaciya", "ООО «Ромашка»"),
        ("ООО «Вектор» — исполнитель", "organizaciya", "ООО «Вектор»"),
        ("Юридический адрес: 117000, г. Москва, ул. Тверская, д. 1", "yuridicheskiy_adres", "117000, г. Москва, ул. Тверская, д. 1"),
        ("Банк: ПАО Сбербанк", "bank", "ПАО Сбербанк"),
        ("БИК: 044525225", "bik", "044525225"),
        ("Расчётный счёт: 40702810000000000000", "raschetny_schet", "40702810000000000000"),
        ("р/с 40702810000000000000", "raschetny_schet", "40702810000000000000"),
        ("Корреспондентский счёт: 30101810400000000225", "korr_schet", "30101810400000000225"),
        ("к/с 30101810400000000225", "korr_schet", "30101810400000000225"),
        ("Телефон: +7 (495) 123-45-67", "telefon", "+7 (495) 123-45-67"),
        ("Email: info@example.com", "email", "info@example.com"),
        ("Должность: Генеральный директор", "dolzhnost", "Генеральный директор"),
        ("Дата договора: 01.06.2024", "data_dogovora", "01.06.2024"),
        ("Договор № 15/2024 от 01.06.2024", "data_dogovora", "01.06.2024"),
        ("Договор № 15/2024", "nomer_dogovora", "15/2024"),
        ("Сумма договора: 1 000 000 руб.", "summa", "1 000 000 руб."),
    ],
)
def test_extract_field(text, field, expected):
    found = extract.extract_requisites(text)
    assert found.get(field) == expected


def test_whitespace_normalized():
    text = "Наименование организации:   ООО   «Ромашка»   \n  что-то ещё"
    found = extract.extract_requisites(text)
    assert found["organizaciya"] == "ООО «Ромашка»"


@pytest.mark.parametrize(
    ("text", "field", "expected"),
    [
        ("Серия паспорта: 45", "pasport_seriya", "45"),
        ("Серия паспорта: 4512", "pasport_seriya", "4512"),
        ("Серия 45 12", "pasport_seriya", "4512"),
        ("Номер паспорта: 123456", "pasport_nomer", "123456"),
        ("№ паспорта: 123456", "pasport_nomer", "123456"),
        ("Номер: 123456", "pasport_nomer", "123456"),
    ],
)
def test_passport_formats(text, field, expected):
    found = extract.extract_requisites(text)
    assert found.get(field) == expected


def test_passport_series_and_number_combined():
    found = extract.extract_requisites("Серия и номер паспорта: 4512 123456")
    assert found["pasport_seriya"] == "4512"
    assert found["pasport_nomer"] == "123456"


def test_fio_from_parts():
    text = "Фамилия: Иванов\nИмя: Иван\nОтчество: Иванович"
    found = extract.extract_requisites(text)
    assert found["fio"] == "Иванов Иван Иванович"


def test_missing_fields():
    found = {"inn": "7701234567"}
    missing = extract.missing_fields(found)
    assert "inn" not in missing
    assert "ogrn" in missing
    assert len(missing) == len(extract.FIELDS) - 1


def test_empty_text_returns_empty():
    assert extract.extract_requisites("") == {}
    assert extract.extract_requisites("ничего нет") == {}
