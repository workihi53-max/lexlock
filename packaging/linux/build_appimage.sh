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
    --exclude 'заявка' --exclude 'ошибочки' --exclude 'promo-video' \
    --exclude 'demo_qr.png' --exclude '*.log' --exclude 'docs' \
    "$ROOT/" "$APPDIR/app/"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/bash
# «ЛексЛок» на Linux: разворачивает проект в домашний каталог (AppImage только для
# чтения) и запускает установку/сервер. Прогресс — через kdialog/zenity/xmessage.
set -u
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
TARGET="${LEXLOCK_DIR:-$HOME/lexlock}"
LOG="$HOME/.lexlock-install.log"
URL="http://127.0.0.1:8765"

# Выбираем доступный GUI-диалог: на KDE — kdialog, на GNOME — zenity, иначе xmessage.
DIALOG=""
for d in kdialog zenity xmessage; do
    command -v "$d" >/dev/null 2>&1 && { DIALOG="$d"; break; }
done

info() {
    case "$DIALOG" in
        kdialog) kdialog --title "ЛексЛок" --msgbox "$1" 2>/dev/null ;;
        zenity)  zenity --info --title="ЛексЛок" --text="$1" --width=420 2>/dev/null ;;
        xmessage) xmessage -center -buttons OK "$1" 2>/dev/null ;;
        *) echo "[info] $1" >>"$LOG" ;;
    esac
    return 0
}
error() {
    case "$DIALOG" in
        kdialog) kdialog --title "ЛексЛок" --error "$1" 2>/dev/null ;;
        zenity)  zenity --error --title="ЛексЛок" --text="$1" --width=460 2>/dev/null ;;
        xmessage) xmessage -center -buttons OK "Ошибка: $1" 2>/dev/null ;;
        *) echo "[error] $1" >>"$LOG" ;;
    esac
    return 0
}
confirm() {
    # 0 = «да». Если GUI-диалога нет — продолжаем автоматически (не блокируем).
    case "$DIALOG" in
        kdialog) kdialog --title "ЛексЛок" --yesno "$1" 2>/dev/null ;;
        zenity)  zenity --question --title="ЛексЛок" --text="$1" --width=440 2>/dev/null ;;
        xmessage) xmessage -center -buttons "Да:0,Нет:1" "$1" 2>/dev/null ;;
        *) return 0 ;;
    esac
}
note() { command -v notify-send >/dev/null 2>&1 && notify-send "ЛексЛок" "$1" 2>/dev/null || true; }

install_desktop_entry() {
    # Добавляем «ЛексЛок» в меню приложений (ярлык запускает ~/lexlock/run.sh).
    local apps="$HOME/.local/share/applications"
    local icons="$HOME/.local/share/icons/hicolor/256x256/apps"
    mkdir -p "$apps" "$icons"
    cat > "$apps/lexlock.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=ЛексЛок
Comment=Локальный офлайн ИИ-помощник юриста
Exec=$TARGET/run.sh
Icon=lexlock
Terminal=false
Categories=Office;Utility;
DESK
    if [ -f "$HERE/lexlock.png" ]; then
        cp "$HERE/lexlock.png" "$icons/lexlock.png" 2>/dev/null || true
    fi
    if command -v kbuildsycoca6 >/dev/null 2>&1; then
        kbuildsycoca6 >/dev/null 2>&1 || true
    elif command -v kbuildsycoca5 >/dev/null 2>&1; then
        kbuildsycoca5 >/dev/null 2>&1 || true
    elif command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$apps" >/dev/null 2>&1 || true
    fi
}

refresh_code() {
    # Первый запуск: подтягиваем свежий код ветки main (правки после сборки
    # AppImage тоже попадут). При неудаче молча остаёмся на коде из AppImage.
    # Документы (workspace), окружение (.venv) и журналы не затрагиваются.
    # Каталог с .git считаем разработческим и не перезаписываем.
    [ "${LEXLOCK_NO_REFRESH:-0}" = "1" ] && return 0
    [ -d "$TARGET/.git" ] && return 0
    ref="${LEXLOCK_CODE_REF:-main}"
    tmp="$(mktemp -d)" || return 0
    if curl -fL --retry 2 "https://github.com/workihi53-max/lexlock/archive/refs/heads/$ref.tar.gz" \
            -o "$tmp/src.tar.gz" 2>/dev/null \
        && tar -xzf "$tmp/src.tar.gz" -C "$tmp" 2>/dev/null \
        && [ -d "$tmp/lexlock-$ref" ]; then
        ( cd "$tmp/lexlock-$ref" && tar -cf - \
            --exclude=.venv --exclude=workspace --exclude=.git --exclude=dist \
            --exclude='*.log' --exclude=.lexlock_model --exclude=__pycache__ . ) \
            | ( cd "$TARGET" && tar -xf - ) 2>/dev/null || true
        echo "Код обновлён до $ref."
    fi
    rm -rf "$tmp"
}

if [ ! -x "$TARGET/.venv/bin/python" ]; then
    if [ -n "$DIALOG" ]; then
        confirm "ЛексЛок установится и откроется в браузере.\nПервый запуск скачает свежий код, компоненты и модель (~2 ГБ).\n\nПродолжить?" || exit 0
    fi
    if [ ! -d "$TARGET" ]; then
        mkdir -p "$TARGET"
        cp -R "$HERE/app/." "$TARGET/"
    fi
    cd "$TARGET" || exit 1
    refresh_code >>"$LOG" 2>&1
    if ! ./install.sh >>"$LOG" 2>&1; then
        error "Не удалось установить. Проверьте интернет и попробуйте снова.\n\nЖурнал: $LOG"
        exit 1
    fi
fi

install_desktop_entry

cd "$TARGET" || exit 1
( ./run.sh --no-browser >>"$LOG" 2>&1 & )
for _ in $(seq 1 60); do
    curl -s --max-time 1 "$URL/api/health" >/dev/null 2>&1 && break
    sleep 1
done
command -v xdg-open >/dev/null 2>&1 && xdg-open "$URL" >/dev/null 2>&1 || true
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
