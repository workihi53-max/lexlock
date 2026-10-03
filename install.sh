#!/usr/bin/env bash
# Первичная установка «Вани» — одна команда. Интернет нужен один раз:
# ставятся uv, Ollama, зависимости Python и скачивается модель.
#
#   ./install.sh                # полная установка
#   ./install.sh --skip-model   # без скачивания модели (быстрая проверка)
#   ./install.sh --model qwen2.5:1.5b
#
# Скрипт сам ставит uv и Ollama, если их нет в системе.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
MODEL="qwen2.5:3b"
MODEL_EXPLICIT=0
SKIP_MODEL=0
NO_OCR=0
OLLAMA_BIN=""

usage() {
    echo "Использование: ./install.sh [--skip-model] [--no-ocr] [--model ИМЯ] [-h]"
    echo "  --skip-model   не скачивать модель Ollama"
    echo "  --no-ocr       не ставить OCR (Tesseract + PyMuPDF)"
    echo "  --model ИМЯ    модель Ollama (по умолчанию подбирается по ОЗУ)"
    exit 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --skip-model) SKIP_MODEL=1; shift ;;
        --no-ocr) NO_OCR=1; shift ;;
        --model) MODEL="${2:?--model требует имя модели}"; MODEL_EXPLICIT=1; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Неизвестный флаг: $1" >&2; usage ;;
    esac
done

OS="$(uname -s)"

# Добавляет в PATH места, куда uv/Ollama ставятся без root.
add_local_paths() {
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
}

