' Запуск «ЛексЛока» из офлайн-пакета Windows: без чёрных окон, с ярлыками и окнами с ошибками.
' Сервер и Ollama стартуют скрытно, потом открывается браузер. Журнал: lexlock.log рядом с программой.
Option Explicit

Dim fso, sh, root, q, logFile, model, i, p, readyPort, quietFails
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
q = Chr(34)
root = fso.GetParentFolderName(WScript.ScriptFullName)
logFile = root & "\lexlock.log"

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
End Function

' Порт, на котором уже отвечает ЛексЛок (основной 8765, запасные - если он был занят).
Function FindPort()
    Dim n
    FindPort = 0
    For n = 8765 To 8774
        If IsReady("http://127.0.0.1:" & n & "/api/health") Then
            FindPort = n
            Exit Function
        End If
    Next
End Function

Sub MakeShortcut(path)
    On Error Resume Next
    Dim sc
    Set sc = sh.CreateShortcut(path)
    sc.TargetPath = sh.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\wscript.exe"
    sc.Arguments = q & WScript.ScriptFullName & q
    sc.WorkingDirectory = root
    If fso.FileExists(root & "\lexlock.ico") Then sc.IconLocation = root & "\lexlock.ico"
    sc.Description = "Локальный офлайн-помощник юриста"
    sc.Save
    Err.Clear
End Sub

' Ярлыки на рабочем столе и в меню «Пуск»: при первом запуске и если папку перенесли.
Sub EnsureShortcuts()
    On Error Resume Next
    Dim marker, old, ts
    marker = root & "\.shortcuts_done"
    old = ""
    If fso.FileExists(marker) Then
        Set ts = fso.OpenTextFile(marker, 1)
        old = Trim(ts.ReadAll())
        ts.Close
    End If
    If old <> root Then
        MakeShortcut sh.SpecialFolders("Programs") & "\ЛексЛок.lnk"
        MakeShortcut sh.SpecialFolders("Desktop") & "\ЛексЛок.lnk"
        Set ts = fso.CreateTextFile(marker, True)
        ts.Write root
        ts.Close
        sh.Popup "Ярлык «ЛексЛок» добавлен на рабочий стол и в меню «Пуск».", 6, "ЛексЛок", 64
    End If
    Err.Clear
End Sub

' Завершает только нашу Ollama (из папки программы), чужую не трогает.
Sub StopOllama()
    On Error Resume Next
    Dim svc, procs, pr, prefix
    prefix = LCase(root & "\ollama\")
    Set svc = GetObject("winmgmts:\\.\root\cimv2")
    Set procs = svc.ExecQuery("Select * From Win32_Process Where Name='ollama.exe'")
    For Each pr In procs
        If InStr(LCase(pr.ExecutablePath), prefix) = 1 Then pr.Terminate
    Next
    Err.Clear
End Sub

' --- Проверки ---
If InStr(LCase(root), "\temp\temp") > 0 Or Not fso.FileExists(root & "\python\python.exe") Then
    MsgBox "Программа запущена не из распакованной папки." & vbCrLf & vbCrLf & _
        "Закройте окно архива, нажмите на архиве правой кнопкой мыши -> «Извлечь всё», " & _
        "затем запустите ЛексЛок из получившейся папки.", 16, "ЛексЛок"
    WScript.Quit 1
End If

' Уже запущено - просто открыть браузер.
readyPort = FindPort()
If readyPort <> 0 Then
    sh.Run "http://127.0.0.1:" & readyPort
    WScript.Quit 0
End If

EnsureShortcuts

model = "qwen2.5:3b"
If fso.FileExists(root & "\.lexlock_model") Then
    model = Trim(fso.OpenTextFile(root & "\.lexlock_model", 1).ReadAll())
End If
If Not fso.FolderExists(root & "\workspace") Then fso.CreateFolder root & "\workspace"

Set p = sh.Environment("PROCESS")
p("LEXLOCK_MODEL") = model
p("LEXLOCK_OFFLINE") = "1"
p("LEXLOCK_LLM_EXTRACT") = "1"
p("LEXLOCK_PORT") = "8765"
p("LEXLOCK_WORKSPACE") = root & "\workspace"
p("LEXLOCK_OLLAMA_URL") = "http://127.0.0.1:11435"
p("OLLAMA_HOST") = "127.0.0.1:11435"
p("OLLAMA_NO_CLOUD") = "1"
p("OLLAMA_MODELS") = root & "\models"
p("PYTHONNOUSERSITE") = "1"

' Ollama на своём порту, чтобы не мешать установленной у пользователя.
If Not IsReady("http://127.0.0.1:11435/api/tags") Then
    sh.Run "cmd /s /c " & q & q & root & "\ollama\ollama.exe" & q & " serve >> " & q & logFile & q & " 2>&1" & q, 0, False
    For i = 1 To 20
        If IsReady("http://127.0.0.1:11435/api/tags") Then Exit For
        WScript.Sleep 1000
    Next
End If

sh.CurrentDirectory = root
sh.Run "cmd /s /c " & q & q & root & "\python\python.exe" & q & " scripts\launcher.py --no-browser >> " & q & logFile & q & " 2>&1" & q, 0, False

readyPort = 0
For i = 1 To 90
    readyPort = FindPort()
    If readyPort <> 0 Then Exit For
    WScript.Sleep 1000
Next

If readyPort = 0 Then
    StopOllama
    MsgBox "Не удалось запустить ЛексЛок." & vbCrLf & vbCrLf & _
        "Что можно сделать: перезагрузите компьютер и попробуйте снова. Если не помогло, " & _
        "отправьте разработчику файл:" & vbCrLf & logFile, 16, "ЛексЛок"
    WScript.Quit 1
End If

sh.Run "http://127.0.0.1:" & readyPort

' Ждём остановки сервера (кнопка «Остановить»), затем гасим Ollama, чтобы не держать память.
quietFails = 0
Do While quietFails < 3
    WScript.Sleep 5000
    If IsReady("http://127.0.0.1:" & readyPort & "/api/health") Then
        quietFails = 0
    Else
        quietFails = quietFails + 1
    End If
Loop
StopOllama
