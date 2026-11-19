# Compila a ACBrLibNFe para Windows 64 bits a partir do código aberto do Projeto ACBr
# (LGPL) e monta o pacote que o comunicador instala (app/instalador.py):
#
#   ACBrNFe64.dll + OpenSSL + libxml2 (as DLLs do próprio ACBr) + Schemas\*.xsd
#
# É o mesmo projeto e o mesmo modo de compilação MT da lib de Linux, no modo
# win64-x86_64-MT. Precisa do Lazarus 64 bits (lazbuild) e de um cliente SVN.
#
#   .\compilar-acbrlib.ps1                  # última revisão do trunk2
#   .\compilar-acbrlib.ps1 -Revisao 48608   # uma revisão fixa
#
# Sai em windows\lib (vai junto no .exe do desktop e do serviço) e em
# windows\pacote\acbrlib-nfe-windows-x64-r<rev>.zip, com o SHA-256 da DLL.
param(
    [string]$Revisao = "HEAD",
    [string]$Trabalho = (Join-Path $env:LOCALAPPDATA "acbr-build"),
    [string]$Lazbuild = "",
    [string]$Svn = "",
    # 1.1.1: a série que o próprio ACBr recomenda (DLLs\OpenSSL\Leia-me.txt).
    [ValidateSet("1.1.1.10", "3.1.3")][string]$OpenSSL = "1.1.1.10"
)
$ErrorActionPreference = "Stop"
$repositorio = "https://svn.code.sf.net/p/acbr/code/trunk2"

function Achar([string]$informado, [string]$nome, [string[]]$lugares) {
    if ($informado) { return $informado }
    $achado = Get-Command $nome -ErrorAction SilentlyContinue
    if ($achado) { return $achado.Source }
    foreach ($l in $lugares) { if (Test-Path $l) { return $l } }
    throw "Não achei $nome. Instale (winget install Lazarus.Lazarus / Slik.Subversion) ou informe o caminho."
}
$Svn = Achar $Svn "svn.exe" @("$env:ProgramFiles\SlikSvn\bin\svn.exe", "$env:ProgramFiles\TortoiseSVN\bin\svn.exe")
# Também o conjunto montado sem instalador (FPC extraído + lazbuild compilado do fonte)
# em $Trabalho: o instalador do Lazarus no SourceForge recusa download automatizado.
$Lazbuild = Achar $Lazbuild "lazbuild.exe" @((Join-Path $Trabalho "lazarus\lazbuild.exe"), "C:\lazarus\lazbuild.exe",
    "$env:ProgramFiles\Lazarus\lazbuild.exe", "$env:LOCALAPPDATA\Programs\Lazarus\lazbuild.exe")
$opcoesLazbuild = @("--pcp=$(Join-Path $Trabalho 'lazarus-config')", "--lazarusdir=$(Split-Path $Lazbuild)")
$fpcLocal = Join-Path $Trabalho "fpc\app\bin\i386-win32\fpc.exe"
if (Test-Path $fpcLocal) { $opcoesLazbuild += "--compiler=$fpcLocal" }

# ── o código: só as pastas que a lib usa ─────────────────────────────────────
$fontes = Join-Path $Trabalho "trunk2"
if (-not (Test-Path (Join-Path $fontes ".svn"))) {
    New-Item -ItemType Directory -Force $Trabalho | Out-Null
    & $Svn checkout --quiet --depth empty -r $Revisao $repositorio $fontes
    if ($LASTEXITCODE) { throw "svn checkout falhou" }
}
$pastas = @(
    "Fontes",
    "Projetos/ACBrLib/Fontes/Comum",
    "Projetos/ACBrLib/Fontes/NFe",
    "DLLs/OpenSSL/$OpenSSL/x64",
    "DLLs/LibXml2/x64",
    "Exemplos/ACBrDFe/Schemas/NFe"
)
Push-Location $fontes
try {
    foreach ($p in $pastas) {
        # Os pais vazios primeiro: o SVN não cria o caminho intermediário sozinho.
        # Só os que ainda não existem: --set-depth empty numa pasta já baixada APAGA as
        # irmãs (o NFe apagava o Comum de Projetos/ACBrLib/Fontes, e faltava ACBrLibConfig).
        $partes = $p -split "/"
        for ($i = 0; $i -lt $partes.Count - 1; $i++) {
            $pai = $partes[0..$i] -join "/"
            if (Test-Path $pai) { continue }
            & $Svn update --quiet --set-depth empty -r $Revisao $pai
            if ($LASTEXITCODE) { throw "svn update $pai falhou" }
        }
        Write-Host "svn: $p"
        & $Svn update --quiet --set-depth infinity -r $Revisao $p
        if ($LASTEXITCODE) { throw "svn update $p falhou" }
    }
    # A revisão das pastas baixadas, e não a da raiz: a raiz fica na do primeiro
    # checkout, e com -Revisao fixa o pacote saía com o número errado no nome.
    $rev = (& $Svn info --show-item revision "Fontes").Trim()
} finally { Pop-Location }

