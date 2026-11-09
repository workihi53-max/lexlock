#!/usr/bin/env bash
# Собирает самодостаточный офлайн-пакет «ЛексЛока»: Python, зависимости, Ollama и модель.
# У пользователя ничего не качается и не устанавливается.
#
#   scripts/build_offline.sh windows [модель]   # с Linux/macOS (кросс-сборка)
#   scripts/build_offline.sh linux   [модель]   # на Linux x86_64 -> .AppImage
#   scripts/build_offline.sh macos   [модель]   # на macOS (arm64 или x86_64) -> .dmg
#
# Модель по умолчанию qwen2.5:3b; если её нет локально, она скачивается через Ollama.
set -euo pipefail

TARGET="${1:?Укажите цель: windows | linux | macos}"
MODEL="${2:-qwen2.5:3b}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/pyproject.toml")"
HOST="$(uname -s)"; ARCH="$(uname -m)"
CACHE="$ROOT/dist/.cache"
MODELS_SRC="${OLLAMA_MODELS:-$HOME/.ollama/models}"
OLLAMA_REL="https://github.com/ollama/ollama/releases/latest/download"
PYMIN="3.12"

case "$TARGET" in
    windows) PLAT=win;   OUTNAME="LexLock-$VERSION-win-offline" ;;
    linux)   PLAT=linux; OUTNAME="LexLock-$VERSION-linux-offline"
             [ "$HOST" = Linux ] && [ "$ARCH" = x86_64 ] || { echo "Linux-сборка — только на Linux x86_64" >&2; exit 1; } ;;
    macos)   PLAT=mac;   OUTNAME="LexLock-$VERSION-mac-$ARCH-offline"
             [ "$HOST" = Darwin ] || { echo "macOS-сборка — только на macOS" >&2; exit 1; } ;;
    *) echo "Неизвестная цель: $TARGET" >&2; exit 1 ;;
esac

PAYLOAD="$ROOT/dist/$OUTNAME"        # каталог с содержимым пакета
mkdir -p "$CACHE"
rm -rf "$PAYLOAD"; mkdir -p "$PAYLOAD/ollama" "$PAYLOAD/models"
fetch() { [ -s "$2" ] || curl -fL -sS --retry 10 --retry-all-errors -C - -o "$2" "$1"; }

# ---------- 1. Python ----------
echo "==> Python"
if [ "$PLAT" = win ]; then
    PYV=3.12.8
    mkdir -p "$PAYLOAD/python"
    fetch "https://www.python.org/ftp/python/$PYV/python-$PYV-embed-amd64.zip" "$CACHE/py-win.zip"
    unzip -q -o "$CACHE/py-win.zip" -d "$PAYLOAD/python"
    printf 'python312.zip\n.\n..\\site-packages\n..\nimport site\n' > "$PAYLOAD/python/python312._pth"
    UVARGS=(--python-platform x86_64-pc-windows-msvc --python-version "$PYMIN")
    PYBIN=""
else
    # python-build-standalone: переносимый Python, который ставит сам uv.
    PYDIR="$CACHE/py-$PLAT-$ARCH"
    uv python install "$PYMIN" --install-dir "$PYDIR" >/dev/null
    SRC="$(ls -d "$PYDIR"/cpython-$PYMIN* | head -1)"
    cp -a "$SRC" "$PAYLOAD/python"
    PYBIN="$PAYLOAD/python/bin/python3"
    UVARGS=(--python "$PYBIN")
fi

# ---------- 2. Зависимости ----------
echo "==> Зависимости"
uv pip install --quiet --target "$PAYLOAD/site-packages" "${UVARGS[@]}" "$ROOT[ocr,tray]"
rm -rf "$PAYLOAD/site-packages"/lexlock* "$PAYLOAD/site-packages"/app "$PAYLOAD/site-packages"/bin

# ---------- 3. Код ----------
echo "==> Код приложения"
for d in lexlock app templates samples; do cp -r "$ROOT/$d" "$PAYLOAD/$d"; done
mkdir -p "$PAYLOAD/scripts"
cp "$ROOT/scripts/launcher.py" "$PAYLOAD/scripts/"
cp "$ROOT/scripts/make_template.py" "$ROOT/scripts/demo_data.py" "$PAYLOAD/scripts/" 2>/dev/null || true
cp "$ROOT/README.md" "$PAYLOAD/"
find "$PAYLOAD" -name __pycache__ -type d -prune -exec rm -rf {} +
echo "$MODEL" > "$PAYLOAD/.lexlock_model"

