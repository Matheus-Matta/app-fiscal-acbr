"""O contrato com o cliente (server/README.md, "Operações").

Quem emite, onde e com qual certificado pode chegar em toda chamada ou ficar
guardado no comunicador (`configuracao.py`, o que o desktop grava). O que vier
na chamada vale sobre o guardado.
"""
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

UF = Literal["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB",
             "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"]
#: 1 = produção, 2 = homologação.
Ambiente = Literal["1", "2"]
Modelo = Literal["55", "65"]
#: Doze posições alfanuméricas e dois dígitos: vale também para o CNPJ alfanumérico.
PADRAO_CNPJ = r"^[0-9A-Z]{12}[0-9]{2}$"
PADRAO_FUSO = r"^$|^[+-]\d{2}:\d{2}$"


def normalizar_cnpj(valor):
    """Só letras e dígitos, em maiúscula: "11.222.333/0001-81" vira "11222333000181"."""
    return re.sub(r"[^0-9A-Za-z]", "", str(valor or "")).upper()


class Certificado(BaseModel):
    pfx_base64: str = ""
    senha: str = ""


class Csc(BaseModel):
    id: str = ""
    token: str = ""


class Contexto(BaseModel):
    referencia: str = ""
    modelo: Modelo = "65"
    ambiente: Ambiente = "2"
    # Vazios: valem os do emitente guardado (`configuracao.completar`).
    uf: UF | Literal[""] = ""
    cnpj: str = Field(default="", pattern=r"^$|" + PADRAO_CNPJ)
    # O fuso do dhEmi ("-03:00"). Vazio = vale o do sistema.
    fuso: str = Field(default="", pattern=PADRAO_FUSO)
    certificado: Certificado = Certificado()
    csc: Csc = Csc()

    _cnpj = field_validator("cnpj", mode="before")(normalizar_cnpj)


class Emitir(Contexto):
    ini: str = Field(min_length=1)
    tp_emis: Literal["1", "9"] = "1"  # "9" = só assina (contingência offline), não transmite


class Transmitir(Contexto):
    xml: str = Field(min_length=1)


class Consultar(Contexto):
    chave: str = Field(pattern=r"^\d{44}$")


class Cancelar(Contexto):
    chave: str = Field(pattern=r"^\d{44}$")
    protocolo: str = Field(min_length=1)
    # O limite da SEFAZ para o xJust do evento de cancelamento.
    justificativa: str = Field(min_length=15, max_length=255)


# ── configuração guardada ────────────────────────────────────────────────────
class Emitente(BaseModel):
    """O que o desktop/painel grava. `certificado`/`csc` ausentes = mantém o guardado."""

    cnpj: str = Field(pattern=PADRAO_CNPJ)
    uf: UF
    ambiente: Ambiente = "2"
    modelo: Modelo = "65"
    fuso: str = Field(default="", pattern=PADRAO_FUSO)
    certificado: Certificado | None = None
    csc: Csc | None = None

    _cnpj = field_validator("cnpj", mode="before")(normalizar_cnpj)


class RemoverEmitente(BaseModel):
    cnpj: str = Field(pattern=PADRAO_CNPJ)

    _cnpj = field_validator("cnpj", mode="before")(normalizar_cnpj)


class TrocarToken(BaseModel):
    """Vazio: o comunicador gera um."""

    token: str = ""


class InstalarLib(BaseModel):
    """Vazios: o pacote configurado no ambiente (ACBRLIB_PACOTE_URL/ACBRLIB_SO_SHA256)."""

    url: str = ""
    sha256: str = ""


class Vazio(BaseModel):
    pass
