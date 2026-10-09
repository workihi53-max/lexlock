; Установщик «ЛексЛока» для Windows (Inno Setup 6).
; Сборка: iscc packaging\windows\installer.iss
; Требуется установленный Inno Setup (на CI: choco install innosetup).

#define MyAppName "ЛексЛок"
#define MyAppVersion "0.2.3"
#define MyAppPublisher "Legal AI Vault"

[Setup]
AppId={{8F2B9C41-6D2A-4E7B-9C51-000000000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\LexLock
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=LexLock-{#MyAppVersion}-win-setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern
InfoBeforeFile={#SourcePath}\pred_ustanovkoy.txt
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
; Кладём весь проект, кроме тяжёлых/генерируемых каталогов.
Source: "..\..\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; \
    Excludes: ".venv\*,.venv,workspace\*,workspace,dist\*,dist,.git\*,.git,__pycache__\*,__pycache__,*.pyc,.pytest_cache\*,.lexlock_model,*.egg-info\*"

[Icons]
Name: "{group}\ЛексЛок"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\packaging\windows\run.vbs"""; WorkingDir: "{app}"; Comment: "Запустить «ЛексЛок»"
Name: "{group}\Установить компоненты"; Filename: "powershell.exe"; \
    Parameters: "-ExecutionPolicy Bypass -File ""{app}\packaging\windows\install.ps1"""; \
    WorkingDir: "{app}"; Comment: "Поставить uv, Ollama, модель"
Name: "{autodesktop}\ЛексЛок"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\packaging\windows\run.vbs"""; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Run]
; Ставим компоненты (uv, Ollama, модель) сразу после копирования файлов.
Filename: "powershell.exe"; \
    Parameters: "-ExecutionPolicy Bypass -File ""{app}\packaging\windows\install.ps1"""; \
    WorkingDir: "{app}"; StatusMsg: "Устанавливаю окружение, Ollama и модель..."; \
    Flags: runhidden waituntilterminated
Filename: "{sys}\wscript.exe"; Parameters: """{app}\packaging\windows\run.vbs"""; \
    Description: "Запустить «ЛексЛок»"; Flags: postinstall nowait skipifsilent
