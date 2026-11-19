; Compilado por gerar.ps1. A lib (ACBrNFe64.dll, dependências e Schemas) entra de
; windows\lib; sem ela o instalador sai igual e o /health acusa a falta.
; /DTESTE: instala sem administrador e sem tarefa, só para conferir os arquivos.
[Setup]
AppName=Acbr Fiscal
AppVersion=1.0
DefaultDirName={autopf}\AcbrFiscal
DefaultGroupName=Acbr Fiscal
DisableProgramGroupPage=yes
OutputDir=saida
OutputBaseFilename=AcbrFiscal-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#ifdef TESTE
PrivilegesRequired=lowest
#else
PrivilegesRequired=admin
#endif

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "saida\AcbrFiscal\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "lib\*"; DestDir: "{app}\lib"; Flags: recursesubdirs ignoreversion skipifsourcedoesntexist

[Run]
; O console fica aberto para digitar ou anotar o token do PDV.
Filename: "{cmd}"; Parameters: "/c ""{app}\AcbrFiscal.exe"" configurar & pause"; StatusMsg: "Definindo o token..."; Flags: waituntilterminated; Check: not WizardSilent
#ifndef TESTE
Filename: "{app}\AcbrFiscal.exe"; Parameters: "instalar-tarefa"; StatusMsg: "Registrando o início com o Windows..."; Flags: runhidden waituntilterminated
#endif

[UninstallRun]
#ifndef TESTE
Filename: "{app}\AcbrFiscal.exe"; Parameters: "remover-tarefa"; Flags: runhidden; RunOnceId: "RemoverTarefa"
#endif
