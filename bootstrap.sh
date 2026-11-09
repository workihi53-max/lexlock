#!/usr/bin/env bash
# Установка «ЛексЛока» на Linux одним файлом.
#
#   Скачайте этот файл, разрешите запуск (правый клик -> Свойства -> Разрешить
#   выполнение) и откройте двойным кликом. Либо одной командой:
#     curl -fsSL https://raw.githubusercontent.com/workihi53-max/lexlock/main/bootstrap.sh | bash
#
# Скрипт скачивает свежий код ветки main, ставит uv/Ollama/модель, добавляет
# «ЛексЛок» в меню приложений и открывает браузер. Повторный запуск не качает
# заново уже установленное.
set -euo pipefail

REPO="${LEXLOCK_REPO:-workihi53-max/lexlock}"
LEGACY_REPO="workihi53-max/vanya-legal-vault"  # на случай, если репо ещё не переименован
BRANCH="${LEXLOCK_BRANCH:-main}"
DEST="${LEXLOCK_DIR:-$HOME/lexlock}"
URL="http://127.0.0.1:8765"

# GUI-диалоги: kdialog (KDE) -> zenity (GNOME) -> xmessage -> молча в терминал.
DIALOG=""
for d in kdialog zenity xmessage; do
    command -v "$d" >/dev/null 2>&1 && { DIALOG="$d"; break; }
done
info() {
    case "$DIALOG" in
        kdialog) kdialog --title "ЛексЛок" --msgbox "$1" 2>/dev/null ;;
        zenity)  zenity --info --title="ЛексЛок" --text="$1" --width=440 2>/dev/null ;;
        xmessage) xmessage -center -buttons OK "$1" 2>/dev/null ;;
        *) echo "[ЛексЛок] $1" ;;
    esac
    return 0
}
error() {
    case "$DIALOG" in
        kdialog) kdialog --title "ЛексЛок" --error "$1" 2>/dev/null ;;
        zenity)  zenity --error --title="ЛексЛок" --text="$1" --width=460 2>/dev/null ;;
        xmessage) xmessage -center -buttons OK "Ошибка: $1" 2>/dev/null ;;
        *) echo "[ЛексЛок] Ошибка: $1" >&2 ;;
    esac
    return 0
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "==> ЛексЛок: установка в $DEST"

# Если bootstrap.sh запущен из уже скачанного репозитория — ставим его, не качая.
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/install.sh" ]; then
    DEST="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

download_and_extract() {
    local repo="$1" branch="$2"
    local url="https://github.com/$repo/archive/refs/heads/$branch.tar.gz"
    echo "==> Скачиваю свежий код ($branch, $repo)"
    mkdir -p "$DEST"
    if curl -fL --retry 3 "$url" -o "$TMP/src.tar.gz" 2>/dev/null; then
        tar -xzf "$TMP/src.tar.gz" -C "$TMP"
        local src="$TMP/$(basename "$repo")-$branch"
        if [ -d "$src" ]; then
            # Копируем код, не трогая окружение и рабочую папку.
            (cd "$src" && tar -cf - --exclude=.venv --exclude=workspace .) \
                | (cd "$DEST" && tar -xf -)
            return 0
        fi
    fi
    return 1
}

if [ ! -f "$DEST/install.sh" ]; then
    ok=0
    for repo in "$REPO" "$LEGACY_REPO"; do
        for branch in "$BRANCH" master; do
            if download_and_extract "$repo" "$branch"; then ok=1; break 2; fi
        done
    done
    if [ "$ok" -ne 1 ]; then
        error "Не удалось скачать репозиторий. Проверьте интернет и адрес: https://github.com/$REPO"
        exit 1
    fi
fi

cd "$DEST"
if [ ! -x ".venv/bin/python" ]; then
    info "ЛексЛок сейчас установится и откроется в браузере.\nПервый запуск скачает компоненты и модель (~2 ГБ), это займёт несколько минут."
    if ! ./install.sh; then
        error "Не удалось установить. Проверьте интернет и запустите этот файл ещё раз."
        exit 1
    fi
fi

# Запускаем сервер и открываем браузер.
( ./run.sh --no-browser >/dev/null 2>&1 & )
for _ in $(seq 1 60); do
    curl -s --max-time 1 "$URL/api/health" >/dev/null 2>&1 && break
    sleep 1
done
command -v xdg-open >/dev/null 2>&1 && xdg-open "$URL" >/dev/null 2>&1 || true
info "ЛексЛок запущен — в меню приложений появился ярлык «ЛексЛок»."
