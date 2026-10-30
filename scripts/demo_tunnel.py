#!/usr/bin/env python3
"""Демо-туннель: публичный https-URL на локальный ЛексЛок + QR-код.

Запускать при уже поднятом приложении (./run.sh в другом терминале):

    .venv/bin/python scripts/demo_tunnel.py

Поднимает cloudflared quick tunnel, печатает публичную ссылку и QR-код
(в терминал и в demo_qr.png). Приложение и Ollama остаются локальными.
"""

from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import segno

REPO_ROOT = Path(__file__).resolve().parent.parent
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
QR_PNG = REPO_ROOT / "demo_qr.png"


def find_cloudflared() -> str | None:
    path = shutil.which("cloudflared")
    if path:
        return path
    home = Path.home() / ".local" / "bin" / "cloudflared"
    return str(home) if home.is_file() else None


def check_local_app(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=3):
            return True
    except (urllib.error.URLError, OSError):
        return False


def main() -> int:
    port = int(os.environ.get("LEXLOCK_PORT", "8765"))

    if not check_local_app(port):
        print(f"ЛексЛок не отвечает на 127.0.0.1:{port} — сначала запусти ./run.sh")
        return 1

    binary = find_cloudflared()
    if not binary:
        print("cloudflared не найден: https://developers.cloudflare.com/cloudflare-one/"
              "networks/how-to-tunnel-quick-tunnel/")
        return 1

    print(f"Поднимаю туннель на http://127.0.0.1:{port} ...")
    proc = subprocess.Popen(
        [binary, "tunnel", "--url", f"http://127.0.0.1:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    lines: queue.Queue[str | None] = queue.Queue()

    def pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=pump, daemon=True).start()

    url: str | None = None
    while True:
        try:
            line = lines.get(timeout=5)
        except queue.Empty:
            if proc.poll() is not None:
                print("cloudflared завершился до появления ссылки.")
                return 1
            continue
        if line is None:
            print("Поток логов cloudflared закрылся.")
            return 1
        match = URL_RE.search(line)
        if match and url is None:
            url = match.group(0)

        if url:
            break

    assert url is not None
    qr = segno.make(url, error="m")
    qr.save(QR_PNG, scale=8, border=4)
    print()
    print(f"Публичная ссылка: {url}")
    print(f"QR сохранён:      {QR_PNG}")
    print()
    qr.terminal(border=2)
    print()
    print("Эксперты сканируют QR — работают через интернет на этот ноутбук.")
    print("Нажми Ctrl+C, чтобы остановить туннель (ссылка живёт только пока туннель жив).")
    print()

    try:
        while lines.get() is not None:
            pass
    except KeyboardInterrupt:
        pass
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
