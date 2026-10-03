' Запуск «Вани» на Windows без чёрного окна консоли.
' Сервер стартует скрытно, затем открывается браузер. Журнал: vanya.log.
Option Explicit

Dim fso, sh, dir, model, logFile, cmd, q, http
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
q = Chr(34)

If Not fso.FileExists(dir & "\.venv\Scripts\python.exe") Then
    MsgBox "Компоненты не установлены. Запустите установщик «Вани».", 16, "Ваня"
    WScript.Quit 1
End If

model = "qwen2.5:3b"
If fso.FileExists(dir & "\.vanya_model") Then
    model = Trim(fso.OpenTextFile(dir & "\.vanya_model").ReadAll())
End If
sh.Environment("PROCESS")("VANYA_MODEL") = model
sh.Environment("PROCESS")("VANYA_OFFLINE") = "1"
sh.Environment("PROCESS")("VANYA_LLM_EXTRACT") = "1"

' Поднять Ollama, если не отвечает.
On Error Resume Next
Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
http.Open "GET", "http://127.0.0.1:11434/api/tags", False
http.Send
If http.Status <> 200 Then sh.Run "cmd /c ollama serve", 0, False
On Error GoTo 0

logFile = dir & "\vanya.log"
cmd = "cmd /c " & q & dir & "\.venv\Scripts\python.exe" & q & " -m app.server >> " & q & logFile & q & " 2>&1"
sh.Run cmd, 0, False

WScript.Sleep 4000
sh.Run "http://127.0.0.1:8765"
