@echo off
rem Запуск «ЛексЛока» на Windows (офлайн). Скрипт лежит в packaging\windows.
cd /d "%~dp0..\.."

if not exist ".venv\Scripts\python.exe" (
    echo Ошибка: окружение не найдено. Сначала выполните:
    echo   powershell -ExecutionPolicy Bypass -File packaging\windows\install.ps1
    pause
    exit /b 1
)

set "LEXLOCK_MODEL=qwen2.5:3b"
if exist .lexlock_model set /p LEXLOCK_MODEL=<.lexlock_model
set "LEXLOCK_OFFLINE=1"
set "LEXLOCK_LLM_EXTRACT=1"
set "LEXLOCK_PORT=8765"

rem Ollama: поднять, если не отвечает
curl -s --max-time 2 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo Запускаю Ollama...
    start "" /b ollama serve
    timeout /t 3 /nobreak >nul
)

echo Открой http://127.0.0.1:%LEXLOCK_PORT%
start "" "http://127.0.0.1:%LEXLOCK_PORT%"
".venv\Scripts\python.exe" -m app.server
