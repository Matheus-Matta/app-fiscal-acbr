"""Modo nuvem: só por API, com o emitente em toda chamada, nada guardado, e as defesas extras."""
import base64
import hashlib
import importlib
import json
import threading

import pytest

from app import modo
from tests.conftest import TOKEN, ClienteSelado
from tests.test_api import CONTEXTO, INI
from tests.test_certificados import _com_a1


def _cliente(ip="203.0.113.10"):
    import app.main

    cliente = ClienteSelado(app.main.app, client=(ip, 50000))
    cliente.headers["Authorization"] = f"Bearer {TOKEN}"
    return cliente


# ── nada é guardado ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("rota", ["/v1/config/emitente", "/v1/config/emitente/remover", "/v1/config/token"])
def test_rotas_de_gravar_emitente_e_token_nao_existem(api, rota):
    assert api.post(rota, json={}).status_code == 404


def test_sem_emitente_na_chamada_explica(api):
    resposta = api.post("/v1/nfe/emitir", json={"ini": INI.format(tp=1)})
    assert resposta.status_code == 500
    assert resposta.json()["erro"] == "configuracao" and resposta.json()["motivo"] == "dados_do_emitente_ausentes"


@pytest.mark.parametrize("campo", ["ambiente", "modelo"])
def test_ambiente_e_modelo_nao_tem_padrao_na_nuvem(api, campo):
    """Sem isto, quem esquecesse o ambiente emitiria em homologação achando que era produção."""
    corpo = {k: v for k, v in CONTEXTO.items() if k != campo}
    resposta = api.post("/v1/nfe/emitir", json={**corpo, "ini": INI.format(tp=1)})
    assert resposta.json()["motivo"] == "dados_do_emitente_ausentes" and campo in resposta.json()["mensagem"]


def test_emitente_completo_na_chamada_emite_e_devolve_o_xml(api):
    corpo = api.post("/v1/nfe/emitir", json={**CONTEXTO, "ini": INI.format(tp=1)}).json()
    assert corpo["situacao"] == "autorizada" and corpo["xml"]


def test_ler_mostra_so_a_lib_sem_emitentes(api):
    corpo = api.post("/v1/config/ler", json={}).json()
    assert corpo["modo"] == "nuvem" and "emitentes" not in corpo and "token" not in corpo


def test_nada_fica_na_pasta_de_dados(api, tmp_path):
    api.post("/v1/nfe/emitir", json={**_com_a1(), "ini": INI.format(tp=1)})
    dados = tmp_path / "dados"
    assert not dados.exists() or list(dados.rglob("*")) == []


def test_token_trocado_no_disco_nao_vale_na_nuvem(api, tmp_path):
    """Na nuvem vale só o token do .env: um acesso.json deixado no volume não abre a porta."""
    (tmp_path / "dados").mkdir(parents=True, exist_ok=True)
    outro = "outro-token-que-alguem-gravou-no-volume"
    (tmp_path / "dados" / "acesso.json").write_text(json.dumps({"sha256": hashlib.sha256(outro.encode()).hexdigest()}))
    assert api.post("/v1/status-servico", json=CONTEXTO).status_code == 200
    api.headers["Authorization"] = f"Bearer {outro}"
    assert api.post("/v1/status-servico", json=CONTEXTO).status_code == 401


# ── não sobe mal configurado ─────────────────────────────────────────────────
@pytest.mark.parametrize("variavel,valor", [
    ("ACBRLIB_TOKEN", "curto-demais"),
    ("ACBRLIB_TOKEN", ""),
    ("ACBRLIB_TOKEN", "token com espaco e comprido o bastante"),
    ("ACBR_E2E_KEY", ""),
    ("ACBR_E2E_KEY", base64.b64encode(b"k" * 16).decode()),
    ("ACBR_MODO", "hibrido"),
])
def test_nao_sobe_mal_configurado(ambiente, monkeypatch, variavel, valor):
    monkeypatch.setenv("ACBR_SIMULADOR", "1")
    monkeypatch.setenv(variavel, valor)
    import app.main

    with pytest.raises(modo.ConfiguracaoInvalida):
        importlib.reload(app.main)


