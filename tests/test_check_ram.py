"""Тесты визарда модели в scripts/check_ram.py (импорт по пути, без пакета)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "check_ram", Path(__file__).resolve().parent.parent / "scripts" / "check_ram.py"
)
check_ram = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(check_ram)


def test_recommend_full_machine_uses_3b():
    assert check_ram.recommend_model(8.0) == "qwen2.5:3b"


def test_recommend_low_memory_uses_1_5b():
    assert check_ram.recommend_model(1.6) == "qwen2.5:1.5b"


def test_recommend_boundary():
    assert check_ram.recommend_model(5.0) == "qwen2.5:3b"
    assert check_ram.recommend_model(4.9) == "qwen2.5:1.5b"


def test_estimate_model_ram_known_and_unknown():
    assert check_ram.estimate_model_ram("qwen2.5:3b") == 2.5
    assert check_ram.estimate_model_ram("что-то:7b") == 6.0
