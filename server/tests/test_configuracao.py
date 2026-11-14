"""A configuração guardada (desktop/painel), o token trocado pela API e as regras novas da API."""
import base64
import os

import pytest
from fastapi.testclient import TestClient

from tests.conftest import CHAVE_E2E, TOKEN
from tests.test_api import INI
from tests.test_certificados import CNPJ, SENHA, _pfx

A1 = {"pfx_base64": base64.b64encode(_pfx()).decode(), "senha": SENHA}
EMITENTE = {"cnpj": "11.222.333/0001-81", "uf": "RJ", "ambiente": "2", "modelo": "65",
            "certificado": A1, "csc": {"id": "1", "token": "CSC-SECRETO"}}


class MotorFalso:
    nome = "acbrlib"

    def __init__(self):
        self.pedido = None

    def status_servico(self, pedido):
        self.pedido = pedido
        return {"online": True}


@pytest.fixture
def motor_real(api, monkeypatch):
    import app.main

    falso = MotorFalso()
    monkeypatch.setattr(app.main, "motor", falso)
    return falso


def _gravar(api, **extra):
    resposta = api.post("/v1/config/emitente", json={**EMITENTE, **extra})
    assert resposta.status_code == 200, resposta.json()
    return resposta.json()


# ── o emitente guardado ───────────────────────────────────────────────────────
def test_emitente_guardado_dispensa_os_dados_na_chamada(api):
    _gravar(api, certificado=None)
    corpo = api.post("/v1/nfe/emitir", json={"ini": INI.format(tp=1)}).json()
    assert corpo["situacao"] == "autorizada"
    assert corpo["chave"][:2] == "33" and corpo["chave"][6:20] == CNPJ  # RJ e o CNPJ guardados


def test_certificado_e_csc_guardados_chegam_na_lib(api, motor_real):
    _gravar(api)
    assert api.post("/v1/status-servico", json={}).status_code == 200
    assert motor_real.pedido.certificado.pfx_base64 == A1["pfx_base64"]
    assert motor_real.pedido.csc.token == "CSC-SECRETO" and motor_real.pedido.uf == "RJ"


def test_o_que_vem_na_chamada_vale_sobre_o_guardado(api, motor_real):
    _gravar(api)
    outro = {"pfx_base64": base64.b64encode(_pfx()).decode(), "senha": SENHA}
    api.post("/v1/status-servico", json={"cnpj": CNPJ, "uf": "SP", "ambiente": "1", "certificado": outro})
    pedido = motor_real.pedido
    assert pedido.certificado.pfx_base64 == outro["pfx_base64"]
    assert pedido.uf == "SP" and pedido.ambiente == "1" and pedido.csc.token == "CSC-SECRETO"


def test_gravar_sem_certificado_mantem_o_anterior(api, motor_real):
    _gravar(api)
    _gravar(api, certificado=None, uf="SP")
    api.post("/v1/status-servico", json={})
    assert motor_real.pedido.certificado.pfx_base64 == A1["pfx_base64"] and motor_real.pedido.uf == "SP"


@pytest.mark.parametrize("certificado,motivo", [
    ({**A1, "senha": "errada"}, "senha_invalida"),
    ({"pfx_base64": base64.b64encode(_pfx(dias=-1)).decode(), "senha": SENHA}, "certificado_vencido"),
    ({"pfx_base64": base64.b64encode(_pfx(nome="OUTRA:99888777000166")).decode(), "senha": SENHA},
     "cnpj_diferente"),
])
def test_certificado_ruim_nao_e_gravado(api, certificado, motivo):
    resposta = api.post("/v1/config/emitente", json={**EMITENTE, "certificado": certificado})
    assert resposta.json()["erro"] == "configuracao" and resposta.json()["motivo"] == motivo
    assert api.post("/v1/config/ler", json={}).json()["emitentes"] == []


def test_ler_nao_devolve_segredo(api):
    _gravar(api)
    corpo = api.post("/v1/config/ler", json={}).json()
    texto = str(corpo)
    assert SENHA not in texto and "CSC-SECRETO" not in texto and A1["pfx_base64"][:40] not in texto
    emitente = corpo["emitentes"][0]
    assert emitente["cnpj"] == CNPJ and emitente["csc"] == {"id": "1", "configurado": True}
    assert emitente["certificado"]["cnpj"] == CNPJ and emitente["certificado"]["vencido"] is False


def test_no_disco_nada_fica_em_claro(api, tmp_path):
    _gravar(api)
    gravado = (tmp_path / "dados" / "configuracao.bin").read_bytes()
    for segredo in (SENHA.encode(), b"CSC-SECRETO", A1["pfx_base64"][:40].encode(), CNPJ.encode()):
        assert segredo not in gravado


def test_trocar_a_chave_e2e_deixa_a_configuracao_ilegivel(api, monkeypatch):
    _gravar(api)
    nova = base64.b64encode(b"n" * 32).decode()
    monkeypatch.setenv("ACBR_E2E_KEY", nova)
    api.chave = nova
    resposta = api.post("/v1/nfe/emitir", json={"ini": INI.format(tp=1)})
    assert resposta.json()["motivo"] == "configuracao_ilegivel"


def test_sem_emitente_nenhum_explica(api):
    resposta = api.post("/v1/nfe/emitir", json={"ini": INI.format(tp=1)})
    assert resposta.json()["erro"] == "configuracao" and resposta.json()["motivo"] == "emitente_nao_configurado"


