#!/usr/bin/env bash
# Sobe a imagem do comunicador como na nuvem e confere que ela emite de verdade:
# a ACBrLib embutida carregou (/health lib: true) e o atalho libxml2.so, sem o qual a
# lib carrega mas a ASSINATURA da primeira nota falha, existe.
#   bash .github/scripts/testar-imagem.sh <imagem>
set -euo pipefail
imagem="$1"
nome="comunicador-teste-$$"

docker run --rm --entrypoint sh "$imagem" -c 'test -e /usr/lib/libxml2.so' \
    || { echo "::error::Falta o atalho /usr/lib/libxml2.so na imagem"; exit 1; }

docker run -d --name "$nome" -p 127.0.0.1:18030:8030 \
    -e ACBR_MODO=nuvem \
    -e ACBRLIB_TOKEN="$(openssl rand -base64 48 | tr -d '\n/+=')" \
    -e ACBR_E2E_KEY="$(openssl rand -base64 32)" \
    "$imagem" > /dev/null
trap 'docker logs "$nome" 2>&1 | tail -30; docker rm -f "$nome" > /dev/null' EXIT

corpo=""
for _ in $(seq 1 60); do
    corpo=$(curl -s http://127.0.0.1:18030/health || true)
    [ -n "$corpo" ] && break
    sleep 1
done
echo "health: $corpo"
echo "$corpo" | grep -q '"lib":true' || { echo "::error::A imagem não carregou a ACBrLib embutida"; exit 1; }
echo "$corpo" | grep -q '"modo":"nuvem"' || { echo "::error::A imagem não subiu no modo nuvem"; exit 1; }
echo "ok: a imagem sobe na nuvem com a ACBrLib embutida"
