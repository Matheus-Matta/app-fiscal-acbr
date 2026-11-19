"""Cliente de exemplo do Comunicador Fiscal no modo NUVEM (docs/API.md).

Faz a cifra de ponta a ponta e fala com a API como um PDV/ERP. Só precisa de
`cryptography` (pip install cryptography); o HTTP é o da biblioteca padrão.

    export ACBR_URL=https://fiscal.suaempresa.com.br
    export ACBRLIB_TOKEN=...      # o mesmo do .env do comunicador
    export ACBR_E2E_KEY=...       # idem
    python cliente_nuvem.py
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ROTULO = "acbr-e2e-v1"


def _chave(chave_base64, sentido):
    """Uma chave por sentido ("pedido" ou "resposta"), derivada da ACBR_E2E_KEY."""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=f"{ROTULO} {sentido}".encode()).derive(base64.b64decode(chave_base64))


class SemResposta(Exception):
    """Nada confiável voltou (rede, 401, 403, 429, erro de cifra): trate como `incerto`."""


class Comunicador:
    def __init__(self, url, token, chave_e2e, tempo_limite=60):
        self.url, self.token, self.chave, self.tempo_limite = url.rstrip("/"), token, chave_e2e, tempo_limite

    def chamar(self, rota, corpo):
        """(status HTTP, resposta aberta). Levanta SemResposta quando não há resposta confiável."""
        ts = int(time.time())
        nonce_bruto = os.urandom(12)  # novo a cada tentativa: repetir um envelope dá 409
        nonce = base64.b64encode(nonce_bruto).decode()
        aad = f"{ROTULO}\nPOST\n{rota}\n{ts}\n{nonce}".encode()
        cifrado = AESGCM(_chave(self.chave, "pedido")).encrypt(nonce_bruto, json.dumps(corpo).encode(), aad)
        envelope = {"v": 1, "ts": ts, "nonce": nonce, "dados": base64.b64encode(cifrado).decode()}

        pedido = urllib.request.Request(self.url + rota, data=json.dumps(envelope).encode(), method="POST",
                                        headers={"Authorization": f"Bearer {self.token}",
                                                 "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(pedido, timeout=self.tempo_limite) as r:
                status, bruto = r.status, r.read()
        except urllib.error.HTTPError as erro:
            status, bruto = erro.code, erro.read()
        except OSError as erro:
            raise SemResposta(f"sem resposta: {erro}") from None

        try:
            selado = json.loads(bruto)
            aad = f"{ROTULO}\n{status}\n{nonce}".encode()
            claro = AESGCM(_chave(self.chave, "resposta")).decrypt(
                base64.b64decode(selado["nonce"]), base64.b64decode(selado["dados"]), aad)
        except Exception:
            # Sem envelope (401, 403, 429, erro: sigilo) ou envelope que não abre: qualquer um
            # no caminho poderia ter forjado. Não é decisão fiscal.
            raise SemResposta(f"HTTP {status} sem resposta cifrada: {bruto[:200]!r}") from None
        return status, json.loads(claro)


if __name__ == "__main__":
    comunicador = Comunicador(os.environ["ACBR_URL"], os.environ["ACBRLIB_TOKEN"], os.environ["ACBR_E2E_KEY"])
    contexto = {
        "cnpj": "11222333000181", "uf": "SP", "ambiente": "2", "modelo": "65", "fuso": "-03:00",
        # Na nuvem o certificado e o CSC vão em toda chamada (nunca ficam no servidor):
        # "certificado": {"pfx_base64": base64.b64encode(open("a1.pfx", "rb").read()).decode(), "senha": "..."},
        # "csc": {"id": "1", "token": "..."},
    }
    print(comunicador.chamar("/v1/status-servico", contexto))
