# Установка «Вани» на Windows. Запуск из PowerShell:
#   powershell -ExecutionPolicy Bypass -File packaging\windows\install.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Test-Path (Join-Path $Root "..\pyproject.toml")) {
    $Root = (Resolve-Path (Join-Path $Root "..")).Path
}
Set-Location $Root
Write-Host "=== Ваня: установка ==="

# --- uv ---
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "==> Устанавливаю uv"
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

# --- Ollama ---
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "==> Устанавливаю Ollama"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
    } else {
        $exe = Join-Path $env:TEMP "OllamaSetup.exe"
        Invoke-WebRequest "https://ollama.com/download/OllamaSetup.exe" -OutFile $exe
        Start-Process $exe -ArgumentList "/VERYSILENT" -Wait
    }
    $env:Path = "$env:LOCALAPPDATA\Programs\Ollama;$env:Path"
}

# --- окружение Python (с OCR) ---
if (-not (Test-Path ".venv\Scripts\python.exe")) { uv venv --python 3.12 .venv }
uv pip install --python .venv\Scripts\python.exe -e ".[ocr]"

# --- OCR: Tesseract + русский ---
if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
    Write-Host "==> Устанавливаю Tesseract OCR"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id UB-Mannheim.TesseractOCR -e --accept-source-agreements --accept-package-agreements
    } else {
        Write-Host "    Установите Tesseract вручную: https://github.com/UB-Mannheim/tesseract/wiki" -ForegroundColor Yellow
    }
}

# --- модель по объёму ОЗУ ---
$ramGb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
$model = if ($ramGb -ge 10) { "qwen2.5:3b" } else { "qwen2.5:1.5b" }
[System.IO.File]::WriteAllText("$Root\.vanya_model", $model)
Write-Host "==> ОЗУ $ramGb ГБ, выбрана модель $model"

# --- Ollama serve + модель ---
try {
    Invoke-WebRequest http://127.0.0.1:11434/api/tags -TimeoutSec 2 | Out-Null
} catch {
    Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
}
ollama pull $model

# --- шаблон и тестовые данные ---
.venv\Scripts\python.exe scripts\make_template.py
.venv\Scripts\python.exe scripts\demo_data.py

Write-Host ""
Write-Host "Готово. Запустите run.bat"
