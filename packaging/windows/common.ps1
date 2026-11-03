# Внешние программы в Windows PowerShell 5.1 не бросают исключение при exit != 0.
function Invoke-Checked {
    param([Parameter(Mandatory=$true)][string]$Command, [string[]]$Arguments = @())
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Команда $Command завершилась с кодом $LASTEXITCODE. Подробности — в install.log."
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