# ---------- 4. Ollama ----------
echo "==> Ollama"
case "$PLAT" in
  win)   fetch "$OLLAMA_REL/ollama-windows-amd64.zip" "$CACHE/ollama-win.zip"
         unzip -q -o "$CACHE/ollama-win.zip" -d "$PAYLOAD/ollama" ;;
  linux) fetch "$OLLAMA_REL/ollama-linux-amd64.tar.zst" "$CACHE/ollama-linux.tar.zst"
         zstd -dc "$CACHE/ollama-linux.tar.zst" | tar -x -C "$PAYLOAD/ollama" ;;
  mac)   fetch "$OLLAMA_REL/ollama-darwin.tgz" "$CACHE/ollama-darwin.tgz"
         tar -xzf "$CACHE/ollama-darwin.tgz" -C "$PAYLOAD/ollama" ;;
esac
# Целимся в обычные ноутбуки: библиотеки CUDA/ROCm (~2 ГБ) не нужны.
rm -rf "$PAYLOAD"/ollama/lib/ollama/cuda_v* "$PAYLOAD"/ollama/lib/ollama/rocm* "$PAYLOAD"/ollama/lib/ollama/mlx*
[ "$PLAT" = win ] && OLL_BUNDLED="$PAYLOAD/ollama/ollama.exe" || OLL_BUNDLED="$PAYLOAD/ollama/bin/ollama"
[ "$PLAT" = mac ] && [ ! -x "$OLL_BUNDLED" ] && OLL_BUNDLED="$PAYLOAD/ollama/ollama"
[ "$PLAT" != win ] && chmod +x "$OLL_BUNDLED"

# ---------- 5. Модель ----------
echo "==> Модель $MODEL"
NAMEPART="${MODEL%%:*}"; TAG="${MODEL##*:}"
MAN="$MODELS_SRC/manifests/registry.ollama.ai/library/$NAMEPART/$TAG"
if [ ! -f "$MAN" ]; then
    echo "    Нет локально — скачиваю через Ollama..."
    if [ "$PLAT" != win ]; then
        OLL="$OLL_BUNDLED"
    elif command -v ollama >/dev/null 2>&1; then
        OLL="$(command -v ollama)"
    else
        # Кросс-сборка под Windows: берём Ollama под хост-систему только чтобы скачать модель.
        HOSTDIR="$CACHE/ollama-host"; mkdir -p "$HOSTDIR"
        if [ "$HOST" = Linux ]; then
            fetch "$OLLAMA_REL/ollama-linux-amd64.tar.zst" "$CACHE/ollama-linux.tar.zst"
            zstd -dc "$CACHE/ollama-linux.tar.zst" | tar -x -C "$HOSTDIR"
            OLL="$HOSTDIR/bin/ollama"
        else
            fetch "$OLLAMA_REL/ollama-darwin.tgz" "$CACHE/ollama-darwin.tgz"
            tar -xzf "$CACHE/ollama-darwin.tgz" -C "$HOSTDIR"
            OLL="$HOSTDIR/ollama"; [ -x "$OLL" ] || OLL="$HOSTDIR/bin/ollama"
        fi
        chmod +x "$OLL"
    fi
    OLLAMA_MODELS="$MODELS_SRC" OLLAMA_HOST=127.0.0.1:11499 "$OLL" serve >/dev/null 2>&1 & SPID=$!
    for _ in $(seq 1 30); do curl -s -m 1 http://127.0.0.1:11499/api/tags >/dev/null 2>&1 && break; sleep 1; done
    OLLAMA_HOST=127.0.0.1:11499 "$OLL" pull "$MODEL"
    kill "$SPID" 2>/dev/null || true
fi
mkdir -p "$PAYLOAD/models/manifests/registry.ollama.ai/library/$NAMEPART" "$PAYLOAD/models/blobs"
cp "$MAN" "$PAYLOAD/models/manifests/registry.ollama.ai/library/$NAMEPART/$TAG"
python3 -c "
import json
m=json.load(open('$MAN'))
for d in [m['config']['digest']]+[l['digest'] for l in m['layers']]: print(d.replace(':','-'))
" | while read -r b; do cp "$MODELS_SRC/blobs/$b" "$PAYLOAD/models/blobs/$b"; done

# ---------- 6. Запуск ----------
echo "==> Запускатор"
if [ "$PLAT" = win ]; then
cat > "$PAYLOAD/Запустить ЛексЛок.bat" <<'BAT'
@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "LEXLOCK_MODEL=qwen2.5:3b"
if exist .lexlock_model set /p LEXLOCK_MODEL=<.lexlock_model
set "LEXLOCK_OFFLINE=1"
set "LEXLOCK_LLM_EXTRACT=1"
set "LEXLOCK_PORT=8765"
set "LEXLOCK_WORKSPACE=%~dp0workspace"
set "LEXLOCK_OLLAMA_URL=http://127.0.0.1:11435"
set "OLLAMA_HOST=127.0.0.1:11435"
set "OLLAMA_NO_CLOUD=1"
set "OLLAMA_MODELS=%~dp0models"
set "PYTHONNOUSERSITE=1"
if not exist workspace mkdir workspace

