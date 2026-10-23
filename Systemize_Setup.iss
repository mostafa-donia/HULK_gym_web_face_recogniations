#define MyAppName "Systemize Gym OS"
#define MyAppVersion "2.2"
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
OutputBaseFilename=Systemize_Setup_v2.2
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
; Main Native Desktop Shortcut (Zero Terminal / Clean Windows App)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\Systemize.exe"; WorkingDir: "{app}"; IconFilename: "{app}\gym_icon.ico"; Tasks: desktopicon

; Start Menu Shortcuts
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\Systemize.exe"; WorkingDir: "{app}"; IconFilename: "{app}\gym_icon.ico"
Name: "{autoprograms}\{#MyAppName}\إيقاف تشغيل Systemize (Stop)"; Filename: "{app}\STOP_SYSTEMIZE.bat"; WorkingDir: "{app}"
Name: "{autoprograms}\{#MyAppName}\تحديث النظام من GitHub"; Filename: "{app}\UPDATE_SYSTEMIZE.bat"; WorkingDir: "{app}"
Name: "{autoprograms}\{#MyAppName}\تشغيل مع شاشة الأوامر (Debug)"; Filename: "{app}\START_SYSTEMIZE.bat"; WorkingDir: "{app}"
Name: "{autoprograms}\{#MyAppName}\Uninstall Systemize"; Filename: "{uninstallexe}"

[Run]
; Auto-run migrations silently upon installation
Filename: "{app}\runtime\python.exe"; Parameters: "-s manage.pyc migrate --noinput"; WorkingDir: "{app}"; StatusMsg: "Configuring database schema..."; Flags: runhidden

; Apply custom gym onboarding parameters (Name, Theme, Logo, Clean vs Demo)
Filename: "{app}\runtime\python.exe"; Parameters: "-s manage.pyc setup_custom_gym --name ""{code:GetGymName}"" --theme ""{code:GetGymTheme}"" --logo ""{code:GetGymLogo}"" {code:GetDbModeFlag}"; WorkingDir: "{app}"; StatusMsg: "Configuring gym branding & database..."; Flags: runhidden

; Launch Systemize immediately after install
Filename: "{app}\Systemize.exe"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: postinstall nowait

[Code]
var
  BrandingPage: TInputQueryWizardPage;
  ThemeComboPage: TInputOptionWizardPage;
  DbModePage: TInputOptionWizardPage;
  LogoPage: TInputFileWizardPage;

procedure InitializeWizard;
begin
  // Page 1: Gym Name (Optional)
  BrandingPage := CreateInputQueryPage(wpSelectDir,
    'تخصيص هوية وبيانات الجيم (اختياري)',
    'Gym Branding & Identity (Optional)',
    'يمكنك إدخال اسم الجيم الخاص بك الآن لطباعته على الإيصالات ولوحة التحكم (يمكن تركه وسيتم استخدام الاسم الافتراضي):');
  BrandingPage.Add('اسم الصالة الرياضية (Gym Name):', False);
  BrandingPage.Values[0] := 'Systemize Gym';

  // Page 2: Theme Color Selection
  ThemeComboPage := CreateInputOptionPage(BrandingPage.ID,
    'طابع الألوان المعتمد (Theme Color)',
    'اختر لون وهوية النظام المفضلة لديك:',
    'يمكنك تغيير هذا الطابع في أي وقت من إعدادات النظام:',
    True, False);
  ThemeComboPage.Add('الأخضر الرياضي النيون (Neon Lime) - الافتراضي');
  ThemeComboPage.Add('الأخضر الزمردي الراقي (Dark Emerald)');
  ThemeComboPage.Add('أزرق تيتانيوم (Titanium Blue)');
  ThemeComboPage.Add('برتقالي حماسي (Blaze Orange)');
  ThemeComboPage.Add('أحمر طاقة (Power Red)');
  ThemeComboPage.Add('أرجواني مميز (Cyber Purple)');
  ThemeComboPage.Add('ذهبي ملكي (Royal Gold)');
  ThemeComboPage.Add('أسود أحادي داكن (Obsidian Monochrome)');
  ThemeComboPage.SelectedValueIndex := 0;

  // Page 3: Database mode (Clean vs Demo)
  DbModePage := CreateInputOptionPage(ThemeComboPage.ID,
    'تهيئة قاعدة البيانات (Database Setup)',
    'اختر نوع قاعدة البيانات التي تود البدء بها:',
    'حدد ما إذا كنت تريد البدء بنظام نظيف للعمل الفعلي، أو بيانات تجريبية كاملة للمعاينة:',
    True, False);
  DbModePage.Add('بدء نظيف للعمل الفعلي (Start Clean) - قاعدة بيانات فارغة جاهزة لإدخال المشتركين الحقيقيين فوراً');
  DbModePage.Add('بيانات تجريبية كاملة (Seed Demo Data) - مشتركين واشتراكات ومبيعات جاهزة لمعاينة النظام');
  DbModePage.SelectedValueIndex := 0;

  // Page 4: Optional Logo File
  LogoPage := CreateInputFilePage(DbModePage.ID,
    'شعار الجيم (اختياري - Gym Logo)',
    'تحديد ملف اللوجو الخاص بالصالة',
    'إذا كان لديك ملف شعار (PNG أو JPG)، يمكنك اختياره الآن ليتم ربطه تلقائياً بالنظام والإيصالات:');
  LogoPage.Add('مسار ملف اللوجو (اتركه فارغاً للاحتفاظ باللوجو الافتراضي):', 'Image files (*.png;*.jpg;*.jpeg;*.ico)|*.png;*.jpg;*.jpeg;*.ico|All files (*.*)|*.*', '.png');
end;

function GetGymName(Param: String): String;
begin
  Result := Trim(BrandingPage.Values[0]);
  if Result = '' then
    Result := 'Systemize Gym';
end;

function GetGymTheme(Param: String): String;
begin
  case ThemeComboPage.SelectedValueIndex of
    0: Result := 'lime';
    1: Result := 'emerald';
    2: Result := 'blue';
    3: Result := 'orange';
    4: Result := 'red';
    5: Result := 'purple';
    6: Result := 'gold';
    7: Result := 'monochrome';
  else
    Result := 'lime';
  end;
end;

function GetGymLogo(Param: String): String;
begin
  Result := Trim(LogoPage.Values[0]);
end;

function GetDbModeFlag(Param: String): String;
begin
  if DbModePage.SelectedValueIndex = 1 then
    Result := '--seed-demo'
  else
    Result := '--clear-data';
end;
