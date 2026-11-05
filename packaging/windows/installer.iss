; Установщик «ЛексЛока» для Windows (Inno Setup 6).
; Сборка: iscc packaging\windows\installer.iss
; Требуется установленный Inno Setup (на CI: choco install innosetup).

#define MyAppName "ЛексЛок"
#define MyAppVersion "0.3.0"
#define MyAppPublisher "Legal AI Vault"

[Setup]
AppId={{8F2B9C41-6D2A-4E7B-9C51-000000000001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppComments=Офлайн-помощник юриста: документы обрабатываются только на вашем компьютере
VersionInfoDescription=Установка ЛексЛока: программа, Python-окружение, Ollama и модель
DefaultDirName={localappdata}\LexLock
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
; Кладём только нужное. «Всё подряд» больше не используем: так в установщик
; не попадают приватные каталоги (заявка, ошибочки, promo-video), кэши и логи.
Source: "..\..\lexlock\*"; DestDir: "{app}\lexlock"; Flags: recursesubdirs createallsubdirs ignoreversion; \
    Excludes: "__pycache__\*,__pycache__,*.pyc"
Source: "..\..\app\*"; DestDir: "{app}\app"; Flags: recursesubdirs createallsubdirs ignoreversion; \
    Excludes: "__pycache__\*,__pycache__,*.pyc"
Source: "..\..\templates\*"; DestDir: "{app}\templates"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\..\samples\*"; DestDir: "{app}\samples"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\..\scripts\check_ram.py"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\..\scripts\make_template.py"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\..\scripts\demo_data.py"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\..\pyproject.toml"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\packaging\windows\*"; DestDir: "{app}\packaging\windows"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\ЛексЛок"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\packaging\windows\run.vbs"""; WorkingDir: "{app}"; Comment: "Запустить «ЛексЛок» (сервер + браузер)"
Name: "{group}\Установить компоненты"; Filename: "powershell.exe"; \
    Parameters: "-ExecutionPolicy Bypass -File ""{app}\packaging\windows\install.ps1"""; \
    WorkingDir: "{app}"; Comment: "Докачать Python-окружение, Ollama и модель (нужен интернет, ~2 ГБ)"
Name: "{autodesktop}\ЛексЛок"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\packaging\windows\run.vbs"""; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Run]
; Ставим компоненты (Python-окружение, Ollama, модель ~2 ГБ) сразу после копирования файлов.
; Папка установки: {app} (по умолчанию %LOCALAPPDATA%\LexLock). Документы: {app}\workspace.
Filename: "powershell.exe"; \
    Parameters: "-ExecutionPolicy Bypass -File ""{app}\packaging\windows\install.ps1"""; \
    WorkingDir: "{app}"; StatusMsg: "Шаг 2 из 2: ставлю Python-окружение, Ollama и модель (~2 ГБ, нужен интернет)…"; \
    Flags: runhidden waituntilterminated; BeforeInstall: ResetComponentStatus; AfterInstall: CheckComponentStatus
Filename: "{sys}\wscript.exe"; Parameters: """{app}\packaging\windows\run.vbs"""; \
    Description: "Запустить «ЛексЛок» (откроется в браузере)"; Flags: postinstall nowait skipifsilent

[Code]
procedure ResetComponentStatus;
begin
  DeleteFile(ExpandConstant('{app}\.lexlock_install_ok'));
end;

procedure CheckComponentStatus;
begin
  if not FileExists(ExpandConstant('{app}\.lexlock_install_ok')) then
    RaiseException('Не удалось установить компоненты. Подробности: ' +
      ExpandConstant('{app}\install.log') + '. Повторите через ярлык «Установить компоненты».');
end;