def test_nao_sobe_com_a_chave_igual_ao_token(ambiente, monkeypatch):
    chave = base64.b64encode(b"t" * 32).decode()  # 44 caracteres: passaria como token forte
    monkeypatch.setenv("ACBRLIB_TOKEN", chave)
    monkeypatch.setenv("ACBR_E2E_KEY", chave)
    import app.main

    with pytest.raises(modo.ConfiguracaoInvalida):
        importlib.reload(app.main)


def test_sem_modo_no_ambiente_vale_a_nuvem(ambiente, monkeypatch):
    monkeypatch.delenv("ACBR_MODO")
    assert modo.atual() == "nuvem"


# ── bloqueio por tentativas ──────────────────────────────────────────────────
def test_quem_erra_o_token_demais_fica_bloqueado(api, monkeypatch):
    monkeypatch.setenv("ACBR_TENTATIVAS", "3")
    monkeypatch.setenv("ACBR_BLOQUEIO_SEGUNDOS", "600")
    import app.main

    importlib.reload(app.main)
    atacante, loja = _cliente("203.0.113.66"), _cliente("198.51.100.7")
    atacante.headers["Authorization"] = "Bearer chutado"
    assert [atacante.post("/v1/status-servico", json=CONTEXTO).status_code for _ in range(3)] == [401] * 3
    # Bloqueado: nem o token certo passa, e a resposta diz quando tentar de novo.
    atacante.headers["Authorization"] = f"Bearer {TOKEN}"
    resposta = atacante.post("/v1/status-servico", json=CONTEXTO)
    assert resposta.status_code == 429 and 0 < int(resposta.headers["retry-after"]) <= 600
    # Os outros IPs seguem normais.
    assert loja.post("/v1/status-servico", json=CONTEXTO).status_code == 200


def test_acertar_zera_a_contagem():
    bloqueio = modo.Bloqueio(tentativas=3, segundos=60)
    bloqueio.errou("1.2.3.4", agora=0)
    bloqueio.errou("1.2.3.4", agora=1)
    bloqueio.acertou("1.2.3.4")
    bloqueio.errou("1.2.3.4", agora=2)
    assert bloqueio.restante("1.2.3.4", agora=3) == 0


def test_o_bloqueio_acaba_sozinho():
    bloqueio = modo.Bloqueio(tentativas=2, segundos=60)
    bloqueio.errou("1.2.3.4", agora=0)
    bloqueio.errou("1.2.3.4", agora=1)
    assert bloqueio.restante("1.2.3.4", agora=30) > 0
    assert bloqueio.restante("1.2.3.4", agora=62) == 0


@pytest.mark.parametrize("variavel,valor", [("ACBR_TENTATIVAS", "dez"), ("ACBR_TENTATIVAS", "0"),
                                            ("ACBR_BLOQUEIO_SEGUNDOS", "-5")])
def test_bloqueio_mal_configurado_nao_sobe(ambiente, monkeypatch, variavel, valor):
    monkeypatch.setenv(variavel, valor)
    import app.main

    with pytest.raises(modo.ConfiguracaoInvalida):
        importlib.reload(app.main)


def test_ipv6_conta_pela_rede_64_e_nao_escapa_trocando_de_endereco():
    bloqueio = modo.Bloqueio(tentativas=3, segundos=60)
    for final in ("1", "2", "3"):
        bloqueio.errou(f"2001:db8:1:2::{final}", agora=0)
    assert bloqueio.restante("2001:db8:1:2:ffff::9", agora=1) > 0  # mesma /64
    assert bloqueio.restante("2001:db8:1:3::1", agora=1) == 0  # outra /64


def test_ipv4_escrito_como_ipv6_conta_como_ipv4():
    bloqueio = modo.Bloqueio(tentativas=2, segundos=60)
    bloqueio.errou("::ffff:203.0.113.5", agora=0)
    bloqueio.errou("203.0.113.5", agora=0)
    assert bloqueio.restante("203.0.113.5", agora=1) > 0


def test_ipv6_com_zona_nao_estoura():
    assert modo.quem_conta("fe80::1%eth0") == "fe80::/64"
    assert modo.quem_conta("") == "" and modo.quem_conta("testclient") == "testclient"


