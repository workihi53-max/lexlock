#!/usr/bin/env bash
# Собирает портативный офлайн-пакет ЛексЛока для Windows x64 (запускать на Linux/macOS).
# Внутри: Python, зависимости, Ollama и модель. Пользователю: распаковать и запустить .bat.
# Использование: scripts/build_offline_windows.sh [модель, по умолчанию qwen2.5:3b]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL="${1:-qwen2.5:3b}"
PYVER="3.12.8"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/pyproject.toml")"
NAME="LexLock-$VERSION-win-offline"
OUT="$ROOT/dist/$NAME"
CACHE="$ROOT/dist/.cache"
MODELS_SRC="${OLLAMA_MODELS:-$HOME/.ollama/models}"

mkdir -p "$CACHE"
rm -rf "$OUT"; mkdir -p "$OUT/python" "$OUT/ollama" "$OUT/models"

fetch() { [ -s "$2" ] || curl -fL -sS --retry 10 --retry-all-errors -C - -o "$2" "$1"; }

echo "==> Python $PYVER (embeddable)"
fetch "https://www.python.org/ftp/python/$PYVER/python-$PYVER-embed-amd64.zip" "$CACHE/py.zip"
unzip -q -o "$CACHE/py.zip" -d "$OUT/python"
# Разрешаем site-packages и корень проекта.
cat > "$OUT/python/python312._pth" <<PTH
python312.zip
.
..\\site-packages
..
import site
PTH

echo "==> Зависимости (колёса для Windows)"
uv pip install --quiet --target "$OUT/site-packages" \
    --python-platform x86_64-pc-windows-msvc --python-version 3.12 \
    "$ROOT[ocr,tray]"
rm -rf "$OUT/site-packages"/lexlock* "$OUT/site-packages"/app "$OUT/site-packages"/bin

echo "==> Код приложения"
for d in lexlock app templates samples scripts; do cp -r "$ROOT/$d" "$OUT/$d"; done
find "$OUT" -name __pycache__ -type d -prune -exec rm -rf {} +
mkdir -p "$OUT/workspace"
cp "$ROOT/README.md" "$OUT/"
echo "$MODEL" > "$OUT/.lexlock_model"

echo "==> Ollama для Windows"
fetch "https://github.com/ollama/ollama/releases/latest/download/ollama-windows-amd64.zip" "$CACHE/ollama.zip"
unzip -q -o "$CACHE/ollama.zip" -d "$OUT/ollama"
# Целимся в обычные ноутбуки: библиотеки CUDA (~2 ГБ) не нужны, останутся CPU и Vulkan.
rm -rf "$OUT"/ollama/lib/ollama/cuda_v* "$OUT"/ollama/lib/ollama/rocm*

echo "==> Модель $MODEL"
NAMEPART="${MODEL%%:*}"; TAG="${MODEL##*:}"
MAN="$MODELS_SRC/manifests/registry.ollama.ai/library/$NAMEPART/$TAG"
[ -f "$MAN" ] || { echo "Модель $MODEL не найдена локально ($MAN). Сначала: ollama pull $MODEL" >&2; exit 1; }
mkdir -p "$OUT/models/manifests/registry.ollama.ai/library/$NAMEPART" "$OUT/models/blobs"
cp "$MAN" "$OUT/models/manifests/registry.ollama.ai/library/$NAMEPART/$TAG"
python3 -c "
import json,sys
m=json.load(open('$MAN'))
for d in [m['config']['digest']]+[l['digest'] for l in m['layers']]: print(d.replace(':','-'))
" | while read -r b; do cp "$MODELS_SRC/blobs/$b" "$OUT/models/blobs/$b"; done

echo "==> Запускатор"
cat > "$OUT/Запустить ЛексЛок.bat" <<'BAT'
@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "LEXLOCK_MODEL=qwen2.5:3b"
if exist .lexlock_model set /p LEXLOCK_MODEL=<.lexlock_model
set "LEXLOCK_OFFLINE=1"
set "LEXLOCK_LLM_EXTRACT=1"
set "LEXLOCK_PORT=8765"
set "LEXLOCK_WORKSPACE=%~dp0workspace"
set "OLLAMA_MODELS=%~dp0models"
set "PYTHONNOUSERSITE=1"

echo Запускаю ЛексЛок. Это окно можно свернуть; закрыть программу - значок в трее "Остановить".
curl -s --max-time 2 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    start "" /min "%~dp0ollama\ollama.exe" serve
    timeout /t 4 /nobreak >nul
)
start "" /min "%~dp0python\python.exe" scripts\launcher.py --no-browser

set /a tries=0
:wait
curl -s --max-time 1 http://127.0.0.1:%LEXLOCK_PORT%/api/health >nul 2>&1
if not errorlevel 1 goto ok
set /a tries+=1
if %tries% geq 90 goto fail
timeout /t 1 /nobreak >nul
goto wait
:ok
start "" "http://127.0.0.1:%LEXLOCK_PORT%"
exit /b 0
:fail
echo Не удалось запустить. Сообщите разработчику.
pause
BAT
cat > "$OUT/ПРОЧТИ МЕНЯ.txt" <<'TXT'
ЛексЛок - офлайн-версия для Windows. Интернет НЕ нужен.

1. Распакуйте архив целиком в любую папку (например, C:\LexLock). Не запускайте из окна архива.
2. Дважды щёлкните "Запустить ЛексЛок.bat". Первый запуск может занять до минуты.
3. Откроется браузер со страницей http://127.0.0.1:8765.
4. Документы лежат в папке workspace рядом с программой.

Если Windows пишет "защитили ваш компьютер" - "Подробнее" - "Выполнить в любом случае".
Нужно ~8 ГБ ОЗУ и ~5 ГБ свободного места.
TXT

echo "==> Архив"
cd "$ROOT/dist"
rm -f "$NAME.zip"
python3 - "$NAME" <<'PY'
import os, sys, zipfile
name = sys.argv[1]
with zipfile.ZipFile(name + ".zip", "w", zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True) as z:
    for d, _, files in os.walk(name):
        for f in files:
            p = os.path.join(d, f)
            big = os.path.getsize(p) > 50_000_000  # модель уже сжата
            z.write(p, p, compress_type=zipfile.ZIP_STORED if big else zipfile.ZIP_DEFLATED)
PY
ls -lh "$NAME.zip"
