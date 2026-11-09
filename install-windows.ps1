# Установка «ЛексЛока» на Windows одной командой в PowerShell:
#
#   irm https://raw.githubusercontent.com/workihi53-max/lexlock/main/install-windows.ps1 | iex
#
# Скрипт скачивает свежий код ветки main, ставит Python-окружение, Ollama и модель,
# создаёт ярлык «ЛексЛок» в меню «Пуск» и запускает приложение. Повторный запуск
# не качает уже установленное.
$ErrorActionPreference = "Stop"
# Windows PowerShell 5.1: для загрузок нужен TLS 1.2.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Repo   = "workihi53-max/lexlock"
$Branch = "main"
$Dest   = Join-Path $env:LOCALAPPDATA "LexLock"
$Url    = "https://github.com/$Repo/archive/refs/heads/$Branch.zip"

Write-Host "==> ЛексЛок: установка в $Dest"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

# --- 1. Свежий код из main ---------------------------------------------------
Write-Host "==> Скачиваю свежий код ($Branch)"
$zip = Join-Path $env:TEMP "lexlock-$Branch.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
# Загрузка с докачкой и повторами (слабый интернет).
$curl = Join-Path $env:SystemRoot "System32\curl.exe"
$ok = $false
for ($i = 1; $i -le 15 -and -not $ok; $i++) {
    if (Test-Path $curl) {
        & $curl -L -f -C - --connect-timeout 20 -o $zip $Url
        $ok = ($LASTEXITCODE -eq 0)
    } else {
        try { Invoke-WebRequest -UseBasicParsing $Url -OutFile $zip; $ok = $true } catch { }
    }
    if (-not $ok) { Write-Host "    Связь оборвалась, повторяю (попытка $i из 15)..."; Start-Sleep -Seconds 5 }
}
if (-not $ok) { throw "Не удалось скачать код. Проверьте интернет и повторите." }
$tmp = Join-Path $env:TEMP "lexlock-src"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $tmp -Force
$src = Get-ChildItem $tmp -Directory | Select-Object -First 1
if (-not $src) { throw "Не удалось распаковать архив с кодом." }
Copy-Item (Join-Path $src.FullName "*") $Dest -Recurse -Force

# --- 2. Компоненты: uv, Ollama, модель, зависимости --------------------------
$install = Join-Path $Dest "packaging\windows\install.ps1"
if (-not (Test-Path $install)) { throw "В архиве нет packaging\windows\install.ps1" }
$ps = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
& $ps -ExecutionPolicy Bypass -File $install -NoRefresh
if ($LASTEXITCODE -ne 0) { throw "Установка компонентов завершилась с кодом $LASTEXITCODE. Подробности: $Dest\install.log" }

# --- 3. Ярлык в меню «Пуск» --------------------------------------------------
$launcher = Join-Path $Dest "packaging\windows\run.vbs"
if (Test-Path $launcher) {
    $wshell = New-Object -ComObject WScript.Shell
    $startMenu = [Environment]::GetFolderPath("Programs")
    $shortcut = $wshell.CreateShortcut((Join-Path $startMenu "ЛексЛок.lnk"))
    $shortcut.TargetPath = "wscript.exe"
    $shortcut.Arguments = '"{0}"' -f $launcher
    $shortcut.WorkingDirectory = $Dest
    $icon = Join-Path $Dest "packaging\windows\lexlock.ico"
    if (Test-Path $icon) { $shortcut.IconLocation = $icon }
    $shortcut.Description = "Локальный офлайн-помощник юриста"
    $shortcut.Save()
    Write-Host "    Ярлык добавлен в меню «Пуск»."
}

# --- 4. Запуск ---------------------------------------------------------------
if (Test-Path $launcher) {
    Start-Process "wscript.exe" -ArgumentList ('"{0}"' -f $launcher)
}

Write-Host ""
Write-Host "Готово. ЛексЛок запущен и открылся в браузере."
Write-Host "Ярлык «ЛексЛок» — в меню «Пуск». Документы кладите в: $(Join-Path $Dest 'workspace')"
