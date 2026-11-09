"""Запуск «ЛексЛока»: сервер в фоне + иконка в трее (если доступна).

Используется вместо ``python -m app.server``, чтобы у пользователя была иконка
в трее с пунктами «Открыть» и «Остановить» и понятный способ закрыть приложение.
Если трей недоступен (нет библиотеки/графического окружения) — приложение просто
работает как раньше.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser

import uvicorn

from app.server import create_app
from lexlock.config import load_config


def _exit_soon() -> None:
    """Завершает процесс чуть позже — чтобы успел уйти ответ браузеру/трею."""
    time.sleep(0.3)
    os._exit(0)


def main() -> None:
    no_browser = "--no-browser" in sys.argv[1:]
    config = load_config()
    app = create_app(config)
    url = f"http://127.0.0.1:{config.port}"

    def serve() -> None:
        uvicorn.run(app, host="127.0.0.1", port=config.port, log_level="warning")

    threading.Thread(target=serve, daemon=True).start()

    # Ждём, пока сервер ответит на /api/health.
    import httpx

    for _ in range(60):
        try:
            if httpx.get(f"{url}/api/health", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(1)

    if not no_browser:
        webbrowser.open(url)

    try:
        from lexlock import tray

        if tray.available():
            tray.run(url, on_stop=_exit_soon)
            return
    except Exception:
        pass

    # Без трея — держим процесс живым, пока работает сервер.
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        _exit_soon()


if __name__ == "__main__":
    main()
