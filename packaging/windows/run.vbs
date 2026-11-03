' Запуск «ЛексЛока» на Windows без чёрного окна консоли.
' Сервер стартует скрытно, затем открывается браузер. Журнал: lexlock.log в корне проекта.
Option Explicit

Dim fso, sh, dir, root, model, logFile, cmd, q, http, ollamaDir
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

' run.vbs лежит в packaging\windows — корень проекта двумя уровнями выше.
dir  = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(fso.GetParentFolderName(dir))
sh.CurrentDirectory = root
q = Chr(34)

If Not fso.FileExists(root & "\.venv\Scripts\python.exe") Then
    MsgBox "Компоненты не установлены. Запустите установщик «ЛексЛока».", 16, "ЛексЛок"
    WScript.Quit 1
End If

model = "qwen2.5:3b"
If fso.FileExists(root & "\.lexlock_model") Then
    model = Trim(fso.OpenTextFile(root & "\.lexlock_model").ReadAll())
End If
sh.Environment("PROCESS")("LEXLOCK_MODEL") = model
sh.Environment("PROCESS")("LEXLOCK_OFFLINE") = "1"
sh.Environment("PROCESS")("LEXLOCK_LLM_EXTRACT") = "1"

' Ollama могла быть поставлена только что — добавляем её каталоги в PATH процесса.
ollamaDir = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Ollama")
If fso.FolderExists(ollamaDir) Then
    sh.Environment("PROCESS")("Path") = ollamaDir & ";" & sh.Environment("PROCESS")("Path")
End If
ollamaDir = sh.ExpandEnvironmentStrings("%ProgramFiles%\Ollama")
If fso.FolderExists(ollamaDir) Then
    sh.Environment("PROCESS")("Path") = ollamaDir & ";" & sh.Environment("PROCESS")("Path")
End If

Function IsReady(url)
    On Error Resume Next
    Dim request
    IsReady = False
    Set request = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    request.setTimeouts 1000, 1000, 1000, 2000
    request.Open "GET", url, False
    request.Send
    If Err.Number = 0 Then IsReady = (request.Status = 200)
    Err.Clear
    On Error GoTo 0
End Function

' Повторный запуск открывает уже работающий сервер.
If IsReady("http://127.0.0.1:8765/api/health") Then
    sh.Run "http://127.0.0.1:8765"
    WScript.Quit 0
End If

' Сетевую ошибку проверяем внутри функции: она не должна пропустить запуск Ollama.
If Not IsReady("http://127.0.0.1:11434/api/tags") Then
    sh.Run "cmd /c ollama serve", 0, False
End If

logFile = root & "\lexlock.log"
' cmd /s /c требует внешнюю пару кавычек, если путь к Python содержит пробелы.
cmd = "cmd /s /c " & q & q & root & "\.venv\Scripts\python.exe" & q & " -m app.server >> " & q & logFile & q & " 2>&1" & q
sh.Run cmd, 0, False

Dim attempt
For attempt = 1 To 30
    If IsReady("http://127.0.0.1:8765/api/health") Then
        sh.Run "http://127.0.0.1:8765"
        WScript.Quit 0
    End If
    WScript.Sleep 1000
Next
MsgBox "Не удалось запустить ЛексЛок. Подробности: " & logFile, 16, "ЛексЛок"
WScript.Quit 1
