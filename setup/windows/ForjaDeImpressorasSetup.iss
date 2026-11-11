; ============================================================
;  Forja de Impressoras — Script de Instalação (Inno Setup 6)
; ============================================================
;
;  PRÉ-REQUISITOS antes de compilar:
;
;  1. Executar o build:
;       scripts\build.bat
;
;  2. Compilar via ISCC com /DAppVersion ou abrir este script
;     diretamente no Inno Setup Compiler.
;
;  A desinstalacao e livre (sem senha): use "Adicionar/Remover
;  Programas" ou o painel de controle.
; ============================================================

; Fonte unica da versao: arquivo VERSION, repassado pelo build.bat
; via /DAppVersion=... Compilar diretamente sem defini-la e erro.
#ifndef AppVersion
  #error "AppVersion nao definida. Compile via scripts\build.bat (le VERSION)."
#endif

[Setup]
AppId={{9B4C2E71-3A5D-4F82-9C10-7E2D5B6A8C34}
AppName=Forja de Impressoras
AppVersion={#AppVersion}
AppPublisher=Dok Solutions
AppPublisherURL=https://doksolutions.com.br
DefaultDirName={commonpf}\Forja de Impressoras
DefaultGroupName=Forja de Impressoras
OutputDir=..\..\dist\windows
OutputBaseFilename=ForjaDeImpressorasSetup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
PrivilegesRequired=admin
WizardStyle=modern
CloseApplications=yes
SetupIconFile=..\..\app\resources\icon.ico
UninstallDisplayIcon={app}\ForjaDeImpressoras.exe

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\..\dist\windows\ForjaDeImpressoras.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "Iniciar Forja de Impressoras.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Forja de Impressoras"; Filename: "{app}\Iniciar Forja de Impressoras.bat"; WorkingDir: "{app}"; IconFilename: "{app}\ForjaDeImpressoras.exe"
Name: "{commondesktop}\Forja de Impressoras"; Filename: "{app}\Iniciar Forja de Impressoras.bat"; WorkingDir: "{app}"; IconFilename: "{app}\ForjaDeImpressoras.exe"
Name: "{group}\Desinstalar Forja de Impressoras"; Filename: "{uninstallexe}"; IconFilename: "{app}\ForjaDeImpressoras.exe"

[Run]
Filename: "{app}\ForjaDeImpressoras.exe"; Description: "Iniciar a Forja de Impressoras apos a instalacao"; Flags: nowait runascurrentuser
