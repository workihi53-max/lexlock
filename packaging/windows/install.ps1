# Установка «ЛексЛока» на Windows. Запуск из PowerShell:
#   powershell -ExecutionPolicy Bypass -File packaging\windows\install.ps1
$ErrorActionPreference = "Stop"
# PowerShell 5.1: для загрузок нужен TLS 1.2 и режим без Internet Explorer.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
. (Join-Path $PSScriptRoot "common.ps1")
$env:Path = "$env:USERPROFILE\.local\bin;$env:USERPROFILE\.cargo\bin;$env:LOCALAPPDATA\Programs\Ollama;$env:ProgramFiles\Ollama;$env:Path"

# Скрипт лежит в packaging\windows — корень проекта ищем вверх до pyproject.toml.
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = $Dir
while ($Root -and -not (Test-Path (Join-Path $Root "pyproject.toml"))) {
    $Parent = Split-Path -Parent $Root
    if (-not $Parent -or $Parent -eq $Root) { $Root = $null; break }
    $Root = $Parent
}
if (-not $Root) {
    Write-Host "Не удалось найти корень проекта (pyproject.toml). Запустите скрипт из папки проекта." -ForegroundColor Red
    exit 1
}
Set-Location $Root
Start-Transcript -Path (Join-Path $Root "install.log") -Force | Out-Null
$ReadyFile = Join-Path $Root ".lexlock_install_ok"
Remove-Item $ReadyFile -ErrorAction SilentlyContinue
try {
Write-Host "=== ЛексЛок: установка компонентов ==="
Write-Host "Папка программы: $Root"
Write-Host "Документы будут здесь: $(Join-Path $Root 'workspace')"
Write-Host ""

# --- Шаг 1/6: менеджер пакетов uv (ставится в профиль пользователя) ---
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[1/6] Ставлю менеджер uv (нужен для Python-окружения)..."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "Не удалось установить uv" }
} else {
    Write-Host "[1/6] uv уже есть — пропускаю."
}
$env:Path = "$env:USERPROFILE\.local\bin;$env:USERPROFILE\.cargo\bin;$env:Path"

# --- Шаг 2/6: Ollama (запуск модели локально, ~500 МБ) ---
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "[2/6] Ставлю Ollama (программа для локального запуска модели)..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Invoke-Checked winget @("install", "--id", "Ollama.Ollama", "-e", "--silent", "--disable-interactivity", "--accept-source-agreements", "--accept-package-agreements")
    } else {
        $exe = Join-Path $env:TEMP "OllamaSetup.exe"
        Invoke-WebRequest -UseBasicParsing "https://ollama.com/download/OllamaSetup.exe" -OutFile $exe
        $signature = Get-AuthenticodeSignature $exe
        if ($signature.Status -ne "Valid") { throw "Не удалось подтвердить подпись установщика Ollama" }
        $setup = Start-Process $exe -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait -PassThru
        if ($setup.ExitCode -notin @(0, 3010)) { throw "Установка Ollama завершилась с кодом $($setup.ExitCode)" }
    }
} else {
    Write-Host "[2/6] Ollama уже есть — пропускаю."
}
$env:Path = "$env:LOCALAPPDATA\Programs\Ollama;$env:ProgramFiles\Ollama;$env:Path"

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { throw "Ollama не найдена после установки" }

# --- Шаг 3/6: Python-окружение только для ЛексЛока (.venv в папке программы) ---
Write-Host "[3/6] Создаю Python-окружение в папке программы (.venv)..."
if (-not (Test-Path ".venv\Scripts\python.exe")) { Invoke-Checked uv @("venv", "--python", "3.12", ".venv") }
Invoke-Checked uv @("pip", "install", "--python", ".venv\Scripts\python.exe", "-e", ".[ocr]")

# --- Шаг 4/6: Tesseract для чтения сканов (необязательно) ---
if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
    Write-Host "[4/6] Ставлю Tesseract для чтения сканов (необязательно)..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        try {
            Invoke-Checked winget @("install", "--id", "UB-Mannheim.TesseractOCR", "-e", "--silent", "--disable-interactivity", "--accept-source-agreements", "--accept-package-agreements")
        } catch { Write-Warning "OCR не установлен. Основные сценарии продолжат работать: $_" }
    } else {
        Write-Host "    Установите Tesseract вручную: https://github.com/UB-Mannheim/tesseract/wiki" -ForegroundColor Yellow
    }
}

# --- Шаг 5/6: языковая модель под вашу память (скачивается один раз, ~1-2 ГБ) ---
$ramGb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
$model = if ($ramGb -ge 10) { "qwen2.5:3b" } else { "qwen2.5:1.5b" }
[System.IO.File]::WriteAllText("$Root\.lexlock_model", $model)
Write-Host "[5/6] Памяти: $ramGb ГБ — качаю модель $model (~1-2 ГБ, это дольше всего)..."

# --- Ollama serve + модель ---
try {
    Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/tags -TimeoutSec 2 | Out-Null
} catch {
    Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
}
Wait-Ollama
# Ошибка загрузки обязательной модели не должна превращаться в «Готово».
Invoke-Checked ollama @("pull", $model)

# --- Шаг 6/6: шаблон договора и примеры ---
Write-Host "[6/6] Готовлю шаблон договора и примеры..."
Invoke-Checked ".venv\Scripts\python.exe" @("scripts\make_template.py")
Invoke-Checked ".venv\Scripts\python.exe" @("scripts\demo_data.py")

Set-Content -Path $ReadyFile -Value "ok" -Encoding ASCII
Write-Host ""
Write-Host "Готово. Программа здесь: $Root"
Write-Host "Документы кладите сюда: $(Join-Path $Root 'workspace')"
Write-Host "Запуск — ярлык «ЛексЛок» в меню Пуск (откроется в браузере)."
} catch {
    Write-Host "Установка не завершена: $_" -ForegroundColor Red
    if ($env:LEXLOCK_INSTALL_NONINTERACTIVE -ne "1") {
    $shell = New-Object -ComObject WScript.Shell
    $shell.Popup("Установка не завершена. Проверьте интернет и повторите через ярлык «Установить компоненты». Подробности: $Root\install.log", 0, "ЛексЛок", 16) | Out-Null
    }
    exit 1
} finally {
    Stop-Transcript | Out-Null
}
