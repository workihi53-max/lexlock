"""Извлечение реквизитов из текста. Только регулярки и нормализация, без LLM."""

from __future__ import annotations

import re

FIELDS = (
    "familiya",
    "imya",
    "otchestvo",
    "fio",
    "data_rozhdeniya",
    "pasport_seriya",
    "pasport_nomer",
    "pasport_vydan",
    "pasport_data",
    "pasport_kod",
    "adres_registracii",
    "inn",
    "ogrn",
    "kpp",
    "organizaciya",
    "yuridicheskiy_adres",
    "bank",
    "bik",
    "raschetny_schet",
    "korr_schet",
    "telefon",
    "email",
    "dolzhnost",
    "data_dogovora",
    "nomer_dogovora",
    "summa",
)

_DATE = r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"

# Паттерны по полям (метки — с границей слова, чтобы не цеплять подстроки).
_FAM = [re.compile(r"\bФамилия[:\s]+([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)", re.IGNORECASE)]
_IMYA = [re.compile(r"\bИмя[:\s]+([А-ЯЁ][а-яё]+)", re.IGNORECASE)]
_OTCH = [re.compile(r"\bОтчество[:\s]+([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)", re.IGNORECASE)]
_FIO = [
    re.compile(
        r"\b(?:Ф\.?\s*И\.?\s*О\.?|ФИО)[:\s]+"
        r"([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)",
        re.IGNORECASE,
    )
]
_DATA_ROZHD = [
    re.compile(rf"\bДата\s+рождения[:\s]+({_DATE})", re.IGNORECASE),
    re.compile(rf"\bродил(?:ся|ась)[:\s]+({_DATE})", re.IGNORECASE),
    re.compile(rf"\b({_DATE})\s*г\.?\s*р\.?", re.IGNORECASE),
]
_PASSPORT_COMBINED = [
    re.compile(
        r"\bСерия\s+и\s+номер\s+паспорта[:\s]*(\d{2}\s*\d{2}|\d{4})\s+(\d{6})\b",
        re.IGNORECASE,
    )
]
_PASPORT_SER = [
    re.compile(r"\bСерия[:\s]+(?:паспорта\s*)?[:\s]*(\d{2}\s*\d{2})\b", re.IGNORECASE),
    re.compile(r"\bСерия[:\s]+(?:паспорта\s*)?[:\s]*(\d{4})\b", re.IGNORECASE),
    re.compile(r"\bСерия[:\s]+(?:паспорта\s*)?[:\s]*(\d{2})\b", re.IGNORECASE),
]
_PASPORT_NOM = [
    re.compile(r"\bНомер[:\s]+(?:паспорта\s*)?[:\s]*(\d{6})\b", re.IGNORECASE),
    re.compile(r"№\s*(?:паспорта\s*)?[:\s]*(\d{6})\b", re.IGNORECASE),
]
_PASPORT_VYDAN = [re.compile(r"\bКем\s+выдан[:\s]+(.+?)(?=\n|$)", re.IGNORECASE)]
_PASPORT_DATA = [re.compile(rf"\bДата\s+выдачи[:\s]+({_DATE})", re.IGNORECASE)]
_PASPORT_KOD = [re.compile(r"\bКод\s+подразделения[:\s]+(\d{3}[- ]?\d{3})", re.IGNORECASE)]
_ADRES_REG = [
    re.compile(r"\bАдрес\s+регистрации[:\s]+(.+?)(?=\n|$)", re.IGNORECASE),
    re.compile(r"\bЗарегистрирован(?:а|ы)?\s+по\s+адресу[:\s]+(.+?)(?=\n|$)", re.IGNORECASE),
]
_INN = [re.compile(r"\bИНН[:\s]+(\d{12}|\d{10})\b", re.IGNORECASE)]
_OGRN = [re.compile(r"\bОГРН(?:ИП)?[:\s]+(\d{15}|\d{13})\b", re.IGNORECASE)]
_KPP = [re.compile(r"\bКПП[:\s]+(\d{9})\b", re.IGNORECASE)]
_ORG = [
    re.compile(r"\bНаименование\s+организации[:\s]+(.+?)(?=\n|$)", re.IGNORECASE),
    re.compile(r"\bПолное\s+наименование[:\s]+(.+?)(?=\n|$)", re.IGNORECASE),
    re.compile(r"\bОрганизация[:\s]+(.+?)(?=\n|$)", re.IGNORECASE),
]
_ORG_STANDALONE = re.compile(
    r"\b(?:ООО|ОАО|АО|ЗАО|ПАО|ИП)\s+«([^»]+)»", re.IGNORECASE
)
_YUR_ADRES = [re.compile(r"\bЮридический\s+адрес[:\s]+(.+?)(?=\n|$)", re.IGNORECASE)]
_BANK = [
    re.compile(r"\bБанк[:\s]+(.+?)(?=\n|$)", re.IGNORECASE),
    re.compile(r"\bНаименование\s+банка[:\s]+(.+?)(?=\n|$)", re.IGNORECASE),
]
_BIK = [re.compile(r"\bБИК[:\s]+(\d{9})\b", re.IGNORECASE)]
_RS = [
    re.compile(r"\bРасч[ёе]тный\s+сч[ёе]т[:\s]+(\d{20})\b", re.IGNORECASE),
    re.compile(r"\bр/с[:\s]+(\d{20})\b", re.IGNORECASE),
]
_KS = [
    re.compile(r"\bКорреспондентский\s+сч[ёе]т[:\s]+(\d{20})\b", re.IGNORECASE),
    re.compile(r"\bк/с[:\s]+(\d{20})\b", re.IGNORECASE),
]
_PHONE = [
    re.compile(
        r"\b(?:Телефон|Тел\.?|Моб\.?|Мобильный)[:\s]+(\+?\d[\d\s\-()]{6,}\d)",
        re.IGNORECASE,
    )
]
_EMAIL = [
    re.compile(
        r"\b(?:E-?mail|Электронная\s+почта|Эл\.?\s*почта)[:\s]+"
        r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
        re.IGNORECASE,
    )
]
_DOLZH = [re.compile(r"\bДолжность[:\s]+(.+?)(?=\n|$)", re.IGNORECASE)]
_DATA_DOG = [
    re.compile(rf"\bДата\s+договора[:\s]+({_DATE})", re.IGNORECASE),
    re.compile(rf"\bДоговор[^\n]*?\bот\s+({_DATE})", re.IGNORECASE),
]
_NOMER_DOG = [
    re.compile(r"\bДоговор\s+№\s*([\d/.\-]+)", re.IGNORECASE),
    re.compile(r"\bДоговор\s+N\s*([\d/.\-]+)", re.IGNORECASE),
]
_SUMMA = [
    re.compile(r"\bСумма\s+договора[:\s]+(.+?)(?=\n|$)", re.IGNORECASE),
    re.compile(r"\bСумма[:\s]+(.+?)(?=\n|$)", re.IGNORECASE),
    re.compile(r"\bЦена\s+договора[:\s]+(.+?)(?=\n|$)", re.IGNORECASE),
]


