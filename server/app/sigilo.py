"""A cifra de ponta a ponta das chamadas: o certificado não anda em claro.

O corpo do pedido e o da resposta vão em AES-256-GCM, com uma chave que só o PDV e
este serviço têm (`ACBR_E2E_KEY`). Vale para o Docker e para o .exe, e é obrigatória:
sem chave, nenhuma operação fiscal é aceita. O formato está em README.md, para quem
implementa o outro lado.

Os dados autenticados amarram o pedido à rota e ao horário, e a resposta ao pedido e
ao status HTTP: quem está no meio não reaproveita um pedido em outra rota nem troca
um 503 por 200. Um `nonce` já visto é recusado dentro da janela.
"""
import base64
import binascii
import json
import os
import time

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app import sefaz

VERSAO = 1
ROTULO = "acbr-e2e-v1"
JANELA_SEGUNDOS = 300

_vistos = {}


class Recusa(Exception):
    """O envelope não passou. A resposta sai em claro: não há com o que selar."""

    def __init__(self, status, motivo, mensagem):
        super().__init__(mensagem)
        self.status, self.motivo, self.mensagem = status, motivo, mensagem


def _decodificar(valor):
    if not isinstance(valor, str):
        raise ValueError("não é texto")
    return base64.b64decode(valor, validate=True)


def validar_chave(bruta, token=""):
    """Os 32 bytes da chave, ou ValueError dizendo o que está errado."""
    try:
        chave = _decodificar(bruta)
    except (binascii.Error, ValueError):
        chave = b""
    if len(chave) != 32:
        raise ValueError("ACBR_E2E_KEY inválida: use 32 bytes em base64 (openssl rand -base64 32).")
    # O token anda no cabeçalho, em claro: igual a ele, a chave não protegeria nada.
    if bruta == token:
        raise ValueError("ACBR_E2E_KEY não pode ser igual ao ACBRLIB_TOKEN.")
    return chave


def _chave_do_ambiente():
    try:
        return validar_chave(os.environ.get("ACBR_E2E_KEY", ""), os.environ.get("ACBRLIB_TOKEN", ""))
    except ValueError as erro:
        raise sefaz.FalhaDeConfiguracao(str(erro), "e2e_sem_chave") from None


def _derivar(chave, sentido):
    # Uma chave por sentido: um pedido capturado nunca passa por resposta.
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=f"{ROTULO} {sentido}".encode()).derive(chave)


def _aad_pedido(metodo, caminho, ts, nonce):
    return f"{ROTULO}\n{metodo}\n{caminho}\n{ts}\n{nonce}".encode()


def _aad_resposta(status, nonce_pedido):
    return f"{ROTULO}\n{status}\n{nonce_pedido}".encode()


def _cifrar(chave, dados, aad_de):
    nonce_bruto = os.urandom(12)
    nonce = base64.b64encode(nonce_bruto).decode()
    return nonce, base64.b64encode(AESGCM(chave).encrypt(nonce_bruto, dados, aad_de(nonce))).decode()


# ── lado do serviço ──────────────────────────────────────────────────────────
def abrir_pedido(envelope, metodo, caminho):
    """(corpo em claro, nonce do pedido). Falha com `Recusa`, sem dizer o conteúdo."""
    chave = _chave_do_ambiente()
    try:
        dados = json.loads(envelope)
        ts, nonce = dados["ts"], dados["nonce"]
        nonce_bruto = _decodificar(nonce)
        cifrado = _decodificar(dados["dados"])
        valido = dados["v"] == VERSAO and type(ts) is int and len(nonce_bruto) == 12
    except (ValueError, KeyError, TypeError, RecursionError, binascii.Error):
        valido = False
    if not valido:
        raise Recusa(400, "envelope_invalido", "Chamada sem a cifra de ponta a ponta.")

    agora = time.time()
    if abs(agora - ts) > JANELA_SEGUNDOS:
        raise Recusa(400, "fora_da_janela", "O relógio deste PC e o do serviço estão diferentes.")
    try:
        corpo = AESGCM(_derivar(chave, "pedido")).decrypt(
            nonce_bruto, cifrado, _aad_pedido(metodo, caminho, ts, nonce))
    except (InvalidTag, ValueError):
        raise Recusa(400, "nao_decifrou", "A ACBR_E2E_KEY do cliente não é a deste serviço.") from None

    # Só depois de autenticado: lixo de fora não ocupa memória aqui.
    for visto in [n for n, validade in _vistos.items() if validade < agora]:
        del _vistos[visto]
    if nonce in _vistos:
        raise Recusa(409, "repetida", "Esta chamada já foi recebida.")
    _vistos[nonce] = agora + 2 * JANELA_SEGUNDOS
    return corpo, nonce


def selar_resposta(corpo, status, nonce_pedido):
    chave = _derivar(_chave_do_ambiente(), "resposta")
    nonce, dados = _cifrar(chave, corpo, lambda _n: _aad_resposta(status, nonce_pedido))
    return {"v": VERSAO, "nonce": nonce, "dados": dados}


# ── lado do cliente (referência; os testes falam com a API por aqui) ─────────
def selar_pedido(corpo, metodo, caminho, chave, *, ts=None):
    """(envelope, nonce do pedido) para chamar a API. `chave` em base64."""
    ts = int(time.time()) if ts is None else ts
    cifra = _derivar(_decodificar(chave), "pedido")
    nonce, dados = _cifrar(cifra, corpo, lambda n: _aad_pedido(metodo, caminho, ts, n))
    return {"v": VERSAO, "ts": ts, "nonce": nonce, "dados": dados}, nonce


def abrir_resposta(envelope, status, nonce_pedido, chave):
    """O corpo em claro. Levanta InvalidTag se a resposta foi trocada no caminho."""
    return AESGCM(_derivar(_decodificar(chave), "resposta")).decrypt(
        _decodificar(envelope["nonce"]), _decodificar(envelope["dados"]),
        _aad_resposta(status, nonce_pedido))