def test_a_memoria_nao_e_varrida_a_cada_erro(monkeypatch):
    bloqueio = modo.Bloqueio(tentativas=100, segundos=900)
    varreduras = []
    original = bloqueio._limpar
    monkeypatch.setattr(bloqueio, "_limpar", lambda agora: (varreduras.append(agora), original(agora)))
    for numero in range(1000):
        bloqueio.errou(f"10.1.{numero // 250}.{numero % 250}", agora=numero / 100)  # 1000 erros em 10 s
    assert len(varreduras) == 1000  # chamada sempre...
    assert bloqueio._limpo_em == 0  # ...mas só varre de fato a cada LIMPEZA_SEGUNDOS


def test_registra_o_bloqueio_uma_vez_e_nao_cada_chute(api, monkeypatch, caplog):
    monkeypatch.setenv("ACBR_TENTATIVAS", "3")
    import app.main

    importlib.reload(app.main)
    atacante = _cliente("203.0.113.77")
    atacante.headers["Authorization"] = "Bearer chutado"
    with caplog.at_level("WARNING", logger="acbr"):
        for _ in range(8):
            atacante.post("/v1/status-servico", json=CONTEXTO)
    avisos = [r.getMessage() for r in caplog.records if "bloqueado" in r.getMessage()]
    assert len(avisos) == 1 and "203.0.113.77" in avisos[0]


def test_bloqueios_vencidos_saem_da_memoria():
    bloqueio = modo.Bloqueio(tentativas=1, segundos=60)
    for numero in range(50):
        bloqueio.errou(f"10.0.0.{numero}", agora=0)
    bloqueio.errou("10.0.1.1", agora=100)
    assert set(bloqueio._bloqueados) == {"10.0.1.1"}


def test_erros_espalhados_alem_da_janela_nao_bloqueiam():
    bloqueio = modo.Bloqueio(tentativas=3, segundos=60)
    for agora in (0, 100, 200, 300):
        bloqueio.errou("1.2.3.4", agora=agora)
    assert bloqueio.restante("1.2.3.4", agora=301) == 0


# ── a lib não guarda XML nem segredo ─────────────────────────────────────────
class LibQueAnota:
    def __init__(self):
        self.gravados = []

    def NFE_Inicializar(self, *_args):
        return 0

    def NFE_ConfigGravarValor(self, _handle, secao, chave, valor):
        self.gravados.append((secao.decode(), chave.decode(), valor.decode()))
        return 0


def _lib(monkeypatch, falsa):
    import ctypes

    from app import acbrlib

    monkeypatch.setattr(ctypes, "CDLL", lambda _caminho: falsa)
    return acbrlib.AcbrLib("lib-falsa", "config.ini")


@pytest.mark.parametrize("modo_atual", ["nuvem", "local"])
def test_a_lib_nao_grava_o_xml_em_modo_nenhum(monkeypatch, modo_atual):
    monkeypatch.setenv("ACBR_MODO", modo_atual)
    falsa = LibQueAnota()
    _lib(monkeypatch, falsa)
    assert ("NFe", "SalvarGer", "0") in falsa.gravados


def test_o_ini_base_nao_grava_o_xml():
    from pathlib import Path

    ini = (Path(__file__).resolve().parent.parent / "config" / "ACBrLib.ini").read_text(encoding="utf-8")
    assert "SalvarGer=0" in ini and "SalvarGer=1" not in ini


def test_a_lib_esquece_certificado_e_csc_ao_fim_de_cada_chamada(monkeypatch):
    falsa = LibQueAnota()
    motor = _lib(monkeypatch, falsa)
    with pytest.raises(RuntimeError), motor._vez():
        motor.lib.NFE_ConfigGravarValor(None, b"DFe", b"DadosPFX", b"PFX-SECRETO")
        raise RuntimeError("a nota falhou no meio")
    finais = {(s, c): v for s, c, v in falsa.gravados}
    assert finais[("DFe", "DadosPFX")] == "" and finais[("DFe", "Senha")] == ""
    assert finais[("NFe", "CSC")] == "" and finais[("NFe", "IdCSC")] == ""
    assert not motor.trava.locked()


def test_a_trava_e_liberada_mesmo_se_esquecer_falhar(monkeypatch):
    falsa = LibQueAnota()
    motor = _lib(monkeypatch, falsa)

    def quebra(*_args):
        raise OSError("lib fora")

    falsa.NFE_ConfigGravarValor = quebra
    with motor._vez():
        pass
    assert isinstance(motor.trava, type(threading.Lock())) and not motor.trava.locked()
