#!/usr/bin/env bash
# Первичная установка «ЛексЛока» — одна команда. Интернет нужен один раз:
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
# Если модель задана снаружи — считаем выбор явным и авто-подбор не применяем.
if [ -n "${LEXLOCK_MODEL:-}" ]; then
    MODEL="$LEXLOCK_MODEL"
    MODEL_EXPLICIT=1
fi
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

# --- Linux: пароль администратора (sudo) ------------------------------------
# Ollama и Tesseract ставятся на всю систему, поэтому Linux спросит пароль.
# Сначала объясняем зачем, потом спрашиваем один раз. Без прав установка не рушится:
# программа ставится, а недостающее можно поставить вручную (подсказка в сообщении).
SUDO_STATE=""
as_root() {
    if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}
ensure_sudo() {
    [ "$OS" = "Linux" ] || return 0
    [ "$(id -u)" -eq 0 ] && return 0
    [ "$SUDO_STATE" = ok ] && return 0
    [ "$SUDO_STATE" = no ] && return 1
    echo
    if ! command -v sudo >/dev/null 2>&1; then
        echo "    Нужны права администратора, чтобы поставить: $1." >&2
        echo "    В системе нет команды sudo. Попросите администратора поставить это или" >&2
        echo "    выполните установку от имени root." >&2
        SUDO_STATE=no; return 1
    fi
    echo "==> Нужен пароль администратора: $1"
    echo "    Сейчас система спросит пароль вашей учётной записи — тот, которым вы входите"
    echo "    в компьютер. Пароль при вводе НЕ показывается (ни точек, ни звёздочек): это нормально."
    echo "    Введите его вслепую и нажмите Enter."
    if sudo -v; then
        SUDO_STATE=ok; return 0
    fi
    echo "    Пароль не подошёл, либо у вашей учётной записи нет прав администратора," >&2
    echo "    либо установка запущена не из терминала (тогда откройте терминал и повторите)." >&2
    SUDO_STATE=no; return 1
}

# OCR на Linux: пакет Tesseract с русским языком для своего дистрибутива.
install_ocr_linux() {
    local pkgs=""
    local -a cmd=()
    if command -v apt-get >/dev/null 2>&1; then
        pkgs="tesseract-ocr tesseract-ocr-rus"; cmd=(apt-get install -y -qq)
    elif command -v dnf >/dev/null 2>&1; then
        pkgs="tesseract tesseract-langpack-rus"; cmd=(dnf install -y)
    elif command -v pacman >/dev/null 2>&1; then
        pkgs="tesseract tesseract-data-rus"; cmd=(pacman -S --noconfirm --needed)
    elif command -v zypper >/dev/null 2>&1; then
        pkgs="tesseract-ocr tesseract-ocr-traineddata-russian"; cmd=(zypper --non-interactive install)
    else
        echo "    OCR: не знаю пакетный менеджер. Поставьте Tesseract с русским языком вручную." >&2
        return 0
    fi
    if ! ensure_sudo "чтение сканов (пакеты: $pkgs)"; then
        echo "    OCR пропущен. Позже можно поставить: sudo ${cmd[*]} $pkgs" >&2
        return 0
    fi
    echo "==> Ставлю OCR: $pkgs"
    [ "${cmd[0]}" = apt-get ] && { as_root apt-get update -qq || true; }
    # shellcheck disable=SC2086
    as_root "${cmd[@]}" $pkgs || \
        echo "    Предупреждение: не удалось поставить Tesseract. Остальное работает." >&2
}

