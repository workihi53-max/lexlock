"""Запуск «ЛексЛока»: сервер в фоне + иконка в трее (если доступна).

Используется вместо ``python -m app.server``, чтобы у пользователя была иконка
в трее с пунктами «Открыть» и «Остановить» и понятный способ закрыть приложение.
Если трей недоступен (нет библиотеки/графического окружения) — приложение просто
работает как раньше.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

import uvicorn

from app.server import create_app
from lexlock import portcheck
from lexlock.config import Config, load_config


def _exit_soon() -> None:
    """Завершает процесс чуть позже — чтобы успел уйти ответ браузеру/трею."""
    time.sleep(0.3)
    os._exit(0)


def _notify(text: str) -> None:
    """Сообщение пользователю: в терминал и, если есть, в окно системы."""
    print(f"[ЛексЛок] {text}", file=sys.stderr)
    try:
        if sys.platform == "darwin":
            script = f'display dialog "{text}" with title "ЛексЛок" buttons {{"OK"}}'
            subprocess.run(["osascript", "-e", script], timeout=120, check=False)
        elif sys.platform.startswith("win"):
            import ctypes

            getattr(ctypes, "windll").user32.MessageBoxW(0, text, "ЛексЛок", 0x40)
        elif shutil.which("kdialog"):
            subprocess.run(["kdialog", "--title", "ЛексЛок", "--msgbox", text], timeout=120, check=False)
        elif shutil.which("zenity"):
            subprocess.run(["zenity", "--info", "--title=ЛексЛок", f"--text={text}"], timeout=120, check=False)
    except Exception:
        pass


def _choose_port(config: Config, no_browser: bool) -> Config | None:
    """Возвращает конфиг с рабочим портом или None, если запускать не нужно."""
    port = config.port
    if portcheck.port_is_free(port):
        return config
    if portcheck.is_lexlock(port):
        # Уже запущен: просто показываем окно, второй сервер не нужен.
        if not no_browser:
            webbrowser.open(f"http://127.0.0.1:{port}")
        return None
    new_port = portcheck.pick_free_port(port)
    if new_port is None:
        _notify(f"Порт {port} занят другой программой, свободный порт не нашёлся. "
                "Закройте эту программу или задайте другой порт: LEXLOCK_PORT=9000.")
        sys.exit(1)
    _notify(f"Порт {port} занят другой программой. ЛексЛок откроется на "
            f"http://127.0.0.1:{new_port}")
    return dataclasses.replace(config, port=new_port)


def main() -> None:
    no_browser = "--no-browser" in sys.argv[1:]
    config = _choose_port(load_config(), no_browser)
    if config is None:
        return
    app = create_app(config)
    url = f"http://127.0.0.1:{config.port}"

    def serve() -> None:
        uvicorn.run(app, host="127.0.0.1", port=config.port, log_level="warning")

    server = threading.Thread(target=serve, daemon=True)
    server.start()

    # Ждём, пока сервер ответит на /api/health.
    import httpx

    for _ in range(60):
        if not server.is_alive():
            _notify("Сервер ЛексЛока не запустился. Подробности в журнале.")
            sys.exit(1)
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
