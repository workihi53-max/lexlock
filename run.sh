#!/usr/bin/env bash
# Запуск «Вани» — работает без интернета.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
OFFLINE=1
OPEN=1

while [ $# -gt 0 ]; do
    case "$1" in
        --no-offline) OFFLINE=0; shift ;;
        --no-browser) OPEN=0; shift ;;
        *) echo "Неизвестный флаг: $1 (доступны --no-offline, --no-browser)" >&2; exit 2 ;;
    esac
done

if [ ! -x "$VENV/bin/python" ]; then
    echo "Ошибка: виртуальное окружение не найдено." >&2
    echo "Сначала выполните: ./install.sh" >&2
    exit 1
fi

# Ищем ollama, включая приложение Ollama.app (macOS) и Homebrew.
find_ollama() {
    if command -v ollama >/dev/null 2>&1; then
        command -v ollama; return 0
    fi
    for candidate in \
        /Applications/Ollama.app/Contents/Resources/ollama \
        "$HOME/Applications/Ollama.app/Contents/Resources/ollama" \
        /usr/local/bin/ollama /opt/homebrew/bin/ollama; do
        if [ -x "$candidate" ]; then
            echo "$candidate"; return 0
        fi
    done
    return 1
}

# Ollama: если не отвечает — поднять в фоне (нужна только LLM-сценариям,
# детерминированное заполнение договора работает и без неё).
OLLAMA="$(find_ollama || true)"
if [ -n "$OLLAMA" ] && command -v curl >/dev/null 2>&1 \
   && ! curl -s --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "Запускаю Ollama..."
    nohup "$OLLAMA" serve >/dev/null 2>&1 &
    for _ in $(seq 1 20); do
        curl -s --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break
        sleep 1
    done
fi

# Модель: VANYA_MODEL > .vanya_model (выбрана install.sh) > 3b.
DEFAULT_MODEL="qwen2.5:3b"
if [ -f "$ROOT/.vanya_model" ]; then
    DEFAULT_MODEL="$(cat "$ROOT/.vanya_model")"
fi
CHOSEN_MODEL="${VANYA_MODEL:-$DEFAULT_MODEL}"

# Предупреждение о ресурсах (не блокирует запуск).
if ! "$VENV/bin/python" "$ROOT/scripts/check_ram.py" --model "$CHOSEN_MODEL" >/dev/null 2>&1; then
    echo "Внимание: свободной ОЗУ мало — модель может работать медленно или уйти в своп." >&2
fi

export VANYA_OFFLINE="$OFFLINE"
export VANYA_MODEL="$CHOSEN_MODEL"
# В рабочем запуске включаем дозаполнение реквизитов моделью (в тестах — выключено).
export VANYA_LLM_EXTRACT="${VANYA_LLM_EXTRACT:-1}"

PORT="${VANYA_PORT:-8765}"
URL="http://127.0.0.1:${PORT}"
echo "Открой $URL"

# Открываем браузер после старта сервера (не критично, если не получится).
if [ "$OPEN" -eq 1 ]; then
    (
        for _ in $(seq 1 30); do
            if curl -s --max-time 1 "$URL/api/health" >/dev/null 2>&1; then
                break
            fi
            sleep 1
        done
        if command -v open >/dev/null 2>&1; then
            open "$URL" >/dev/null 2>&1 || true
        elif command -v xdg-open >/dev/null 2>&1; then
            xdg-open "$URL" >/dev/null 2>&1 || true
        fi
    ) &
fi

cd "$ROOT"
exec "$VENV/bin/python" -m app.server
