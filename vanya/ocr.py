"""Локальный OCR (Tesseract) для сканов PDF и изображений. Русский язык.

Работает офлайн: Tesseract — системный бинарник, никаких облачных сервисов.
OCR PDF дополнительно требует PyMuPDF (optional extra `.[ocr]`), чтобы
отрисовать страницы в изображения. Если OCR недоступен, приложение продолжает
работать и честно сообщает об этом.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
DEFAULT_LANG = "rus+eng"
_MIN_TEXT_CHARS = 20


def tesseract_path() -> str | None:
    return shutil.which("tesseract")


def available() -> bool:
    return tesseract_path() is not None


def _run_tesseract(image_path: str | Path, lang: str = DEFAULT_LANG) -> str:
    exe = tesseract_path()
    if not exe:
        raise RuntimeError("Tesseract не установлен (см. packaging/README.md)")
    proc = subprocess.run(
        [exe, str(image_path), "stdout", "-l", lang],
        capture_output=True,
        timeout=300,
    )
    if proc.returncode != 0:
        error = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(error or "ошибка tesseract")
    return proc.stdout.decode("utf-8", errors="replace")


def ocr_image(path: str | Path, lang: str = DEFAULT_LANG) -> str:
    """Распознаёт текст на изображении."""
    return _run_tesseract(path, lang)


def ocr_pdf(path: str | Path, lang: str = DEFAULT_LANG, dpi: int = 200) -> str:
    """Отрисовывает страницы PDF и распознаёт их через Tesseract."""
    try:
        import pymupdf  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - зависит от окружения
        raise RuntimeError(
            "Для OCR PDF установите extra: pip install -e '.[ocr]'"
        ) from exc

    parts: list[str] = []
    with pymupdf.open(str(path)) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                pix.save(str(tmp_path))
                parts.append(_run_tesseract(tmp_path, lang))
            finally:
                tmp_path.unlink(missing_ok=True)
    return "\n".join(part for part in parts if part.strip())


def needs_ocr(text: str) -> bool:
    """Текст слишком короткий для PDF с текстовым слоем — вероятно, это скан."""
    return len((text or "").strip()) < _MIN_TEXT_CHARS