def test_com_dois_emitentes_a_chamada_diz_qual(api):
    _gravar(api, certificado=None)
    _gravar(api, certificado=None, cnpj="11222333000262")
    resposta = api.post("/v1/nfe/emitir", json={"ini": INI.format(tp=1)})
    assert resposta.json()["motivo"] == "emitente_nao_informado"
    corpo = api.post("/v1/nfe/emitir", json={"cnpj": "11222333000262", "ini": INI.format(tp=1)}).json()
    assert corpo["chave"][6:20] == "11222333000262"


def test_remover_emitente(api):
    _gravar(api, certificado=None)
    assert api.post("/v1/config/emitente/remover", json={"cnpj": CNPJ}).json()["emitentes"] == []
    assert api.post("/v1/config/emitente/remover", json={"cnpj": CNPJ}).json()["motivo"] == \
        "emitente_nao_configurado"


def test_config_exige_token_e_cifra(api):
    assert TestClient.post(api, "/v1/config/ler", json={}).status_code == 400  # corpo em claro
    api.headers["Authorization"] = "Bearer errado"
    assert api.post("/v1/config/ler", json={}).status_code == 401


# ── o token ───────────────────────────────────────────────────────────────────
def test_trocar_o_token_derruba_o_anterior(api):
    novo = api.post("/v1/config/token", json={}).json()["token"]
    assert len(novo) >= 32
    assert api.post("/v1/config/ler", json={}).status_code == 401
    api.headers["Authorization"] = f"Bearer {novo}"
    assert api.post("/v1/config/ler", json={}).json()["token"] == "configurado"


def test_o_token_fica_so_como_hash(api, tmp_path):
    api.post("/v1/config/token", json={"token": "um-token-bem-comprido-123"})
    assert b"um-token-bem-comprido-123" not in (tmp_path / "dados" / "acesso.json").read_bytes()


def test_apagar_o_acesso_volta_ao_token_do_env(api, tmp_path):
    api.post("/v1/config/token", json={"token": "um-token-bem-comprido-123"})
    os.remove(tmp_path / "dados" / "acesso.json")
    api.headers["Authorization"] = f"Bearer {TOKEN}"
    assert api.post("/v1/config/ler", json={}).json()["token"] == "ambiente"


@pytest.mark.parametrize("token", ["curto", "com espaco no meio do token", "token#com#cerquilha#1", CHAVE_E2E])
def test_token_ruim_e_recusado(api, token):
    resposta = api.post("/v1/config/token", json={"token": token})
    assert resposta.status_code == 422
    assert api.post("/v1/config/ler", json={}).status_code == 200  # o anterior continua


# ── validação do contrato ─────────────────────────────────────────────────────
@pytest.mark.parametrize("rota,corpo", [
    ("/v1/nfe/emitir", {"uf": "SP", "cnpj": CNPJ, "ambiente": "3", "ini": "x"}),
    ("/v1/nfe/emitir", {"uf": "XX", "cnpj": CNPJ, "ini": "x"}),
    ("/v1/nfe/emitir", {"uf": "SP", "cnpj": CNPJ, "ini": "x", "tp_emis": "5"}),
    ("/v1/nfe/emitir", {"uf": "SP", "cnpj": CNPJ, "ini": "x", "fuso": "Brasilia"}),
    ("/v1/nfe/consultar", {"uf": "SP", "cnpj": CNPJ, "chave": "123"}),
    ("/v1/nfe/cancelar", {"uf": "SP", "cnpj": CNPJ, "chave": "3" * 44, "protocolo": "1", "justificativa": "curta"}),
])
def test_campos_fora_do_contrato_sao_recusados(api, rota, corpo):
    resposta = api.post(rota, json=corpo)
    assert resposta.status_code == 422 and resposta.json()["motivo"] == "campos_invalidos"


def test_ini_malformado_no_simulador_e_documento_invalido(api):
    resposta = api.post("/v1/nfe/emitir", json={"uf": "SP", "cnpj": CNPJ, "ini": "[Identificacao]\nnNF=1\n"})
    assert resposta.status_code == 422 and resposta.json()["motivo"] == "ini_invalido"


def test_corpo_grande_demais_e_recusado(api):
    resposta = TestClient.post(api, "/v1/nfe/emitir", content=b"x" * (8 * 1024 * 1024 + 1))
    assert resposta.status_code == 413


def test_falha_inesperada_vira_incerto_cifrado(api, monkeypatch):
    import app.main

    class Quebrado:
        nome = "simulador"

        def status_servico(self, _pedido):
            raise KeyError("algo")

    monkeypatch.setattr(app.main, "motor", Quebrado())
    resposta = api.post("/v1/status-servico", json={"uf": "SP", "cnpj": CNPJ})  # ClienteSelado abre a resposta
    assert resposta.status_code == 500
    assert resposta.json()["erro"] == "incerto" and resposta.json()["motivo"] == "falha_interna"


def test_preflight_de_rede_privada_e_liberado_para_a_origem_permitida(api):
    resposta = api.options("/v1/nfe/emitir", headers={
        "Origin": "https://caixa.exemplo.com.br", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Private-Network": "true"})
    assert resposta.headers.get("access-control-allow-private-network") == "true"


def test_health_continua_aberto_e_sem_segredo(api):
    _gravar(api)
    assert set(api.get("/health").json()) == {"ok", "motor", "lib", "simulador"}

