#!/usr/bin/env bash
# Сборка универсального Linux AppImage «Вани» (один файл для всех дистрибутивов).
# Собирается на Linux. appimagetool скачается автоматически.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST="$ROOT/dist"
VERSION="$(grep -m1 '^version' "$ROOT/pyproject.toml" | sed -E 's/.*"(.*)".*/\1/')"

case "$(uname -m)" in
    x86_64|amd64) ARCH="x86_64" ;;
    arm64|aarch64) ARCH="aarch64" ;;
    *) echo "Ошибка: неподдерживаемая архитектура $(uname -m)." >&2; exit 1 ;;
esac

APPDIR="$DIST/Vanya.AppDir"
OUT="$DIST/Vanya-$VERSION-$ARCH.AppImage"

echo "==> Версия: $VERSION, архитектура: $ARCH"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/app"
rsync -a \
    --exclude '.venv' --exclude 'workspace' --exclude 'dist' --exclude '.git' \
    --exclude '__pycache__' --exclude '*.pyc' --exclude '.pytest_cache' \
    --exclude '.vanya_model' --exclude '*.egg-info' \
    "$ROOT/" "$APPDIR/app/"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/bash
# «Ваня»: разворачиваем проект в домашний каталог (AppImage только для чтения)
# и запускаем установку/сервер оттуда.
set -e
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
TARGET="${VANYA_DIR:-$HOME/vanya-legal-vault}"
if [ ! -x "$TARGET/.venv/bin/python" ]; then
    echo "Первый запуск: разворачиваю «Ваню» в $TARGET"
    mkdir -p "$TARGET"
    cp -R "$HERE/app/." "$TARGET/"
fi
cd "$TARGET"
if [ ! -x .venv/bin/python ]; then
    ./install.sh
fi
exec ./run.sh
EOF
chmod +x "$APPDIR/AppRun"
cp "$ROOT/packaging/linux/vanya.desktop" "$APPDIR/vanya.desktop"
cp "$ROOT/packaging/linux/vanya.png" "$APPDIR/vanya.png"

TOOL="$DIST/appimagetool-$ARCH.AppImage"
if [ ! -x "$TOOL" ]; then
    echo "==> Скачиваю appimagetool"
    curl -fL --retry 3 -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
    chmod +x "$TOOL"
fi

echo "==> Собираю $OUT"
# На CI без FUSE запускаем через извлечение.
APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$ARCH" "$TOOL" "$APPDIR" "$OUT"

echo
echo "Готово: $OUT"
echo "Запуск: chmod +x \"$OUT\" && ./$(basename "$OUT")"