# OCR на macOS без Homebrew и без прав администратора: Tesseract из conda-forge
# через micromamba в ~/.local/ocr + русские данные. Приложение ищет его там само.
install_ocr_mac_local() {
    local plat prefix tmp
    case "$(uname -m)" in
        arm64) plat="osx-arm64" ;;
        x86_64) plat="osx-64" ;;
        *) return 1 ;;
    esac
    prefix="${LEXLOCK_OCR_DIR:-$HOME/.local/ocr}"
    tmp="$(mktemp -d)"
    echo "==> Ставлю OCR без Homebrew (около 150 МБ, права администратора не нужны)"
    curl -fL --retry 10 --retry-all-errors --retry-delay 3 --connect-timeout 20 -C - \
        -o "$tmp/mm.tar.bz2" "https://micro.mamba.pm/api/micromamba/$plat/latest" \
        && tar -xjf "$tmp/mm.tar.bz2" -C "$tmp" bin/micromamba \
        && "$tmp/bin/micromamba" create -y -q -p "$prefix" -c conda-forge tesseract \
        && mkdir -p "$prefix/share/tessdata" \
        && curl -fL --retry 10 --retry-all-errors --retry-delay 3 --connect-timeout 20 -C - \
            -o "$prefix/share/tessdata/rus.traineddata" \
            "https://github.com/tesseract-ocr/tessdata_fast/raw/main/rus.traineddata"
    local rc=$?
    rm -rf "$tmp"
    # Не оставляем полуготовую установку: иначе следующий запуск решит, что OCR уже есть.
    [ "$rc" -eq 0 ] || rm -rf "$prefix"
    return $rc
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
            if curl -fL --retry 15 --retry-all-errors --retry-delay 3 --connect-timeout 20 -C - -o "$TMPZIP" https://ollama.com/download/Ollama-darwin.zip; then
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
        # Linux: официальный скрипт установки. Он сам вызывает sudo, поэтому
        # сначала объясняем, зачем нужен пароль.
        if ! command -v curl >/dev/null 2>&1; then
            echo "    Предупреждение: для установки Ollama нужен curl." >&2
        elif ensure_sudo "программа Ollama (она запускает модель на вашем компьютере)"; then
            curl -fsSL https://ollama.com/install.sh | sh || \
                echo "    Предупреждение: установка Ollama завершилась с ошибкой." >&2
        else
            echo "    Ollama автоматически не поставлена. Поставьте вручную: https://ollama.com/download" >&2
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
    uv pip install --python "$VENV/bin/python" -e "$ROOT[tray]"
else
    uv pip install --python "$VENV/bin/python" -e "$ROOT[ocr,tray]"
fi

# --- OCR: Tesseract + русский язык (по умолчанию) ---------------------------
if [ "$NO_OCR" -eq 0 ]; then
    if command -v tesseract >/dev/null 2>&1 || find_tesseract >/dev/null 2>&1; then
        echo "    OCR: Tesseract найден"
    elif [ "$OS" = "Darwin" ]; then
        if command -v brew >/dev/null 2>&1; then
            echo "==> Ставлю OCR: tesseract + русский (brew)"
            brew install tesseract tesseract-lang || \
                echo "    Предупреждение: не удалось поставить Tesseract через brew." >&2
        fi
        if ! find_tesseract >/dev/null 2>&1; then
            install_ocr_mac_local || \
                echo "    Предупреждение: OCR не поставился. Основные сценарии работают, сканы читаться не будут." >&2
        fi
    elif [ "$OS" = "Linux" ]; then
        install_ocr_linux
    else
        echo "    OCR: Tesseract не найден. Установите вручную (см. packaging/README.md)." >&2
    fi
fi

# Визард модели: если --model не задан, выбираем модель по свободной ОЗУ.
if [ "$MODEL_EXPLICIT" -eq 0 ]; then
    REC="$("$VENV/bin/python" "$ROOT/scripts/check_ram.py" --recommend 2>/dev/null || echo "$MODEL")"
    if [ -n "$REC" ] && [ "$REC" != "$MODEL" ]; then
        echo "==> Свободной ОЗУ мало — выбираю лёгкую модель $REC"
        echo "    Переопределить: ./install.sh --model ИМЯ или LEXLOCK_MODEL"
    fi
    MODEL="$REC"
