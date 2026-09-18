; ==========================================================================
; 桌面电子宠物 - Inno Setup 安装包脚本
;
; 编译方式（两种）：
;   1. GUI：用 Inno Setup Compiler 打开本文件 → Compile (Ctrl+Shift+F9)
;   2. 命令行：python scripts/build_installer.py
;
; 产物：release/DesktopPet-Setup-{version}.exe
;
; 设计要点：
;   * 安装目录：{autopf}\DesktopPet（按用户权限自动选 Program Files 或本地目录）
;   * 桌面快捷方式 + 开始菜单 + 可选开机自启
;   * 卸载支持（控制面板可见）
;   * 不覆盖用户已有的 data/、output/、support/Chrome/Profile-*/cookies 文件
;   * 32/64 位自动判断（PyInstaller onedir 体积较大，默认按 64 位打包）
;
; 注意：iss 文件中 {#SourcePath} 是 InnoSetup 编译器预定义变量，
;       表示 iss 文件所在目录，等价于 scripts/ 目录。
; ==========================================================================

; —— 元数据配置（改版本号/产品名等 → 改这里，pet.spec 也要同步改）——
#define MyAppName          "净无欲-王涵桌面电子宠物"
#define MyAppNameEn        "DesktopPet"
#define MyAppExeName       "pet.exe"
#define MyAppVersion       "0.4.0"
#define MyAppPublisher     "锐尘ruichen"
#define MyAppCopyright     "© 2025-2026 mmfyxyk. 基于 MIT License 开源。"
#define MyAppDescription   "净无欲-王涵桌面电子宠物安装程序"
#define MyAppURL          "https://github.com/mmfyxyk/DesktopPet-Jingwuyu--Wanghan"

; 这些路径以 iss 文件所在 scripts/ 为基准
#define ProjectRoot        SourcePath + "\.."
#define DistPetDir        ProjectRoot + "\dist\pet"

[Setup]
AppId={{B7E2F3A1-9D4C-4E5F-8A1B-2C3D4E5F6A7B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright={#MyAppCopyright}
AppComments={#MyAppDescription}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppNameEn}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir={#ProjectRoot}\release
OutputBaseFilename=DesktopPet-Setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; —— setup.exe 属性「详细信息」字段（右键 setup.exe → 属性 → 详细信息）——
VersionInfoVersion={#MyAppVersion}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppDescription}
;VersionInfoTextVersion={#MyAppVersion}
;VersionInfoProductTextVersion={#MyAppVersion}

; 允许用户不创建桌面快捷方式
AllowNoIcons=yes

; 显式开启「选择目标位置」页（默认就是 yes，写出来更清楚）
DisableDirPage=no

; 卸载时询问是否保留用户数据（通过 [Code] 段 CurUninstallStepChanged 实现）
UninstallDisplayIcon={app}\{#MyAppExeName}
Uninstallable=yes
CreateUninstallRegKey=yes

; 许可协议（项目有 LICENSE）
; LicenseFile={#ProjectRoot}\LICENSE

; —— 安装包图标（setup.exe 用，与应用程序图标分开）——
; 放在 assets/WangHan/JingWuyu/icons/installer.ico；不存在时 Inno Setup 用默认图标。
#if FileExists(ProjectRoot + "\assets\WangHan\JingWuyu\icons\installer.ico")
  SetupIconFile={#ProjectRoot}\assets\WangHan\JingWuyu\icons\installer.ico
#endif

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "在桌面创建快捷方式"; GroupDescription: "附加任务:"; Flags: checkedonce
Name: "startupicon"; Description: "开机自动启动"; GroupDescription: "附加任务:"; Flags: unchecked

[Files]
; —— 主程序 ——
Source: "{#DistPetDir}\pet.exe"; DestDir: "{app}"; Flags: ignoreversion

; —— PyInstaller 依赖（含打包进 _internal/assets 的动画资源）——
Source: "{#DistPetDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

; —— 外部工具目录（ffmpeg/Chrome 等，打包时自动从项目 support/ 一起拷贝）——
; 递归拷贝整个 support/ 目录，用户安装后无需再手动放入
; Excludes: 排除 Chrome 用户数据（Profile-* 含 cookies/历史记录等，不能带进安装包）
Source: "{#ProjectRoot}\support\*"; DestDir: "{app}\support"; \
    Excludes: "\Chrome\Profile-*\*,\Chrome\Default\*,\Chrome\*\Cookies,\Chrome\*\History,\Chrome\*\Preferences"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; —— 创建运行时目录（用户数据/输出目录，不删用户已有内容）——
Name: "{app}\data"; Flags: uninsneveruninstall
Name: "{app}\output"; Flags: uninsneveruninstall
Name: "{app}\support"; Flags: uninsneveruninstall

[Icons]
; —— 开始菜单 ——
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"

; —— 桌面快捷方式（条件任务）——
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

; —— 开机自启（条件任务）——
Name: "{commonstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
; —— 安装完成后可选立即启动 ——
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; —— 卸载时清理程序自生成的日志和临时文件，不删 data/output/support 主体 ——
Type: filesandordirs; Name: "{app}\data\tmp"
Type: filesandordirs; Name: "{app}\*.log"

[Code]
// —— 安装后把 unins000.* 改名为 uninstall.*，并更新注册表 ——
procedure CurStepChanged(CurStep: TSetupStep);
var
  AppDir, RegKey: String;
begin
  if CurStep = ssPostInstall then
  begin
    AppDir := ExpandConstant('{app}');
    // 重命名 exe + dat（uninstaller 靠同名 .dat 读取卸载数据）
    if FileExists(AppDir + '\unins000.exe') then
    begin
      RenameFile(AppDir + '\unins000.exe', AppDir + '\uninstall.exe');
      if FileExists(AppDir + '\unins000.dat') then
        RenameFile(AppDir + '\unins000.dat', AppDir + '\uninstall.dat');
      // 更新注册表卸载命令路径
      RegKey := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B7E2F3A1-9D4C-4E5F-8A1B-2C3D4E5F6A7B}_is1';
      RegWriteStringValue(HKLM, RegKey, 'UninstallString', '"' + AppDir + '\uninstall.exe"');
    end;
  end;
end;

// —— 卸载时询问用户是否保留数据 ——
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if MsgBox('是否同时删除用户数据（data/、output/、support/ 下的 cookies、视频、Chrome 用户资料等）？' + #13#10 +
              '点击「是」将彻底清除，点击「否」将保留以便下次重装后继续使用。',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      DelTree(ExpandConstant('{app}\data'), True, True, True);
      DelTree(ExpandConstant('{app}\output'), True, True, True);
      DelTree(ExpandConstant('{app}\support\Chrome'), True, True, True);
    end;
  end;
end;
