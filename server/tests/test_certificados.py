"""O A1 que chega em cada chamada, a cifra de ponta a ponta, o token e as origens."""
import base64
import datetime
import importlib
import json

import pytest
from cryptography import x509
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization.pkcs12 import serialize_key_and_certificates
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from app import sigilo
from tests.conftest import CHAVE_E2E, TOKEN, _texto

CNPJ = "11222333000181"
SENHA = "senha-do-a1"
CONTEXTO = {"uf": "SP", "cnpj": CNPJ, "ambiente": "2", "modelo": "65"}
INI = "[Identificacao]\ncNF=12345678\nmod=65\nserie=1\nnNF=42\ndhEmi=09/10/2026 10:00:00\ntpEmis=1\n"
ROTAS = ["/v1/status-servico", "/v1/nfe/emitir", "/v1/nfe/transmitir", "/v1/nfe/consultar", "/v1/nfe/cancelar"]


def _pfx(*, nome=f"EMPRESA TESTE LTDA:{CNPJ}", dias=365, senha=SENHA):
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sujeito = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, nome)])
    agora = datetime.datetime.now(datetime.UTC)
    cert = (x509.CertificateBuilder().subject_name(sujeito).issuer_name(sujeito)
            .public_key(chave.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(agora - datetime.timedelta(days=400))
            .not_valid_after(agora + datetime.timedelta(days=dias))
            .sign(chave, hashes.SHA256()))
    return serialize_key_and_certificates(
        b"a1", chave, cert, None, serialization.BestAvailableEncryption(senha.encode()))


def _com_a1(pfx=None, senha=SENHA, **extra):
    return {**CONTEXTO, **extra, "certificado": {
        "pfx_base64": base64.b64encode(pfx or _pfx()).decode(), "senha": senha}}


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


def _bruto(api, corpo, caminho="/v1/status-servico", **kwargs):
    """Sela e devolve o envelope, para os testes que mexem nele antes de enviar."""
    return sigilo.selar_pedido(_texto(corpo), "POST", caminho, CHAVE_E2E, **kwargs)


def _envio(api, envelope, caminho="/v1/status-servico"):
    return TestClient.post(api, caminho, json=envelope)


# ── o certificado na chamada ──────────────────────────────────────────────────
def test_certificado_da_chamada_chega_na_lib(api, motor_real):
    pfx = _pfx()
    assert api.post("/v1/status-servico", json=_com_a1(pfx)).status_code == 200
    assert base64.b64decode(motor_real.pedido.certificado.pfx_base64) == pfx
    assert motor_real.pedido.certificado.senha == SENHA


def test_filial_usa_o_certificado_da_matriz(api, motor_real):
    assert api.post("/v1/status-servico", json=_com_a1(cnpj="11222333000262")).status_code == 200


def test_nada_e_gravado_em_disco(api, motor_real, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    api.post("/v1/status-servico", json=_com_a1())
    assert list(tmp_path.rglob("*")) == []


def test_sem_certificado_a_lib_nao_e_chamada(api, motor_real):
    resposta = api.post("/v1/status-servico", json=CONTEXTO)
    assert resposta.status_code == 500 and resposta.json()["motivo"] == "certificado_ausente"
    assert motor_real.pedido is None


@pytest.mark.parametrize("corpo,motivo", [
    (lambda: _com_a1(senha="errada"), "senha_invalida"),
    (lambda: _com_a1(b"nao sou um pfx"), "senha_invalida"),
    (lambda: _com_a1(_pfx(dias=-1)), "certificado_vencido"),
    (lambda: _com_a1(cnpj="99888777000166"), "cnpj_diferente"),
    (lambda: _com_a1(b"0" * 300_000), "certificado_invalido"),
    (lambda: {**CONTEXTO, "certificado": {"pfx_base64": "@@nao base64@@", "senha": SENHA}}, "certificado_invalido"),
])
def test_certificado_ruim_e_configuracao_e_nao_chega_na_lib(api, motor_real, corpo, motivo):
    resposta = api.post("/v1/status-servico", json=corpo())
    assert resposta.status_code == 500  # `configuracao`: nunca vira contingência
    assert resposta.json()["erro"] == "configuracao" and resposta.json()["motivo"] == motivo
    assert motor_real.pedido is None


def test_aceita_cnpj_alfanumerico(api, motor_real):
    corpo = _com_a1(_pfx(nome="EMPRESA NOVA:12ABC34501DE35"), cnpj="12ABC34501DE35")
    assert api.post("/v1/status-servico", json=corpo).status_code == 200


# ── a cifra ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("rota", ROTAS)
def test_toda_operacao_recusa_corpo_em_claro(api, rota):
    resposta = TestClient.post(api, rota, json={**_com_a1(), "ini": INI})
    assert resposta.status_code == 400 and resposta.json()["motivo"] == "envelope_invalido"


def test_o_que_trafega_nao_tem_certificado_senha_csc_nem_dados_fiscais(api):
    pfx = _pfx()
    corpo = {**_com_a1(pfx), "ini": INI, "csc": {"id": "1", "token": "CSC-SECRETO"}}
    envelope, nonce = _bruto(api, corpo, "/v1/nfe/emitir")
    pedido = json.dumps(envelope).encode()
    a_vista = (SENHA.encode(), b"CSC-SECRETO", base64.b64encode(pfx)[:40], CNPJ.encode(), b"Identificacao")
    assert not [s for s in a_vista if s in pedido]

    resposta = _envio(api, envelope, "/v1/nfe/emitir")
    assert set(resposta.json()) == {"v", "nonce", "dados"}
    assert b"autorizada" not in resposta.content and CNPJ.encode() not in resposta.content
    claro = sigilo.abrir_resposta(resposta.json(), resposta.status_code, nonce, CHAVE_E2E)
    assert json.loads(claro)["situacao"] == "autorizada"


def test_erro_fiscal_tambem_volta_cifrado(api, monkeypatch):
    monkeypatch.setenv("ACBR_SIMULAR_SEFAZ", "fora")
    envelope, nonce = _bruto(api, {**CONTEXTO, "ini": INI}, "/v1/nfe/emitir")
    resposta = _envio(api, envelope, "/v1/nfe/emitir")
    assert resposta.status_code == 503 and b"sem_comunicacao" not in resposta.content
    claro = sigilo.abrir_resposta(resposta.json(), 503, nonce, CHAVE_E2E)
    assert json.loads(claro)["erro"] == "sem_comunicacao"


def test_campo_faltando_nao_ecoa_o_certificado(api):
    resposta = api.post("/v1/nfe/emitir", json=_com_a1())  # sem `ini`
    assert resposta.status_code == 422 and resposta.json()["motivo"] == "campos_invalidos"
    assert "ini" in resposta.json()["mensagem"]
    assert SENHA not in resposta.text and "pfx_base64" not in resposta.text


def test_chave_errada_nao_abre(api):
    outra = base64.b64encode(b"z" * 32).decode()
    envelope, _ = sigilo.selar_pedido(_texto(CONTEXTO), "POST", "/v1/status-servico", outra)
    resposta = _envio(api, envelope)
    assert resposta.status_code == 400 and resposta.json()["motivo"] == "nao_decifrou"


def test_alterar_um_byte_e_recusado(api):
    envelope, _ = _bruto(api, CONTEXTO)
    bruto = bytearray(base64.b64decode(envelope["dados"]))
    bruto[0] ^= 1
    resposta = _envio(api, {**envelope, "dados": base64.b64encode(bytes(bruto)).decode()})
    assert resposta.json()["motivo"] == "nao_decifrou"


def test_pedido_de_outra_rota_nao_serve(api):
    envelope, _ = _bruto(api, {**CONTEXTO, "chave": "1", "protocolo": "1", "justificativa": "x"})
    assert _envio(api, envelope, "/v1/nfe/cancelar").json()["motivo"] == "nao_decifrou"


def test_repetir_a_chamada_capturada_e_recusado(api):
    envelope, _ = _bruto(api, CONTEXTO)
    assert _envio(api, envelope).status_code == 200
    repetida = _envio(api, envelope)
    assert repetida.status_code == 409 and repetida.json()["motivo"] == "repetida"


@pytest.mark.parametrize("deslocamento", [-310, 310])  # margem: o int() do ts corta até 1 s
def test_fora_da_janela_e_recusado(api, deslocamento):
    import time

    envelope, _ = _bruto(api, CONTEXTO, ts=int(time.time()) + deslocamento)
    assert _envio(api, envelope).json()["motivo"] == "fora_da_janela"


def test_ts_trocado_no_caminho_e_recusado(api):
    envelope, _ = _bruto(api, CONTEXTO)
    assert _envio(api, {**envelope, "ts": envelope["ts"] + 1}).json()["motivo"] == "nao_decifrou"


def test_resposta_com_status_trocado_nao_abre(api):
    envelope, nonce = _bruto(api, CONTEXTO)
    resposta = _envio(api, envelope)
    with pytest.raises(InvalidTag):
        sigilo.abrir_resposta(resposta.json(), 503, nonce, CHAVE_E2E)


def test_pedido_nao_serve_como_resposta(api):
    envelope, nonce = _bruto(api, CONTEXTO)
    with pytest.raises(InvalidTag):
        sigilo.abrir_resposta(envelope, 200, nonce, CHAVE_E2E)


@pytest.mark.parametrize("lixo", [b"", b"{", b"[]", b'{"v":1}', b'{"v":2,"ts":1,"nonce":"AAAA","dados":"AAAA"}',
                                  b'{"v":1,"ts":"1","nonce":"AAAAAAAAAAAAAAAA","dados":"AAAA"}',
                                  b'{"v":1,"ts":1,"nonce":7,"dados":"AAAA"}', b"[" * 100_000],
                         ids=lambda lixo: f"{len(lixo)}-bytes")
def test_envelope_quebrado_e_recusado_sem_estourar(api, lixo):
    resposta = TestClient.post(api, "/v1/status-servico", content=lixo)
    assert resposta.status_code == 400 and resposta.json()["motivo"] == "envelope_invalido"


@pytest.mark.parametrize("chave", ["", "curta", base64.b64encode(b"k" * 16).decode()])
def test_sem_chave_valida_nada_entra(api, monkeypatch, chave):
    envelope, _ = _bruto(api, CONTEXTO)
    monkeypatch.setenv("ACBR_E2E_KEY", chave)
    resposta = _envio(api, envelope)
    assert resposta.status_code == 500 and resposta.json()["motivo"] == "e2e_sem_chave"


def test_chave_igual_ao_token_e_recusada(api, monkeypatch):
    envelope, _ = _bruto(api, CONTEXTO)
    monkeypatch.setenv("ACBRLIB_TOKEN", CHAVE_E2E)
    api.headers["Authorization"] = f"Bearer {CHAVE_E2E}"
    assert _envio(api, envelope).json()["motivo"] == "e2e_sem_chave"


# ── token e origens ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("rota", ROTAS)
def test_operacoes_exigem_token_antes_de_abrir_o_envelope(api, rota):
    api.headers["Authorization"] = "Bearer errado"
    assert TestClient.post(api, rota, content=b"lixo").status_code == 401


def test_sem_token_configurado_recusa_tudo(api, monkeypatch):
    monkeypatch.setenv("ACBRLIB_TOKEN", "")
    api.headers["Authorization"] = "Bearer "
    assert api.post("/v1/status-servico", json=CONTEXTO).status_code == 401


def test_token_com_acento_recusa_sem_estourar(api):
    resposta = TestClient.post(api, "/v1/status-servico", content=b"x",
                               headers={"Authorization": "Bearer inválido".encode()})
    assert resposta.status_code == 401


def test_origem_fora_da_lista_e_recusada_mesmo_com_token(api):
    resposta = api.post("/v1/status-servico", json=CONTEXTO, headers={"Origin": "https://intruso.exemplo.com"})
    assert resposta.status_code == 403


def test_origem_permitida_recebe_cors(api):
    resposta = api.post("/v1/status-servico", json=CONTEXTO, headers={"Origin": "https://caixa.exemplo.com.br"})
    assert resposta.status_code == 200
    assert resposta.headers["access-control-allow-origin"] == "https://caixa.exemplo.com.br"


def test_preflight_da_origem_permitida_passa_e_o_de_fora_nao(api):
    pedido = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization"}
    assert api.options("/v1/nfe/emitir", headers={**pedido, "Origin": "https://caixa.exemplo.com.br"}).status_code == 200
    assert api.options("/v1/nfe/emitir", headers={**pedido, "Origin": "https://intruso.exemplo.com"}).status_code == 403


def test_sem_origem_configurada_navegador_nao_entra(monkeypatch, api):
    monkeypatch.setenv("ACBR_ALLOWED_ORIGINS", "")
    import app.main

    cliente = TestClient(importlib.reload(app.main).app)
    assert cliente.get("/health", headers={"Origin": "https://caixa.exemplo.com.br"}).status_code == 403
    assert cliente.get("/health").status_code == 200


def test_rotas_do_cofre_e_documentacao_nao_existem(api):
    for rota in ("/painel", "/docs", "/redoc", "/openapi.json"):
        assert api.get(rota).status_code == 404
    assert api.get("/v1/certificados", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 404