fi
printf '%s' "$MODEL" > "$ROOT/.lexlock_model"
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
        # Модель уже установлена — интернет не тратим, скачивание пропускаем.
        if "$OLLAMA_BIN" list 2>/dev/null | grep -q "^$MODEL[[:space:]]"; then
            echo "    Модель $MODEL уже установлена — скачивание не нужно."
        else
            echo "==> Скачивание модели $MODEL (может занять время)"
            # На слабом интернете загрузка рвётся; ollama pull докачивает с места обрыва,
            # поэтому просто повторяем, пока не получится.
            PULLED=0
            for N in $(seq 1 30); do
                if "$OLLAMA_BIN" pull "$MODEL"; then PULLED=1; break; fi
                echo "    Связь оборвалась, докачиваю (попытка $N из 30)..."
                sleep 5
            done
            if [ "$PULLED" -ne 1 ]; then
                echo "    Предупреждение: не удалось скачать модель $MODEL." >&2
                echo "    Повторите позже: $OLLAMA_BIN pull $MODEL" >&2
            fi
        fi
    else
        echo "    Предупреждение: Ollama не запустилась на 127.0.0.1:11434." >&2
        echo "    Запустите вручную и повторите: $OLLAMA_BIN pull $MODEL" >&2
    fi
fi

echo "==> Генерация шаблона и тестовых данных"
"$VENV/bin/python" "$ROOT/scripts/make_template.py"
"$VENV/bin/python" "$ROOT/scripts/demo_data.py"

# Ярлык в меню приложений Linux — чтобы «ЛексЛок» запускался как обычная программа.
if [ "$OS" = "Linux" ]; then
    APPS="$HOME/.local/share/applications"
    ICONS="$HOME/.local/share/icons/hicolor/256x256/apps"
    mkdir -p "$APPS" "$ICONS"
    cat > "$APPS/lexlock.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=ЛексЛок
Comment=Локальный офлайн ИИ-помощник юриста
Exec=$ROOT/run.sh
Icon=lexlock
Terminal=false
Categories=Office;Utility;
DESK
    if [ -f "$ROOT/packaging/linux/lexlock.png" ]; then
        cp "$ROOT/packaging/linux/lexlock.png" "$ICONS/lexlock.png"
    fi
    # Обновляем кэш меню приложений: KDE ждёт kbuildsycoca, GNOME — update-desktop-database.
    if command -v kbuildsycoca6 >/dev/null 2>&1; then
        kbuildsycoca6 >/dev/null 2>&1 || true
    elif command -v kbuildsycoca5 >/dev/null 2>&1; then
        kbuildsycoca5 >/dev/null 2>&1 || true
    elif command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$APPS" >/dev/null 2>&1 || true
    fi
    echo "    Ярлык добавлен в меню приложений."
fi

# Ярлык в Launchpad на macOS — собираем простое .app, чтобы запускать из «Программ».
if [ "$OS" = "Darwin" ]; then
    APPDIR="$HOME/Applications/ЛексЛок.app"
    mkdir -p "$APPDIR/Contents/MacOS" "$APPDIR/Contents/Resources"
    cat > "$APPDIR/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>ЛексЛок</string>
    <key>CFBundleDisplayName</key><string>ЛексЛок</string>
    <key>CFBundleIdentifier</key><string>ru.legalvault.lexlock</string>
    <key>CFBundleExecutable</key><string>lexlock</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST
    cat > "$APPDIR/Contents/MacOS/lexlock" <<LAUNCH
#!/bin/bash
exec "$ROOT/run.sh"
LAUNCH
    chmod +x "$APPDIR/Contents/MacOS/lexlock"
    echo "    Приложение добавлено в «Программы» (Launchpad)."
fi

echo
echo "Готово. Запусти ./run.sh"
echo "Если Ollama ставилась впервые — на macOS запустите приложение Ollama один раз."
