"""A configuração guardada: os emitentes (certificado, CSC, UF...) e o token de acesso.

Fica na pasta de dados (`ACBR_DATA_DIR`: `/app/data` no Docker, a do usuário no
desktop, `%PROGRAMDATA%\\AcbrFiscal` no serviço Windows) e é gravada pelas rotas
`/v1/config/*`, que o desktop usa, com a mesma cifra de ponta a ponta das notas.

- `configuracao.bin`: os emitentes, cifrados com AES-256-GCM e uma chave derivada
  da `ACBR_E2E_KEY`. Trocar a chave deixa o arquivo ilegível: cadastre de novo.
- `acesso.json`: o SHA-256 do token trocado pela API. Ele vale no lugar do
  `ACBRLIB_TOKEN` do .env; apagar o arquivo devolve o acesso ao token do .env.

A chamada continua podendo trazer tudo: o que vier nela vale sobre o guardado.
"""
import hashlib
import json
import logging
import os
import secrets
import threading
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app import certificados, modelos, sefaz, sigilo

log = logging.getLogger("acbr.configuracao")

CABECALHO = b"ACBRCFG1"
_AAD = b"acbr-cofre-v1"
_trava = threading.Lock()


def pasta():
    return Path(os.environ.get("ACBR_DATA_DIR") or "/app/data")


def _arquivo():
    return pasta() / "configuracao.bin"


def _arquivo_acesso():
    return pasta() / "acesso.json"


