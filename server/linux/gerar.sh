#!/usr/bin/env bash
# Gera server/linux/saida/AcbrFiscal/AcbrFiscal: o comunicador empacotado para Linux x64
# (PyInstaller), com a ACBrLib de server/embutida/ ao lado (lib/) e as licenças.
# É o que o desktop Linux (AppImage) embute — o equivalente do `gerar.ps1 -SoExe`.
#
# Precisa de Python 3.12 (python3.12 ou PYTHON=...). As dependências vão num ambiente
# próprio (server/linux/.venv), não no Python do sistema.
#
# Gere numa distribuição com glibc antiga (Ubuntu 22.04, a do GitHub Actions): o binário
# roda nas mais novas, não o contrário. A ACBrLib exige glibc 2.34+.
set -euo pipefail

aqui="$(cd "$(dirname "$0")" && pwd)"
servidor="$(dirname "$aqui")"
saida="$aqui/saida"
trabalho="$(mktemp -d)"
trap 'rm -rf "$trabalho"' EXIT
python="${PYTHON:-python3.12}"
venv="$aqui/.venv"

if [ ! -x "$venv/bin/python" ]; then
    "$python" -m venv "$venv"
fi
"$venv/bin/python" -m pip install -q -r "$servidor/requirements.txt" pyinstaller

"$venv/bin/python" -m PyInstaller --noconfirm --clean --onedir --console --name AcbrFiscal \
    --distpath "$saida" --workpath "$trabalho" --specpath "$trabalho" \
    --paths "$servidor" \
    --add-data "$servidor/config/ACBrLib.ini:config" \
    --hidden-import app.simulador --hidden-import app.acbrlib --hidden-import app.configuracao \
    --hidden-import app.instalador --hidden-import app.modo \
    --collect-submodules uvicorn \
    "$servidor/windows/servico.py"

# A ACBrLib de Linux, do repositório, vai junto (o comunicador a acha em lib/, ao lado).
lib="$saida/AcbrFiscal/lib"
rm -rf "$lib"
cp -r "$servidor/embutida" "$lib"
cp -r "$servidor/licencas" "$lib/LICENCAS"
test -f "$lib/libacbrnfe64.so" || { echo "falta server/embutida/libacbrnfe64.so" >&2; exit 1; }

ls -la "$saida/AcbrFiscal/AcbrFiscal"
echo "ACBrLib embutida: $(sha256sum "$lib/libacbrnfe64.so" | cut -d' ' -f1)"
