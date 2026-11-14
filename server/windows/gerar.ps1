# Gera windows\saida\AcbrFiscal\AcbrFiscal.exe e windows\saida\AcbrFiscal-Setup.exe.
# Precisa de Python 3.12 e do Inno Setup 6. A lib da ACBr vai em windows\lib.
#   -SoExe: só o AcbrFiscal.exe, sem o instalador (é o que o desktop embute).
# As dependências vão num ambiente próprio (windows\.venv), não no Python do sistema.
param(
    [string]$Python = "python",
    [string]$Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    [switch]$Teste,
    [switch]$SoExe
)
$ErrorActionPreference = "Stop"
$servidor = Split-Path $PSScriptRoot
$saida = Join-Path $PSScriptRoot "saida"
$trabalho = Join-Path ([IO.Path]::GetTempPath()) "acbrfiscal-build"
$venv = Join-Path $PSScriptRoot ".venv"
$py = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $py)) {
    & $Python -m venv $venv
    if ($LASTEXITCODE) { throw "venv falhou" }
}
& $py -m pip install -q -r (Join-Path $servidor "requirements.txt") pyinstaller
if ($LASTEXITCODE) { throw "pip falhou" }

& $py -m PyInstaller --noconfirm --clean --onedir --console --name AcbrFiscal `
    --distpath $saida --workpath $trabalho --specpath $trabalho `
    --paths $servidor `
    --add-data "$servidor\config\ACBrLib.ini;config" `
    --hidden-import app.simulador --hidden-import app.acbrlib --hidden-import app.configuracao --hidden-import app.instalador `
    --collect-submodules uvicorn `
    (Join-Path $PSScriptRoot "servico.py")
if ($LASTEXITCODE) { throw "PyInstaller falhou" }

# A lib de Windows, se estiver em windows\lib, vai junto (o comunicador a acha ao lado do .exe).
$lib = Join-Path $PSScriptRoot "lib"
if (Test-Path (Join-Path $lib "ACBrNFe64.dll")) {
    Copy-Item -Recurse -Force $lib (Join-Path $saida "AcbrFiscal\lib")
    Write-Host "ACBrLib embutida de $lib"
}

if ($SoExe) {
    Get-Item (Join-Path $saida "AcbrFiscal\AcbrFiscal.exe") | Select-Object FullName, Length
    return
}

$opcoes = @()
if ($Teste) { $opcoes += "/DTESTE" }
& $Iscc @opcoes (Join-Path $PSScriptRoot "instalador.iss")
if ($LASTEXITCODE) { throw "Inno Setup falhou" }
Get-Item (Join-Path $saida "AcbrFiscal-Setup.exe") | Select-Object FullName, Length
