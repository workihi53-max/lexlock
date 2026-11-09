"""Опциональная иконка в системном трее (pystray).

Если библиотека недоступна или нет графического окружения — приложение работает
без трея, ошибки не всплывают наружу. Меню: «Открыть» (браузер) и «Остановить».
"""

from __future__ import annotations

import webbrowser
from typing import Callable


def available() -> bool:
    """True, если можно показать иконку в трее."""
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


def _icon_image():
    """Пиксельная иконка-книга 64x64 (та же палитра, что у приложения)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # тёмная обводка
    d.rectangle([10, 12, 54, 52], fill=(31, 42, 55, 255))
    # обложка
    d.rectangle([13, 15, 51, 49], fill=(180, 68, 31, 255))
    # страницы справа
    d.rectangle([44, 15, 51, 49], fill=(245, 243, 238, 255))
    # закладка
    d.rectangle([27, 15, 31, 27], fill=(156, 107, 30, 255))
    return img


def run(open_url: str, on_stop: Callable[[], None]) -> None:
    """Запускает иконку в трее (блокирующая функция, обычно — главный поток)."""
    import pystray

    def _open(icon, item) -> None:  # noqa: ARG001
        webbrowser.open(open_url)

    def _stop(icon, item) -> None:  # noqa: ARG001
        try:
            on_stop()
        finally:
            icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Открыть ЛексЛок", _open, default=True),
        pystray.MenuItem("Остановить", _stop),
    )
    icon = pystray.Icon("lexlock", _icon_image(), "ЛексЛок", menu)
    icon.run()
