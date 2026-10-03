#!/usr/bin/env python3
"""Проверка ресурсов машины перед запуском локальной LLM (Ollama, CPU)."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

GB = 1024 ** 3

# Грубая оценка ОЗУ модели в ГБ (по размеру в названии).
MODEL_RAM_GB = {
    "0.5b": 0.8,
    "1.5b": 1.5,
    "3b": 2.5,
    "7b": 6.0,
    "8b": 7.0,
    "14b": 12.0,
    "32b": 24.0,
}
DEFAULT_MODEL = "qwen2.5:3b"


def estimate_model_ram(model: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)b", model.lower())
    if not m:
        return MODEL_RAM_GB["3b"]
    key = m.group(1) + "b"
    return MODEL_RAM_GB.get(key, max(1.0, float(m.group(1)) * 0.8))


def _read_meminfo() -> dict[str, int]:
    """Linux: разбирает /proc/meminfo (значения в кБ)."""
    vals: dict[str, int] = {}
    with open("/proc/meminfo", encoding="utf-8") as f:
        for line in f:
            name, rest = line.split(":", 1)
            vals[name.strip()] = int(rest.split()[0])  # в кБ
    return vals


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def _memory_macos() -> tuple[float, float, float, float]:
    """macOS: (ОЗУ всего, свободно, swap всего, swap свободно) в ГБ.

    Свободной считаем сумму free + inactive + speculative страниц: именно её
    система готова отдать под процессы, тогда как vm_stat «free» занижен.
    """
    total_b = int(_run(["sysctl", "-n", "hw.memsize"]).strip())
    page_size = int(_run(["sysctl", "-n", "hw.pagesize"]).strip() or "4096")
    pages: dict[str, int] = {}
    for line in _run(["vm_stat"]).splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        digits = re.sub(r"[^0-9]", "", rest)
        if digits:
            pages[key.strip()] = int(digits)
    free_pages = (
        pages.get("Pages free", 0)
        + pages.get("Pages inactive", 0)
        + pages.get("Pages speculative", 0)
    )
    ram_total_gb = total_b / GB
    ram_free_gb = free_pages * page_size / GB

    swap_total_gb = swap_free_gb = 0.0
    try:
        swap = _run(["sysctl", "-n", "vm.swapusage"])
        m_total = re.search(r"total\s*=\s*([\d.]+)([MG])", swap)
        m_free = re.search(r"free\s*=\s*([\d.]+)([MG])", swap)

        def _to_gb(match: re.Match[str] | None) -> float:
            if not match:
                return 0.0
            value = float(match.group(1))
            return value / 1024 if match.group(2) == "M" else value

        swap_total_gb = _to_gb(m_total)
        swap_free_gb = _to_gb(m_free)
    except (subprocess.SubprocessError, ValueError):
        pass
    return ram_total_gb, ram_free_gb, swap_total_gb, swap_free_gb


def _memory_linux() -> tuple[float, float, float, float]:
    mem = _read_meminfo()
    ram_total_kb = mem.get("MemTotal", 0)
    ram_avail_kb = mem.get("MemAvailable", mem.get("MemFree", 0))
    swap_total_kb = mem.get("SwapTotal", 0)
    swap_free_kb = mem.get("SwapFree", 0)
    return (
        ram_total_kb * 1024 / GB,
        ram_avail_kb * 1024 / GB,
        swap_total_kb * 1024 / GB,
        swap_free_kb * 1024 / GB,
    )


def collect() -> dict:
    """Собирает ресурсы машины на Linux и macOS."""
    if sys.platform == "darwin":
        ram_total, ram_free, swap_total, swap_free = _memory_macos()
    else:
        ram_total, ram_free, swap_total, swap_free = _memory_linux()
    root = Path(__file__).resolve().parent.parent
    du = shutil.disk_usage(root)
    return {
        "ram_total_gb": round(ram_total, 2),
        "ram_free_gb": round(ram_free, 2),
        "swap_total_gb": round(swap_total, 2),
        "swap_free_gb": round(swap_free, 2),
        "disk_total_gb": round(du.total / GB, 2),
        "disk_free_gb": round(du.free / GB, 2),
        "cores": os.cpu_count() or 0,
    }


def verdict(free_gb: float, required_gb: float) -> tuple[str, bool]:
    """Возвращает (строка-вердикт, ok). ok=False — рискованно (exit 1)."""
    if free_gb < 2.5 or free_gb < required_gb:
        return "⚠️ рискованно: модель может уронить систему в своп", False
    if free_gb >= 5.0:
        return "✅ можно запускать модель", True
    return f"⚠️ впритык: свободно {free_gb:.1f} ГБ, модели нужно ~{required_gb:.1f} ГБ", True


def main() -> int:
    ap = argparse.ArgumentParser(description="Проверка ресурсов перед запуском модели")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="имя модели Ollama (для оценки ОЗУ)")
    ap.add_argument("--json", action="store_true", help="вывод в формате JSON")
    args = ap.parse_args()

    info = collect()
    required = estimate_model_ram(args.model)
    text, ok = verdict(info["ram_free_gb"], required)

    data = {
        "model": args.model,
        "model_ram_gb": round(required, 2),
        **info,
        "ollama_api_tags_checked": False,
        "verdict": text,
        "ok": ok,
    }

    if args.json:
        print(json.dumps(data, ensure_ascii=False))
    else:
        print("Проверка ресурсов для локальной модели")
        print(f"  Модель:          {args.model} (~{required:.1f} ГБ ОЗУ)")
        print(f"  ОЗУ всего:       {info['ram_total_gb']:.1f} ГБ")
        print(f"  ОЗУ свободно:    {info['ram_free_gb']:.1f} ГБ")
        print(f"  Swap:            {info['swap_total_gb']:.1f} ГБ всего, {info['swap_free_gb']:.1f} ГБ свободно")
        print(f"  Диск проекта:    {info['disk_free_gb']:.1f} ГБ свободно (всего {info['disk_total_gb']:.1f} ГБ)")
        print(f"  Ядра CPU:        {info['cores']}")
        print("  Порт /api/tags:  не проверяется")
        print()
        print(f"Вердикт: {text}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
