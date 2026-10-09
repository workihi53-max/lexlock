#!/usr/bin/env bash
# Установка «ЛексЛока» одной командой:
#
#   curl -fsSL https://raw.githubusercontent.com/workihi53-max/lexlock/main/bootstrap.sh | bash
#
# Скрипт скачивает проект (git не нужен), затем запускает install.sh.
# Все флаги install.sh пробрасываются дальше, например:
#
#   ... | bash -s -- --model qwen2.5:1.5b
set -euo pipefail

REPO="${LEXLOCK_REPO:-workihi53-max/lexlock}"
# Старое имя репозитория — на случай, если он ещё не переименован на GitHub.
LEGACY_REPO="workihi53-max/vanya-legal-vault"
BRANCH="${LEXLOCK_BRANCH:-main}"
DEST="${LEXLOCK_DIR:-$HOME/lexlock}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "==> ЛексЛок: установка в $DEST"

# Если bootstrap.sh запущен из уже скачанного репозитория — ставим его.
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/install.sh" ]; then
    DEST="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    exec "$DEST/install.sh" "$@"
fi

download_and_extract() {
    local repo="$1"
    local branch="$2"
    local url="https://github.com/$repo/archive/refs/heads/$branch.tar.gz"
    echo "==> Скачиваю ветку $branch ($repo)"
    mkdir -p "$DEST"
    if curl -fL --retry 3 "$url" -o "$TMP/src.tar.gz" 2>/dev/null; then
        tar -xzf "$TMP/src.tar.gz" -C "$TMP"
        local src="$TMP/$(basename "$repo")-$branch"
        if [ -d "$src" ]; then
            # Копируем код, не трогая виртуальное окружение и рабочую папку.
            (cd "$src" && tar -cf - --exclude=.venv --exclude=workspace .) \
                | (cd "$DEST" && tar -xf -)
            return 0
        fi
    fi
    return 1
}

# Пробуем новое имя репозитория, затем старое и ветку master (для совместимости).
ok=0
for repo in "$REPO" "$LEGACY_REPO"; do
    for branch in "$BRANCH" master; do
        if download_and_extract "$repo" "$branch"; then ok=1; break 2; fi
    done
done
if [ "$ok" -ne 1 ]; then
    echo "Ошибка: не удалось скачать репозиторий." >&2
    echo "Проверьте интернет и адрес: https://github.com/$REPO" >&2
    exit 1
fi

exec "$DEST/install.sh" "$@"