echo ЛексЛок запускается. Это окно можно свернуть. Закрыть программу: кнопка "Остановить" в окне ЛексЛока.
curl -s --max-time 2 http://127.0.0.1:11435/api/tags >nul 2>&1
if errorlevel 1 (
    start "LexLockOllama" /min "%~dp0ollama\ollama.exe" serve
    timeout /t 4 /nobreak >nul
)
start "LexLockServer" /min "%~dp0python\python.exe" scripts\launcher.py --no-browser

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
rem Ждём окончания работы сервера и гасим Ollama, чтобы не держать память.
:alive
timeout /t 5 /nobreak >nul
curl -s --max-time 1 http://127.0.0.1:%LEXLOCK_PORT%/api/health >nul 2>&1
if not errorlevel 1 goto alive
taskkill /f /t /fi "WINDOWTITLE eq LexLockOllama*" >nul 2>&1
exit /b 0
:fail
echo Не удалось запустить. Сообщите разработчику.
pause
BAT
cat > "$PAYLOAD/ПРОЧТИ МЕНЯ.txt" <<'TXT'
ЛексЛок - офлайн-версия для Windows. Интернет НЕ нужен.

1. Распакуйте архив целиком в любую папку (например, C:\LexLock). Не запускайте из окна архива.
2. Дважды щёлкните "Запустить ЛексЛок.bat". Первый запуск может занять до минуты.
3. Откроется браузер со страницей http://127.0.0.1:8765.
4. Документы лежат в папке workspace рядом с программой.

Если Windows пишет "защитили ваш компьютер" - "Подробнее" - "Выполнить в любом случае".
Нужно ~8 ГБ ОЗУ и ~5 ГБ свободного места.
TXT
else
cat > "$PAYLOAD/lexlock-start.sh" <<'SH'
#!/bin/bash
# Запуск «ЛексЛока» из готового пакета. Данные пользователя - в ~/LexLock.
HERE="$(cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")" && pwd)"
DATA="${LEXLOCK_DATA:-$HOME/LexLock}"
LOG="$DATA/lexlock.log"
PORT=8765
OPORT=11435
URL="http://127.0.0.1:$PORT"
mkdir -p "$DATA/workspace"
[ -z "$(ls -A "$DATA/workspace" 2>/dev/null)" ] && cp -R "$HERE/samples/." "$DATA/workspace/" 2>/dev/null

say() {
    if command -v zenity >/dev/null 2>&1; then zenity --error --title="ЛексЛок" --text="$1" --width=420 2>/dev/null
    elif command -v kdialog >/dev/null 2>&1; then kdialog --title "ЛексЛок" --error "$1" 2>/dev/null
    elif [ "$(uname -s)" = Darwin ]; then osascript -e "display dialog \"$1\" with title \"ЛексЛок\" buttons {\"OK\"}" >/dev/null 2>&1
    else echo "$1" >&2; fi
}

# Уже запущено - просто открыть браузер.
if curl -s --max-time 1 "$URL/api/health" >/dev/null 2>&1; then
    { command -v xdg-open >/dev/null && xdg-open "$URL" || open "$URL"; } >/dev/null 2>&1
    exit 0
fi

OLL="$HERE/ollama/bin/ollama"; [ -x "$OLL" ] || OLL="$HERE/ollama/ollama"
export LEXLOCK_MODEL="$(cat "$HERE/.lexlock_model" 2>/dev/null || echo qwen2.5:3b)"
export LEXLOCK_OFFLINE=1 LEXLOCK_LLM_EXTRACT=1 LEXLOCK_PORT=$PORT
export LEXLOCK_WORKSPACE="$DATA/workspace" LEXLOCK_OLLAMA_URL="http://127.0.0.1:$OPORT"
export OLLAMA_HOST="127.0.0.1:$OPORT" OLLAMA_MODELS="$HERE/models" OLLAMA_NO_CLOUD=1
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$HERE/site-packages:$HERE"

OPID=""
if ! curl -s --max-time 1 "http://127.0.0.1:$OPORT/api/tags" >/dev/null 2>&1; then
    "$OLL" serve >>"$LOG" 2>&1 & OPID=$!
fi
cleanup() { [ -n "$OPID" ] && kill "$OPID" 2>/dev/null; }
trap cleanup EXIT INT TERM

cd "$HERE" || exit 1
"$HERE/python/bin/python3" scripts/launcher.py --no-browser >>"$LOG" 2>&1 & SPID=$!

for _ in $(seq 1 90); do
    curl -s --max-time 1 "$URL/api/health" >/dev/null 2>&1 && break
    kill -0 "$SPID" 2>/dev/null || { say "ЛексЛок не запустился. Журнал: $LOG"; exit 1; }
    sleep 1
