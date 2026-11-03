$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
# Проверять синтаксис именно Windows PowerShell 5.1 также позволяет job в CI.
Get-ChildItem (Join-Path $Root "packaging/windows") -Filter *.ps1 | ForEach-Object {
    $tokens = $null
    $errorsFound = $null
    [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$errorsFound) | Out-Null
    if ($errorsFound.Count) { throw ($errorsFound | Out-String) }
}
. (Join-Path $Root "packaging/windows/common.ps1")
$Engine = (Get-Process -Id $PID).Path
Invoke-Checked $Engine @("-NoProfile", "-Command", "exit 0")
$Failed = $false
try { Invoke-Checked $Engine @("-NoProfile", "-Command", "exit 7") } catch { $Failed = $true }
if (-not $Failed) { throw "Native failure was ignored" }

$script:Attempts = 0
function Invoke-WebRequest {
    param($Uri, $TimeoutSec, [switch]$UseBasicParsing)
    $script:Attempts++
    if ($script:Attempts -lt 3) { throw "Not ready" }
}
function Start-Sleep { param($Seconds) }
Wait-Ollama -Attempts 3
if ($script:Attempts -ne 3) { throw "Readiness retries failed" }
$script:Attempts = 0
$Failed = $false
try { Wait-Ollama -Attempts 2 } catch { $Failed = $true }
if (-not $Failed) { throw "Readiness failure was ignored" }
Write-Host "PASS: PowerShell syntax, native exit codes, readiness retries and failure"
