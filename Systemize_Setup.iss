#define MyAppName "Systemize Gym OS"
#define MyAppVersion "2.0"
#define MyAppPublisher "Systemize Tech"
#define MyAppURL "http://127.0.0.1:8000"
#define SourceDir "d:\move\career\gym system\dist\Systemize_Client_Release"

[Setup]
AppId={{D29E73A1-884B-4E32-9F10-6C2A7B8E9012}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName=C:\Systemize
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=d:\move\career\gym system\dist
OutputBaseFilename=Systemize_Setup_v2.0
SetupIconFile={#SourceDir}\gym_icon.ico
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
CloseApplications=force

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; 1. Preserve existing client database on upgrade
Source: "{#SourceDir}\gym_face.sqlite3"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall

; 2. Preserve existing member photos and invoices
Source: "{#SourceDir}\media\*"; DestDir: "{app}\media"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs uninsneveruninstall

; 3. All other compiled binaries, templates, static assets, and runtime
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: "gym_face.sqlite3,media\*"

[Icons]
; Main Silent Desktop Shortcut (Zero Terminal / Console completely hidden!)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\Systemize_Silent.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\gym_icon.ico"; Tasks: desktopicon

; Start Menu Shortcuts
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\Systemize_Silent.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\gym_icon.ico"
Name: "{autoprograms}\{#MyAppName}\إيقاف تشغيل Systemize (Stop)"; Filename: "{app}\STOP_SYSTEMIZE.bat"; WorkingDir: "{app}"
Name: "{autoprograms}\{#MyAppName}\تحديث النظام من GitHub"; Filename: "{app}\UPDATE_SYSTEMIZE.bat"; WorkingDir: "{app}"
Name: "{autoprograms}\{#MyAppName}\تشغيل مع شاشة الأوامر (Debug)"; Filename: "{app}\START_SYSTEMIZE.bat"; WorkingDir: "{app}"
Name: "{autoprograms}\{#MyAppName}\Uninstall Systemize"; Filename: "{uninstallexe}"

[Run]
; Auto-run migrations silently upon installation
Filename: "{app}\runtime\python.exe"; Parameters: "manage.pyc migrate --noinput"; WorkingDir: "{app}"; StatusMsg: "Configuring database schema..."; Flags: runhidden

; Optional: Launch Systemize immediately after install
Filename: "{sys}\wscript.exe"; Parameters: """{app}\Systemize_Silent.vbs"""; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: postinstall nowait