done
{ command -v xdg-open >/dev/null && xdg-open "$URL" || open "$URL"; } >/dev/null 2>&1
wait "$SPID"
SH
chmod +x "$PAYLOAD/lexlock-start.sh"
fi

# ---------- 7. Упаковка ----------
cd "$ROOT/dist"
case "$PLAT" in
win)
    rm -f "$OUTNAME.zip"
    python3 - "$OUTNAME" <<'PY'
import os, sys, zipfile
name = sys.argv[1]
with zipfile.ZipFile(name + ".zip", "w", zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True) as z:
    for d, _, files in os.walk(name):
        for f in files:
            p = os.path.join(d, f)
            big = os.path.getsize(p) > 50_000_000  # модель уже сжата
            z.write(p, p, compress_type=zipfile.ZIP_STORED if big else zipfile.ZIP_DEFLATED)
PY
    ls -lh "$OUTNAME.zip" ;;
linux)
    APPDIR="$ROOT/dist/LexLock.AppDir"
    rm -rf "$APPDIR"; mkdir -p "$APPDIR/usr"
    mv "$PAYLOAD" "$APPDIR/usr/lexlock"
    cp "$ROOT/packaging/linux/lexlock.png" "$APPDIR/lexlock.png"
    cat > "$APPDIR/lexlock.desktop" <<'DESK'
[Desktop Entry]
Type=Application
Name=ЛексЛок
Comment=Локальный офлайн ИИ-помощник юриста
Exec=AppRun
Icon=lexlock
Terminal=false
Categories=Office;Utility;
DESK
    printf '#!/bin/bash\nHERE="$(dirname "$(readlink -f "$0")")"\nexec "$HERE/usr/lexlock/lexlock-start.sh" "$@"\n' > "$APPDIR/AppRun"
    chmod +x "$APPDIR/AppRun"
    TOOL="$CACHE/appimagetool-x86_64.AppImage"
    fetch "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage" "$TOOL"
    chmod +x "$TOOL"
    # Без FUSE на сборке; сжатие zstd - модель всё равно несжимаема, но код ужмётся быстро.
    ARCH=x86_64 "$TOOL" --appimage-extract-and-run --comp zstd "$APPDIR" "$ROOT/dist/$OUTNAME.AppImage"
    rm -rf "$APPDIR"
    ls -lh "$ROOT/dist/$OUTNAME.AppImage" ;;
mac)
    APP="$ROOT/dist/dmgroot/ЛексЛок.app"
    rm -rf "$ROOT/dist/dmgroot"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
    mv "$PAYLOAD" "$APP/Contents/Resources/lexlock"
    cat > "$APP/Contents/MacOS/LexLock" <<'SH'
#!/bin/bash
exec "$(cd "$(dirname "$0")/../Resources/lexlock" && pwd)/lexlock-start.sh"
SH
    chmod +x "$APP/Contents/MacOS/LexLock"
    cat > "$APP/Contents/Info.plist" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>ЛексЛок</string>
<key>CFBundleDisplayName</key><string>ЛексЛок</string>
<key>CFBundleIdentifier</key><string>ru.lexlock.app</string>
<key>CFBundleExecutable</key><string>LexLock</string>
<key>CFBundleVersion</key><string>$VERSION</string>
<key>CFBundleShortVersionString</key><string>$VERSION</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSMinimumSystemVersion</key><string>12.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PL
    [ -f "$ROOT/packaging/macos/lexlock.icns" ] && { cp "$ROOT/packaging/macos/lexlock.icns" "$APP/Contents/Resources/"; }
    cat > "$ROOT/dist/dmgroot/Как открыть.txt" <<'TXT'
1. Перетащите ЛексЛок в папку "Программы".
2. Первый раз: правый клик по ЛексЛок - "Открыть" - "Открыть" (macOS предупреждает о неподписанных приложениях).
3. Откроется браузер со страницей http://127.0.0.1:8765. Интернет не нужен.
Документы: папка ~/LexLock/workspace.
TXT
    ln -s /Applications "$ROOT/dist/dmgroot/Программы"
    # Ad-hoc подпись: на Apple Silicon неподписанный код вообще не запускается.
    codesign --force --deep --sign - "$APP" 2>/dev/null || true
    rm -f "$ROOT/dist/$OUTNAME.dmg"
    hdiutil create -volname "ЛексЛок" -srcfolder "$ROOT/dist/dmgroot" -ov -format UDZO "$ROOT/dist/$OUTNAME.dmg"
    rm -rf "$ROOT/dist/dmgroot"
    ls -lh "$ROOT/dist/$OUTNAME.dmg" ;;
esac
