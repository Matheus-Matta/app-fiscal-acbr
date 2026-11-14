"""A iniciação do .exe grava o mesmo .env do Docker, e nunca troca chave em silêncio."""
import base64
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import sigilo  # noqa: E402
from windows import servico  # noqa: E402

CHAVE = base64.b64encode(b"c" * 32).decode()


@pytest.fixture
def dados(tmp_path, monkeypatch):
    monkeypatch.setenv("ACBR_DATA_DIR", str(tmp_path / "AcbrFiscal"))
    # A permissão real é conferida no .exe; aqui ela prenderia a limpeza do tmp_path.
    monkeypatch.setattr(servico, "_restringir", lambda _pasta: None)
    return tmp_path / "AcbrFiscal"


def test_enter_gera_token_e_chave_validos(dados):
    servico.configurar(entrada=lambda _pergunta: "")
    valores = servico.ler_env(dados / ".env")
    assert len(valores["ACBRLIB_TOKEN"]) >= 32
    assert sigilo.validar_chave(valores["ACBR_E2E_KEY"], valores["ACBRLIB_TOKEN"])
    assert valores["ACBR_SIMULADOR"] == "0" and valores["ACBR_ALLOWED_ORIGINS"] == ""


def test_grava_o_que_foi_digitado_sem_truncar_base64(dados):
    servico.configurar("meu-token", CHAVE, "http://127.0.0.1:8030")
    valores = servico.ler_env(dados / ".env")
    # A chave termina em "=": ler o .env não pode cortar esse caractere.
    assert valores == {"ACBRLIB_TOKEN": "meu-token", "ACBR_E2E_KEY": CHAVE,
                       "ACBR_ALLOWED_ORIGINS": "http://127.0.0.1:8030", "ACBR_SIMULADOR": "0"}


def test_nao_troca_o_que_ja_esta_configurado_sem_pedir(dados):
    servico.configurar("primeiro", CHAVE, "")
    with pytest.raises(SystemExit):
        servico.configurar("segundo", CHAVE, "")
    assert servico.ler_env(dados / ".env")["ACBRLIB_TOKEN"] == "primeiro"
    servico.configurar("segundo", CHAVE, "", forcar=True)
    assert servico.ler_env(dados / ".env")["ACBRLIB_TOKEN"] == "segundo"


@pytest.mark.parametrize("token,chave", [("t", "curta"), ("t", base64.b64encode(b"c" * 16).decode()),
                                         (CHAVE, CHAVE), ("com espaco", CHAVE)])
def test_recusa_valores_ruins_e_nao_grava(dados, token, chave):
    with pytest.raises(SystemExit):
        servico.configurar(token, chave, "")
    assert not (dados / ".env").exists()


def test_o_ini_da_lib_troca_os_caminhos_do_linux(dados, monkeypatch):
    servico.configurar("t", CHAVE, "")
    for variavel in ("ACBRLIB_TOKEN", "ACBR_E2E_KEY", "ACBR_ALLOWED_ORIGINS", "ACBR_SIMULADOR",
                     "ACBR_LIB_PATH", "ACBR_LIB_EMBUTIDA", "ACBR_SCHEMAS", "ACBR_CONFIG"):
        monkeypatch.setenv(variavel, "")
        monkeypatch.delenv(variavel)
    servico._preparar_ambiente()
    ini = (dados / "ACBrLib.ini").read_text(encoding="utf-8")
    assert "/app/" not in ini and str(dados) in ini
