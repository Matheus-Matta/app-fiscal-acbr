"""A conferência do A1 que chega em cada chamada. Nada é gravado em disco.

As recusas saem antes de chegar à
lib, com um `motivo` claro. Viram `configuracao`, nunca contingência: a nota não sai
em tpEmis=9 por causa de uma senha errada. Nem o arquivo nem a senha vão para a
mensagem.
"""
import base64
import binascii
import datetime
import re

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from cryptography.x509.oid import NameOID

from app import sefaz

#: Um A1 real tem poucos KB; o teto só barra o envio do arquivo errado.
TAMANHO_MAXIMO = 256 * 1024

# Doze posições alfanuméricas e dois dígitos: vale também para o CNPJ alfanumérico.
_CNPJ_NO_NOME = re.compile(r"(?:^|[:\s])([0-9A-Z]{12}[0-9]{2})(?:$|\s)")


def _recusar(mensagem, motivo):
    return sefaz.FalhaDeConfiguracao(mensagem, motivo)


def _abrir_pfx(pfx_base64):
    try:
        pfx = base64.b64decode(pfx_base64, validate=True)
    except (binascii.Error, ValueError):
        raise _recusar("O certificado não está em base64.", "certificado_invalido") from None
    if len(pfx) > TAMANHO_MAXIMO:
        raise _recusar("O arquivo é grande demais para ser um .pfx.", "certificado_invalido")
    return pfx


def descrever(pfx_base64, senha):
    """Titular, CNPJ e validade do A1 guardado, para o desktop mostrar. Sem segredo."""
    if not pfx_base64:
        return {"presente": False}
    try:
        _chave, cert, _ = load_key_and_certificates(_abrir_pfx(pfx_base64), senha.encode())
    except (sefaz.FalhaFiscal, ValueError):
        return {"presente": True, "erro": "Não abre com a senha guardada."}
    except UnsupportedAlgorithm:
        return {"presente": True, "erro": "Formato antigo: só a ACBrLib consegue ler."}
    if cert is None:
        return {"presente": True, "erro": "O .pfx não tem certificado."}
    nomes = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    titular = nomes[0].value if nomes else ""
    achado = _CNPJ_NO_NOME.search(titular)
    vence_em = cert.not_valid_after_utc
    return {"presente": True, "titular": titular, "cnpj": achado.group(1) if achado else "",
            "vence_em": vence_em.date().isoformat(),
            "vencido": vence_em <= datetime.datetime.now(datetime.UTC)}


def conferir(pedido, *, exigir):
    """Devolve o pedido, ou recusa. `exigir`: sem a lib real, a falta do A1 não é o problema."""
    if not pedido.certificado.pfx_base64:
        if exigir:
            raise _recusar("A chamada não trouxe o certificado A1.", "certificado_ausente")
        return pedido
    pfx = _abrir_pfx(pedido.certificado.pfx_base64)
    try:
        chave, cert, _ = load_key_and_certificates(pfx, pedido.certificado.senha.encode())
    except ValueError:
        # A biblioteca usa a mesma mensagem para senha errada e arquivo corrompido.
        raise _recusar("A senha não abre este certificado, ou o arquivo não é um .pfx válido.",
                       "senha_invalida") from None
    except UnsupportedAlgorithm:
        return pedido  # A1 antigo (RC2/3DES): a ACBrLib lê, e ela decide ao assinar.
    if cert is None or chave is None:
        raise _recusar("O .pfx precisa conter o certificado e a chave privada.", "certificado_invalido")

    vence_em = cert.not_valid_after_utc
    if vence_em <= datetime.datetime.now(datetime.UTC):
        raise _recusar(f"O certificado venceu em {vence_em:%d/%m/%Y}.", "certificado_vencido")
    nomes = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    achado = _CNPJ_NO_NOME.search(nomes[0].value if nomes else "")
    cnpj = re.sub(r"[^0-9A-Z]", "", pedido.cnpj.upper())
    # A RAIZ (8 primeiras posições): o A1 da matriz assina a nota da filial.
    if achado and achado.group(1)[:8] != cnpj[:8]:
        raise _recusar(f"O certificado é do CNPJ {achado.group(1)}, e não do {cnpj}.", "cnpj_diferente")
    return pedido