def _norm(value: str) -> str:
    return " ".join(value.split())


def _find(text: str, patterns: list[re.Pattern]) -> str | None:
    for pat in patterns:
        m = pat.search(text)
        if m:
            return _norm(m.group(1))
    return None


def _extract_organization(text: str) -> str | None:
    for pat in _ORG:
        m = pat.search(text)
        if m:
            return _norm(m.group(1))
    m = _ORG_STANDALONE.search(text)
    if m:
        return _norm(f"{m.group(0)}")
    return None


def extract_requisites(text: str) -> dict[str, str]:
    """Возвращает только найденные поля (значения — обрезанные строки)."""
    found: dict[str, str] = {}

    familiya = _find(text, _FAM)
    imya = _find(text, _IMYA)
    otchestvo = _find(text, _OTCH)
    if familiya:
        found["familiya"] = familiya
    if imya:
        found["imya"] = imya
    if otchestvo:
        found["otchestvo"] = otchestvo

    fio = _find(text, _FIO)
    if not fio and familiya and imya and otchestvo:
        fio = f"{familiya} {imya} {otchestvo}"
    if fio:
        found["fio"] = fio

    data_rozhdeniya = _find(text, _DATA_ROZHD)
    if data_rozhdeniya:
        found["data_rozhdeniya"] = data_rozhdeniya

    pasport_seriya: str | None = None
    pasport_nomer: str | None = None
    combined = _PASSPORT_COMBINED[0].search(text)
    if combined:
        pasport_seriya = combined.group(1).replace(" ", "")
        pasport_nomer = combined.group(2)
    else:
        pasport_seriya = _find(text, _PASPORT_SER)
        pasport_nomer = _find(text, _PASPORT_NOM)
    if pasport_seriya:
        found["pasport_seriya"] = pasport_seriya.replace(" ", "")
    if pasport_nomer:
        found["pasport_nomer"] = pasport_nomer

    pasport_vydan = _find(text, _PASPORT_VYDAN)
    if pasport_vydan:
        found["pasport_vydan"] = pasport_vydan
    pasport_data = _find(text, _PASPORT_DATA)
    if pasport_data:
        found["pasport_data"] = pasport_data
    pasport_kod = _find(text, _PASPORT_KOD)
    if pasport_kod:
        found["pasport_kod"] = pasport_kod

    adres = _find(text, _ADRES_REG)
    if adres:
        found["adres_registracii"] = adres

    inn = _find(text, _INN)
    if inn:
        found["inn"] = inn
    ogrn = _find(text, _OGRN)
    if ogrn:
        found["ogrn"] = ogrn
    kpp = _find(text, _KPP)
    if kpp:
        found["kpp"] = kpp

    organizaciya = _extract_organization(text)
    if organizaciya:
        found["organizaciya"] = organizaciya
    yur_adres = _find(text, _YUR_ADRES)
    if yur_adres:
        found["yuridicheskiy_adres"] = yur_adres

    bank = _find(text, _BANK)
    if bank:
        found["bank"] = bank
    bik = _find(text, _BIK)
    if bik:
        found["bik"] = bik
    rs = _find(text, _RS)
    if rs:
        found["raschetny_schet"] = rs
    ks = _find(text, _KS)
    if ks:
        found["korr_schet"] = ks

    telefon = _find(text, _PHONE)
    if telefon:
        found["telefon"] = telefon
    email = _find(text, _EMAIL)
    if email:
        found["email"] = email

    dolzhnost = _find(text, _DOLZH)
    if dolzhnost:
        found["dolzhnost"] = dolzhnost

    data_dogovora = _find(text, _DATA_DOG)
    if data_dogovora:
        found["data_dogovora"] = data_dogovora
    nomer_dogovora = _find(text, _NOMER_DOG)
    if nomer_dogovora:
        found["nomer_dogovora"] = nomer_dogovora

    summa = _find(text, _SUMMA)
    if summa:
        found["summa"] = summa

    return found


def missing_fields(found: dict[str, str]) -> list[str]:
    return [f for f in FIELDS if f not in found]
