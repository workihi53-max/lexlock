# Кодировка консоли: иначе русский текст дочернего powershell.exe превращается в «кракозябры».
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

# В Windows PowerShell 5.1 любой вывод native-команды в stderr (прогресс curl, «Resuming transfer»,
# прогресс ollama/uv) при $ErrorActionPreference = "Stop" превращается в NativeCommandError.
# Запускаем внешнюю программу с "Continue", а успех определяем только по коду выхода.
function Invoke-Native {
    param([Parameter(Mandatory=$true)][string]$Command, [string[]]$Arguments = @())
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Command @Arguments 2>&1 | ForEach-Object { Write-Host ("$_") }
        return $LASTEXITCODE
    } finally { $ErrorActionPreference = $prev }
}

# Внешние программы в Windows PowerShell 5.1 не бросают исключение при exit != 0.
function Invoke-Checked {
    param([Parameter(Mandatory=$true)][string]$Command, [string[]]$Arguments = @())
    $code = Invoke-Native $Command $Arguments
    if ($code -ne 0) {
        throw "Команда $Command завершилась с кодом $code. Подробности — в install.log."
    }
}

function Wait-Ollama {
    param([int]$Attempts = 30)
    for ($i = 0; $i -lt $Attempts; $i++) {
        try {
            Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/tags -TimeoutSec 2 | Out-Null
            return
        } catch {
            if ($i -lt ($Attempts - 1)) { Start-Sleep -Seconds 1 }
        }
    }
    throw "Ollama не запустилась. Повторите установку компонентов; подробности — в install.log."
}

# Загрузка с докачкой и повторами: на слабом интернете соединение часто рвётся.
function Get-FileResilient([string]$Url, [string]$OutFile) {
    $curl = Join-Path $env:SystemRoot "System32\curl.exe"
    for ($i = 1; $i -le 15; $i++) {
        if (Test-Path $curl) {
            $code = Invoke-Native $curl @("-sS", "-L", "-f", "-C", "-", "--connect-timeout", "20", "-o", $OutFile, $Url)
            if ($code -eq 0) { return }
        } else {
            try { Invoke-WebRequest -UseBasicParsing $Url -OutFile $OutFile; return } catch { }
        }
        Write-Host "    Связь оборвалась, повторяю (попытка $i из 15)..."
        Start-Sleep -Seconds 5
    }
    throw "Не удалось скачать $Url. Проверьте интернет и повторите."
}