def _gravar(arquivo, dados):
    """Grava inteiro ou nada: um arquivo pela metade perderia a configuração."""
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    temporario = arquivo.with_name(arquivo.name + ".novo")
    descritor = os.open(temporario, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(descritor, "wb") as saida:
        saida.write(dados)
    os.replace(temporario, arquivo)


# ── o cofre dos emitentes ────────────────────────────────────────────────────
def _chave():
    return sigilo._derivar(sigilo._chave_do_ambiente(), "cofre")


def _ler():
    arquivo = _arquivo()
    if not arquivo.exists():
        return {"emitentes": {}}
    bruto = arquivo.read_bytes()
    try:
        if not bruto.startswith(CABECALHO):
            raise ValueError("cabeçalho")
        nonce, cifrado = bruto[len(CABECALHO):len(CABECALHO) + 12], bruto[len(CABECALHO) + 12:]
        dados = json.loads(AESGCM(_chave()).decrypt(nonce, cifrado, _AAD))
    except (InvalidTag, ValueError):
        raise sefaz.FalhaDeConfiguracao(
            f"A configuração guardada em {arquivo} não abre com a ACBR_E2E_KEY atual "
            "(a chave foi trocada?). Cadastre os emitentes de novo.", "configuracao_ilegivel") from None
    dados.setdefault("emitentes", {})
    return dados


def _salvar(dados):
    nonce = os.urandom(12)
    claro = json.dumps(dados, ensure_ascii=False).encode()
    _gravar(_arquivo(), CABECALHO + nonce + AESGCM(_chave()).encrypt(nonce, claro, _AAD))


def completar(pedido):
    """O pedido com o que faltou preenchido pelo emitente guardado.

    Sem CNPJ na chamada, vale o único emitente cadastrado. Campo que a chamada
    trouxe vale sobre o guardado; certificado e CSC vazios na chamada = os guardados.
    """
    emitentes = _ler()["emitentes"]
    cnpj = pedido.cnpj
    if not cnpj and len(emitentes) == 1:
        cnpj = next(iter(emitentes))
    guardado = emitentes.get(cnpj)
    if guardado:
        definidos = pedido.model_fields_set
        mudancas = {"cnpj": cnpj}
        for campo in ("uf", "ambiente", "modelo", "fuso"):
            if campo not in definidos or not getattr(pedido, campo):
                mudancas[campo] = guardado.get(campo, "")
        if not pedido.certificado.pfx_base64 and guardado.get("certificado"):
            mudancas["certificado"] = modelos.Certificado(**guardado["certificado"])
        if not pedido.csc.token and guardado.get("csc"):
            mudancas["csc"] = modelos.Csc(**guardado["csc"])
        pedido = pedido.model_copy(update=mudancas)

    if not pedido.cnpj or not pedido.uf:
        if len(emitentes) > 1 and not pedido.cnpj:
            raise sefaz.FalhaDeConfiguracao("Há mais de um emitente cadastrado: informe o cnpj na chamada.",
                                            "emitente_nao_informado")
        raise sefaz.FalhaDeConfiguracao(
            "Nenhum emitente configurado para esta chamada: cadastre o CNPJ, a UF e o certificado "
            "no Comunicador Fiscal (desktop) ou em /v1/config/emitente, ou envie-os na chamada.",
            "emitente_nao_configurado")
    return pedido


def resumo():
    """A configuração sem segredo nenhum: o que o desktop mostra."""
    emitentes = []
    for cnpj, dados in sorted(_ler()["emitentes"].items()):
        certificado, csc = dados.get("certificado") or {}, dados.get("csc") or {}
        emitentes.append({
            "cnpj": cnpj, "uf": dados["uf"], "ambiente": dados["ambiente"], "modelo": dados["modelo"],
            "fuso": dados.get("fuso", ""),
            "certificado": certificados.descrever(certificado.get("pfx_base64", ""), certificado.get("senha", "")),
            "csc": {"id": csc.get("id", ""), "configurado": bool(csc.get("token"))},
        })
    return {"emitentes": emitentes, "token": origem_do_token()}


def salvar_emitente(emitente: modelos.Emitente):
    with _trava:
        dados = _ler()
        anterior = dados["emitentes"].get(emitente.cnpj, {})
        certificado = (emitente.certificado.model_dump() if emitente.certificado is not None
                       else anterior.get("certificado") or {"pfx_base64": "", "senha": ""})
        csc = emitente.csc.model_dump() if emitente.csc is not None else anterior.get("csc") or {"id": "", "token": ""}
        if certificado["pfx_base64"]:
            # As mesmas recusas da emissão, agora na hora de gravar: senha, validade, CNPJ.
            certificados.conferir(modelos.Contexto(cnpj=emitente.cnpj, uf=emitente.uf,
                                                   certificado=modelos.Certificado(**certificado)), exigir=True)
        dados["emitentes"][emitente.cnpj] = {
            "uf": emitente.uf, "ambiente": emitente.ambiente, "modelo": emitente.modelo, "fuso": emitente.fuso,
            "certificado": certificado, "csc": csc,
        }
        _salvar(dados)
    log.info("emitente %s gravado (UF %s, ambiente %s)", emitente.cnpj, emitente.uf, emitente.ambiente)
    return resumo()


def remover_emitente(cnpj):
    with _trava:
        dados = _ler()
        if dados["emitentes"].pop(cnpj, None) is None:
            raise sefaz.FalhaDeConfiguracao(f"O emitente {cnpj} não está cadastrado.", "emitente_nao_configurado")
        _salvar(dados)
    log.info("emitente %s removido", cnpj)
    return resumo()


# ── o token de acesso ────────────────────────────────────────────────────────
def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _hash_guardado():
    try:
        return json.loads(_arquivo_acesso().read_text(encoding="utf-8"))["sha256"]
    except FileNotFoundError:
        return None
    except (ValueError, KeyError, TypeError):
        log.error("%s ilegível: valendo o ACBRLIB_TOKEN do ambiente", _arquivo_acesso())
        return None


def origem_do_token():
    if _hash_guardado():
        return "configurado"
    return "ambiente" if os.environ.get("ACBRLIB_TOKEN") else "ausente"


def token_confere(recebido):
    """None quando não há token nenhum configurado; senão, se o recebido confere."""
    guardado = _hash_guardado()
    if guardado:
        return secrets.compare_digest(_hash(recebido), guardado)
    esperado = os.environ.get("ACBRLIB_TOKEN", "")
    if not esperado:
        return None
    return secrets.compare_digest(recebido.encode(), esperado.encode())


def trocar_token(novo=""):
    """Grava o novo token (ou gera um) e o devolve: é a única vez que ele aparece."""
    novo = novo.strip() or secrets.token_urlsafe(32)
    if len(novo) < 16:
        raise sefaz.DocumentoInvalido("O token precisa de ao menos 16 caracteres.", "token_curto")
    if any(c.isspace() or c == "#" for c in novo) or not novo.isascii():
        raise sefaz.DocumentoInvalido("O token não pode ter espaço, '#' nem acento.", "token_invalido")
    if novo == os.environ.get("ACBR_E2E_KEY", ""):
        raise sefaz.DocumentoInvalido("O token não pode ser igual à ACBR_E2E_KEY.", "token_invalido")
    with _trava:
        _gravar(_arquivo_acesso(), json.dumps({"sha256": _hash(novo)}).encode())
    log.info("token de acesso trocado pela API")
    return novo