# ── compilar ─────────────────────────────────────────────────────────────────
$projeto = Join-Path $fontes "Projetos\ACBrLib\Fontes\NFe\ACBrLibNFeConsoleMT.lpi"
$env:ACBR_HOME = $fontes   # o $(ACBrDir) do projeto
Write-Host "lazbuild: win64-x86_64-MT (r$rev)"
& $Lazbuild @opcoesLazbuild --build-all --build-mode=win64-x86_64-MT --ws=nogui --no-write-project $projeto
if ($LASTEXITCODE) { throw "lazbuild falhou" }
$dll = Join-Path $fontes "Projetos\ACBrLib\Fontes\NFe\bin\Windows\CONSOLE-MT\ACBrNFe64.dll"
if (-not (Test-Path $dll)) { throw "A compilação não gerou $dll" }

# ── montar o pacote ──────────────────────────────────────────────────────────
$lib = Join-Path $PSScriptRoot "lib"
Remove-Item -Recurse -Force $lib -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force (Join-Path $lib "Schemas") | Out-Null
Copy-Item $dll $lib
Copy-Item (Join-Path $fontes "DLLs\OpenSSL\$OpenSSL\x64\*.dll") $lib
Copy-Item (Join-Path $fontes "DLLs\LibXml2\x64\*.dll") $lib
Copy-Item (Join-Path $fontes "Exemplos\ACBrDFe\Schemas\NFe\*.xsd") (Join-Path $lib "Schemas")
@"
ACBrLibNFe para Windows x64 (modo MT), compilada a partir do código aberto do
Projeto ACBr — https://projetoacbr.com.br — revisão $rev do trunk2
($repositorio).

O ACBr é distribuído sob a licença LGPL (GNU Lesser General Public License). O
código-fonte desta biblioteca é o do repositório acima, na revisão indicada,
compilado sem modificações com:
  lazbuild --build-all --build-mode=win64-x86_64-MT --ws=nogui ACBrLibNFeConsoleMT.lpi

OpenSSL $OpenSSL e libxml2: as DLLs distribuídas pelo próprio Projeto ACBr
(trunk2/DLLs), cada uma sob a sua licença.
"@ | Set-Content -Encoding utf8 (Join-Path $lib "LEIA-ME-ACBrLib.txt")
# Os textos das licenças vão junto da lib (no .exe, no desktop e no repositório).
Copy-Item -Recurse (Join-Path (Split-Path $PSScriptRoot) "licencas") (Join-Path $lib "LICENCAS")

$saida = Join-Path $PSScriptRoot "pacote"
New-Item -ItemType Directory -Force $saida | Out-Null
$zip = Join-Path $saida "acbrlib-nfe-windows-x64-r$rev.zip"
Remove-Item $zip -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $lib "*") -DestinationPath $zip

$shaDll = (Get-FileHash (Join-Path $lib "ACBrNFe64.dll") -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host ""
Write-Host "Pronto (r$rev):"
Write-Host "  pasta:   $lib"
Write-Host "  pacote:  $zip"
Write-Host "  ACBRLIB_SO_SHA256=$shaDll"