# Ищет бинарник ollama, включая установку в Ollama.app на macOS.
find_ollama() {
    if [ -n "$OLLAMA_BIN" ] && [ -x "$OLLAMA_BIN" ]; then
        echo "$OLLAMA_BIN"; return 0
    fi
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

# Ищет бинарник tesseract, включая установку через conda/uv в ~/.local/ocr.
find_tesseract() {
    if command -v tesseract >/dev/null 2>&1; then
        command -v tesseract; return 0
    fi
    for candidate in \
        "$HOME/.local/ocr/bin/tesseract" \
        /opt/homebrew/bin/tesseract /usr/local/bin/tesseract; do
        if [ -x "$candidate" ]; then
            echo "$candidate"; return 0
        fi
    done
    return 1
}

# --- uv: ставим автоматически, если нет -------------------------------------
echo "==> Проверка окружения ($OS)"
add_local_paths
if ! command -v uv >/dev/null 2>&1; then
    echo "==> uv не найден — устанавливаю (https://astral.sh/uv)"
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        echo "Ошибка: нужен curl или wget для установки uv." >&2
        echo "Установите вручную: https://docs.astral.sh/uv/getting-started/installation/" >&2
        exit 1
    fi
    add_local_paths
fi
if ! command -v uv >/dev/null 2>&1; then
    echo "Ошибка: uv установился, но не найден в PATH. Перезапустите терминал и повторите ./install.sh" >&2
    exit 1
fi
echo "    uv: $(command -v uv)"

# --- Ollama: ставим автоматически, если нет --------------------------------
if find_ollama >/dev/null 2>&1; then
    OLLAMA_BIN="$(find_ollama)"
    echo "    Ollama: $OLLAMA_BIN"
else
    echo "==> Ollama не найден — устанавливаю"
    if [ "$OS" = "Darwin" ]; then
        if command -v brew >/dev/null 2>&1; then
            brew install ollama || echo "    Предупреждение: brew install ollama завершился с ошибкой." >&2
        else
            # Ставим официальное приложение Ollama.app без Homebrew.
            TMPZIP="$(mktemp -d)/Ollama-darwin.zip"
            echo "    Скачиваю Ollama.app (~200 МБ)..."
            if curl -fL --retry 3 -o "$TMPZIP" https://ollama.com/download/Ollama-darwin.zip; then
                for APP_DIR in /Applications "$HOME/Applications"; do
                    if unzip -q -o "$TMPZIP" -d "$APP_DIR" 2>/dev/null; then
                        echo "    Ollama.app установлен в $APP_DIR"
                        break
                    fi
                done
            fi
            rm -f "$TMPZIP"
        fi
    else
        # Linux: официальный скрипт установки.
        if command -v curl >/dev/null 2>&1; then
            curl -fsSL https://ollama.com/install.sh | sh || \
                echo "    Предупреждение: установка Ollama завершилась с ошибкой." >&2
        else
            echo "    Предупреждение: для установки Ollama нужен curl." >&2
        fi
    fi
    add_local_paths
    if find_ollama >/dev/null 2>&1; then
        OLLAMA_BIN="$(find_ollama)"
        echo "    Ollama: $OLLAMA_BIN"
    else
        echo "    Предупреждение: Ollama автоматически не установилась." >&2
        echo "    Установите вручную: https://ollama.com/download — затем повторите ./install.sh" >&2
    fi
fi

echo "==> Создание виртуального окружения (Python 3.12 подтянет сам uv)"
if [ ! -x "$VENV/bin/python" ]; then
    uv venv --python 3.12 "$VENV"
fi

echo "==> Установка зависимостей"
if [ "$NO_OCR" -eq 1 ]; then
    uv pip install --python "$VENV/bin/python" -e "$ROOT"
else
    uv pip install --python "$VENV/bin/python" -e "$ROOT[ocr]"
fi

# --- OCR: Tesseract + русский язык (по умолчанию) ---------------------------
if [ "$NO_OCR" -eq 0 ]; then
    if command -v tesseract >/dev/null 2>&1 || find_tesseract >/dev/null 2>&1; then
        echo "    OCR: Tesseract найден"
    elif [ "$OS" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
        echo "==> Ставлю OCR: tesseract + русский (brew)"
        brew install tesseract tesseract-lang || \
            echo "    Предупреждение: не удалось поставить Tesseract через brew." >&2
    elif [ "$OS" = "Linux" ] && command -v apt-get >/dev/null 2>&1; then
        echo "==> Ставлю OCR: tesseract-ocr + русский (apt)"
        sudo apt-get update -qq && sudo apt-get install -y -qq tesseract-ocr tesseract-ocr-rus || \
            echo "    Предупреждение: не удалось поставить Tesseract." >&2
    else
        echo "    OCR: Tesseract не найден. Установите вручную (см. packaging/README.md)." >&2
    fi
fi

# Визард модели: если --model не задан, выбираем модель по свободной ОЗУ.
if [ "$MODEL_EXPLICIT" -eq 0 ]; then
    REC="$("$VENV/bin/python" "$ROOT/scripts/check_ram.py" --recommend 2>/dev/null || echo "$MODEL")"
    if [ -n "$REC" ] && [ "$REC" != "$MODEL" ]; then
        echo "==> Свободной ОЗУ мало — выбираю лёгкую модель $REC"
        echo "    Переопределить: ./install.sh --model ИМЯ или VANYA_MODEL"
    fi
    MODEL="$REC"
fi
printf '%s' "$MODEL" > "$ROOT/.vanya_model"
echo "    Модель: $MODEL"

echo "==> Проверка ресурсов (предупреждение не останавливает установку)"
if ! "$VENV/bin/python" "$ROOT/scripts/check_ram.py" --model "$MODEL"; then
    echo "    Внимание: свободной ОЗУ мало — модель может работать медленно или уйти в своп."
fi

if [ "$SKIP_MODEL" -eq 1 ]; then
    echo "==> Модель Ollama пропущена (--skip-model)"
elif [ -z "$OLLAMA_BIN" ]; then
    echo "==> Модель не скачана: Ollama не найдена." >&2
    echo "    Установите Ollama и выполните: $OLLAMA_BIN pull $MODEL"
else
    echo "==> Проверка Ollama"
    if ! curl -s --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        echo "    Запускаю ollama serve в фоне..."
        nohup "$OLLAMA_BIN" serve >/dev/null 2>&1 &
        for _ in $(seq 1 30); do
            if curl -s --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
                break
            fi
            sleep 1
        done
    fi
    if curl -s --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        echo "==> Скачивание модели $MODEL (может занять время)"
        "$OLLAMA_BIN" pull "$MODEL" || {
            echo "    Предупреждение: не удалось скачать модель $MODEL." >&2
            echo "    Повторите позже: $OLLAMA_BIN pull $MODEL" >&2
        }
    else
        echo "    Предупреждение: Ollama не запустилась на 127.0.0.1:11434." >&2
        echo "    Запустите вручную и повторите: $OLLAMA_BIN pull $MODEL" >&2
    fi
fi

echo "==> Генерация шаблона и тестовых данных"
"$VENV/bin/python" "$ROOT/scripts/make_template.py"
"$VENV/bin/python" "$ROOT/scripts/demo_data.py"

echo
echo "Готово. Запусти ./run.sh"
echo "Если Ollama ставилась впервые — на macOS запустите приложение Ollama один раз."
