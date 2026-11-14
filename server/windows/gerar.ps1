# Gera windows\saida\AcbrFiscal\AcbrFiscal.exe e windows\saida\AcbrFiscal-Setup.exe.
# Precisa de Python 3.12 e do Inno Setup 6. A lib da ACBr vai em windows\lib.
param(
    [string]$Python = "python",
    [string]$Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    [switch]$Teste
)
$ErrorActionPreference = "Stop"
$servidor = Split-Path $PSScriptRoot
$saida = Join-Path $PSScriptRoot "saida"
$trabalho = Join-Path ([IO.Path]::GetTempPath()) "acbrfiscal-build"

& $Python -m pip install -q -r (Join-Path $servidor "requirements.txt") pyinstaller
if ($LASTEXITCODE) { throw "pip falhou" }

& $Python -m PyInstaller --noconfirm --clean --onedir --console --name AcbrFiscal `
    --distpath $saida --workpath $trabalho --specpath $trabalho `
    --paths $servidor `
    --add-data "$servidor\config\ACBrLib.ini;config" `
    --hidden-import app.simulador --hidden-import app.acbrlib `
    --collect-submodules uvicorn `
    (Join-Path $PSScriptRoot "servico.py")
if ($LASTEXITCODE) { throw "PyInstaller falhou" }

$opcoes = @()
if ($Teste) { $opcoes += "/DTESTE" }
& $Iscc @opcoes (Join-Path $PSScriptRoot "instalador.iss")
if ($LASTEXITCODE) { throw "Inno Setup falhou" }
Get-Item (Join-Path $saida "AcbrFiscal-Setup.exe") | Select-Object FullName, Length
