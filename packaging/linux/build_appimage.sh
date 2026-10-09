#!/usr/bin/env bash
# Сборка универсального Linux AppImage «ЛексЛока» (один файл для всех дистрибутивов).
# При запуске показывает понятные диалоги (zenity/kdialog), без терминала.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST="$ROOT/dist"
VERSION="$(grep -m1 '^version' "$ROOT/pyproject.toml" | sed -E 's/.*"(.*)".*/\1/')"

case "$(uname -m)" in
    x86_64|amd64) ARCH="x86_64" ;;
    arm64|aarch64) ARCH="aarch64" ;;
    *) echo "Ошибка: неподдерживаемая архитектура $(uname -m)." >&2; exit 1 ;;
esac

APPDIR="$DIST/LexLock.AppDir"
OUT="$DIST/LexLock-$VERSION-$ARCH.AppImage"

echo "==> Версия: $VERSION, архитектура: $ARCH"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/app"
rsync -a \
    --exclude '.venv' --exclude 'workspace' --exclude 'dist' --exclude '.git' \
    --exclude '__pycache__' --exclude '*.pyc' --exclude '.pytest_cache' \
    --exclude '.lexlock_model' --exclude '*.egg-info' \
    "$ROOT/" "$APPDIR/app/"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/bash
# «ЛексЛок» на Linux: разворачиваем проект в домашний каталог (AppImage только для
# чтения) и запускаем установку/сервер. Прогресс — через zenity/kdialog, если есть.
set -u
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
TARGET="${LEXLOCK_DIR:-$HOME/lexlock}"
LOG="$HOME/.lexlock-install.log"
URL="http://127.0.0.1:8765"

info()  { command -v zenity >/dev/null && zenity --info --title="ЛексЛок" --text="$1" --width=420 2>/dev/null; }
error() { command -v zenity >/dev/null && zenity --error --title="ЛексЛок" --text="$1\n\nЖурнал: $LOG" --width=460 2>/dev/null; }
ask()   { command -v zenity >/dev/null && zenity --question --title="ЛексЛок" --text="$1" --width=440 2>/dev/null; }
note()  { command -v notify-send >/dev/null && notify-send "ЛексЛок" "$1" 2>/dev/null; }

if [ ! -x "$TARGET/.venv/bin/python" ]; then
    info "ЛексЛок установится и откроется в браузере.\nПервый запуск скачает компоненты и модель (~2 ГБ)." || exit 0
    if [ ! -d "$TARGET" ]; then
        mkdir -p "$TARGET"
        cp -R "$HERE/app/." "$TARGET/"
    fi
    cd "$TARGET" || exit 1
    if ! ./install.sh >>"$LOG" 2>&1; then
        error "Не удалось установить. Проверьте интернет и попробуйте снова."
        exit 1
    fi
fi

cd "$TARGET" || exit 1
( ./run.sh --no-browser >>"$LOG" 2>&1 & )
for _ in $(seq 1 40); do
    curl -s --max-time 1 "$URL/api/health" >/dev/null 2>&1 && break
    sleep 1
done
command -v xdg-open >/dev/null && xdg-open "$URL" >/dev/null 2>&1 || true
note "ЛексЛок запущен — открываю браузер."
EOF
chmod +x "$APPDIR/AppRun"
cp "$ROOT/packaging/linux/lexlock.desktop" "$APPDIR/lexlock.desktop"
cp "$ROOT/packaging/linux/lexlock.png" "$APPDIR/lexlock.png"

TOOL="$(mktemp -d)/appimagetool-$ARCH.AppImage"
echo "==> Скачиваю appimagetool"
curl -fL --retry 3 -o "$TOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
chmod +x "$TOOL"

echo "==> Собираю $OUT"
APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$ARCH" "$TOOL" "$APPDIR" "$OUT"

echo
echo "Готово: $OUT"
