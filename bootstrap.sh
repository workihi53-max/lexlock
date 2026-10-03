#!/usr/bin/env bash
# Установка «Вани» одной командой:
#
#   curl -fsSL https://raw.githubusercontent.com/workihi53-max/vanya-legal-vault/main/bootstrap.sh | bash
#
# Скрипт скачивает проект (git не нужен), затем запускает install.sh.
# Все флаги install.sh пробрасываются дальше, например:
#
#   ... | bash -s -- --model qwen2.5:1.5b
set -euo pipefail

REPO="workihi53-max/vanya-legal-vault"
BRANCH="${VANYA_BRANCH:-main}"
DEST="${VANYA_DIR:-$HOME/vanya-legal-vault}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "==> Ваня: установка в $DEST"

# Если bootstrap.sh запущен из уже скачанного репозитория — ставим его.
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/install.sh" ]; then
    DEST="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    exec "$DEST/install.sh" "$@"
fi

download_and_extract() {
    local branch="$1"
    local url="https://github.com/$REPO/archive/refs/heads/$branch.tar.gz"
    echo "==> Скачиваю ветку $branch"
    mkdir -p "$DEST"
    if curl -fL --retry 3 "$url" -o "$TMP/src.tar.gz" 2>/dev/null; then
        tar -xzf "$TMP/src.tar.gz" -C "$TMP"
        local src="$TMP/$(basename "$REPO")-$branch"
        if [ -d "$src" ]; then
            # Копируем код, не трогая виртуальное окружение и рабочую папку.
            (cd "$src" && tar -cf - --exclude=.venv --exclude=workspace .) \
                | (cd "$DEST" && tar -xf -)
            return 0
        fi
    fi
    return 1
}

if ! download_and_extract "$BRANCH"; then
    if [ "$BRANCH" = "main" ]; then
        download_and_extract "master"
    else
        echo "Ошибка: не удалось скачать репозиторий $REPO." >&2
        echo "Проверьте интернет и адрес: https://github.com/$REPO" >&2
        exit 1
    fi
fi

exec "$DEST/install.sh" "$@"
