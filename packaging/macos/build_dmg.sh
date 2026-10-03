#!/usr/bin/env bash
# Сборка macOS-установщика «Вани» (.dmg) с двойным кликом.
# Содержит проект и «Установить и запустить.command», который сам поставит uv,
# Ollama, зависимости и запустит приложение. hdiutil входит в macOS, Xcode не нужен.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST="$ROOT/dist"
STAGE="$DIST/dmg-stage"
VERSION="$(grep -m1 '^version' "$ROOT/pyproject.toml" | sed -E 's/.*"(.*)".*/\1/')"
APP_NAME="Ваня"
DMG="$DIST/Vanya-$VERSION.dmg"

if [ "$(uname -s)" != "Darwin" ]; then
    echo "Ошибка: .dmg собирается только на macOS." >&2
    exit 1
fi

echo "==> Версия: $VERSION"
rm -rf "$STAGE"
mkdir -p "$STAGE/$APP_NAME"

echo "==> Копирую проект"
rsync -a \
    --exclude '.venv' --exclude 'workspace' --exclude 'dist' --exclude '.git' \
    --exclude '__pycache__' --exclude '*.pyc' --exclude '.pytest_cache' \
    --exclude '.vanya_model' --exclude '*.egg-info' \
    "$ROOT/" "$STAGE/$APP_NAME/"

LAUNCHER="$STAGE/Установить и запустить.command"
cat > "$LAUNCHER" <<'EOF'
#!/bin/bash
# «Ваня» — двойной клик: установить (первый раз) и запустить.
cd "$(dirname "$0")" || exit 1
clear
echo "=== Ваня: локальный офлайн-ассистент для юристов ==="
echo
if [ ! -x .venv/bin/python ]; then
    echo "Первый запуск: устанавливаю окружение, Ollama и модель..."
    ./install.sh || {
        echo
        echo "Установка не удалась. Проверьте интернет и скопируйте текст выше."
        read -r -p "Enter — закрыть..." _
        exit 1
    }
fi
./run.sh
EOF
chmod +x "$LAUNCHER"

echo "==> Создаю $DMG"
mkdir -p "$DIST"
rm -f "$DMG"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null

echo
echo "Готово: $DMG"
echo "Передайте файл пользователю: открыть .dmg → перетащить «Ваня» на рабочий стол."
echo "Первый запуск потребует интернет (Ollama и модель ~2 ГБ)."
