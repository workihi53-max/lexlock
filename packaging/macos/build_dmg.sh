#!/usr/bin/env bash
# Сборка macOS-установщика «ЛексЛока»: настоящий .app + .dmg с перетаскиванием
# в «Программы». Пользователь не видит терминала — только нативные диалоги.
# hdiutil/sips/iconutil входят в macOS, Xcode не нужен.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST="$ROOT/dist"
STAGE="$DIST/dmg-stage"
VERSION="$(grep -m1 '^version' "$ROOT/pyproject.toml" | sed -E 's/.*"(.*)".*/\1/')"
APP_NAME="ЛексЛок"
APP="$STAGE/$APP_NAME.app"
DMG="$DIST/LexLock-$VERSION.dmg"

if [ "$(uname -s)" != "Darwin" ]; then
    echo "Ошибка: .dmg собирается только на macOS." >&2
    exit 1
fi

echo "==> Версия: $VERSION"
rm -rf "$STAGE"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

echo "==> Копирую проект в приложение"
rsync -a \
    --exclude '.venv' --exclude 'workspace' --exclude 'dist' --exclude '.git' \
    --exclude '__pycache__' --exclude '*.pyc' --exclude '.pytest_cache' \
    --exclude '.lexlock_model' --exclude '*.egg-info' \
    "$ROOT/" "$APP/Contents/Resources/lexlock/"

# --- иконка .icns из PNG ---
ICON_SRC="$ROOT/packaging/linux/lexlock.png"
if [ -f "$ICON_SRC" ]; then
    ICONSET="$DIST/lexlock.iconset"
    rm -rf "$ICONSET"; mkdir -p "$ICONSET"
    for size in 16 32 64 128 256 512; do
        sips -z $size $size "$ICON_SRC" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null 2>&1 || true
        d=$((size * 2))
        sips -z $d $d "$ICON_SRC" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null 2>&1 || true
    done
    iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/vanja.icns" >/dev/null 2>&1 || \
        cp "$ICON_SRC" "$APP/Contents/Resources/vanja.icns" 2>/dev/null || true
fi

# --- Info.plist ---
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>$APP_NAME</string>
    <key>CFBundleDisplayName</key><string>$APP_NAME</string>
    <key>CFBundleIdentifier</key><string>ru.legalvault.lexlock</string>
    <key>CFBundleVersion</key><string>$VERSION</string>
    <key>CFBundleShortVersionString</key><string>$VERSION</string>
    <key>CFBundleExecutable</key><string>lexlock</string>
    <key>CFBundleIconFile</key><string>vanja</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>LSApplicationCategoryType</key><string>public.app-category.productivity</string>
</dict>
</plist>
PLIST

# --- исполняемый лаунчер (GUI через osascript, без терминала) ---
cat > "$APP/Contents/MacOS/lexlock" <<'LAUNCHER'
#!/bin/bash
# Двойной клик: установить (первый раз) и запустить «ЛексЛок».
# Ставим НЕ внутрь .app (он может быть read-only из-за Gatekeeper/translocation),
# а в записываемую ~/Library/Application Support/LexLock.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/../Resources/lexlock"
DIR="$HOME/Library/Application Support/LexLock"
LOG="$HOME/Library/Logs/LexLock.log"
URL="http://127.0.0.1:8765"
mkdir -p "$(dirname "$LOG")"
export PATH="$HOME/.local/bin:$HOME/.local/git/bin:$HOME/.local/ocr/bin:$PATH"

say() { [ "${LEXLOCK_NO_GUI:-0}" = "1" ] || osascript -e "display notification \"$1\" with title \"ЛексЛок\"" >/dev/null 2>&1 || true; }
ask() {
    [ "${LEXLOCK_NO_GUI:-0}" = "1" ] && return 0
    osascript -e "display dialog \"$1\" buttons {\"Продолжить\", \"Отмена\"} default button 1 with title \"ЛексЛок\"" \
        >/dev/null 2>&1 || return 1
}
fail() {
    if [ "${LEXLOCK_NO_GUI:-0}" = "1" ]; then echo "$1" >&2; else
        osascript -e "display dialog \"$1\n\nЖурнал: $LOG\" buttons {\"OK\"} with icon stop with title \"ЛексЛок\"" >/dev/null 2>&1 || true
    fi
}

# Разворачиваем/обновляем проект в записываемом каталоге.
mkdir -p "$DIR" 2>>"$LOG" || { fail "Нет доступа к $DIR."; exit 1; }
if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
        --exclude '.venv' --exclude 'workspace' --exclude '.lexlock_model' \
        "$SRC/" "$DIR/" >>"$LOG" 2>&1 || cp -R "$SRC/." "$DIR/" 2>>"$LOG"
else
    cp -R "$SRC/." "$DIR/" 2>>"$LOG"
fi
cd "$DIR" || { fail "Не нашёл файлы приложения."; exit 1; }

if [ ! -x .venv/bin/python ]; then
    ask "ЛексЛок установится и откроется в браузере.\nПервый запуск скачает компоненты и модель (~2 ГБ),\nэто займёт несколько минут." || exit 0
    say "Устанавливаю «ЛексЛок», это займёт несколько минут…"
    if ! ./install.sh >>"$LOG" 2>&1; then
        fail "Не удалось установить. Проверьте интернет и попробуйте снова."
        exit 1
    fi
fi

# Запускаем сервер в фоне (без своего браузера), затем открываем его сами.
( ./run.sh --no-browser >>"$LOG" 2>&1 & ) || { fail "Не удалось запустить приложение."; exit 1; }

for _ in $(seq 1 40); do
    if curl -s --max-time 1 "$URL/api/health" >/dev/null 2>&1; then break; fi
    sleep 1
done
open "$URL" >/dev/null 2>&1 || true
say "ЛексЛок запущен — открываю браузер."
LAUNCHER
chmod +x "$APP/Contents/MacOS/lexlock"

# --- фон DMG: ссылка на «Программы» ---
ln -s /Applications "$STAGE/Applications"

# --- инструкция для Gatekeeper (приложение пока не подписано) ---
cat > "$STAGE/Как открыть.txt" <<'TXT'
ЛексЛок — установка на macOS

1. Перетащите «ЛексЛок» в папку «Программы».
2. Первый запуск: откройте «Программы», нажмите на «ЛексЛок» ПРАВОЙ кнопкой мыши
   (или Ctrl+клик) и выберите «Открыть» → «Открыть».
   Это нужно один раз, потому что приложение пока не подписано Apple.
3. Дальше «ЛексЛок» запускается обычным двойным кликом.

Приложение само скачает компоненты (~2 ГБ) и откроет браузер.
Журнал установки: ~/Library/Logs/LexLock.log
TXT

echo "==> Создаю $DMG"
mkdir -p "$DIST"
rm -f "$DMG"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null

echo
echo "Готово: $DMG"
echo "Пользователь: открыть .dmg → перетащить «${APP_NAME}» в «Программы» → запустить."
