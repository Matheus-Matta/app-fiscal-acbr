"""O comunicador de ponta a ponta, com a SEFAZ simulada.

Cada teste é um caminho do plano de contingência visto DO comunicador: o que
ele responde e com qual `erro`, que é o que o cliente classifica.
"""
INI = """[Identificacao]
cNF=12345678
mod=65
serie=1
nNF=42
dhEmi=09/10/2026 10:00:00
tpEmis={tp}
"""
CONTEXTO = {"uf": "SP", "cnpj": "11222333000181", "ambiente": "2", "modelo": "65"}


def _emitir(api, tp="1"):
    return api.post("/v1/nfe/emitir", json={**CONTEXTO, "tp_emis": tp, "ini": INI.format(tp=tp)})


def test_sem_token_recusa(api):
    api.headers.pop("Authorization")
    assert api.post("/v1/nfe/emitir", json={**CONTEXTO, "ini": INI.format(tp=1)}).status_code == 401


def test_health_diz_que_e_simulador(api):
    assert api.get("/health").json() == {"ok": True, "modo": "nuvem", "motor": "simulador", "lib": False,
                                         "simulador": True}


def test_emite_e_autoriza_com_a_chave_do_ini(api):
    corpo = _emitir(api).json()
    assert corpo["situacao"] == "autorizada" and corpo["cstat"] == "100"
    chave = corpo["chave"]
    assert len(chave) == 44 and chave[:2] == "35" and chave[2:6] == "2610"
    assert chave[20:22] == "65" and chave[25:34] == "000000042" and chave[34] == "1"


def test_sefaz_fora_responde_sem_comunicacao_503(api, monkeypatch):
    monkeypatch.setenv("ACBR_SIMULAR_SEFAZ", "fora")
    resposta = _emitir(api)
    assert resposta.status_code == 503 and resposta.json()["erro"] == "sem_comunicacao"


def test_contingencia_so_assina_e_a_chave_leva_o_tpemis_9(api, monkeypatch):
    monkeypatch.setenv("ACBR_SIMULAR_SEFAZ", "fora")  # nem precisa da SEFAZ
    corpo = _emitir(api, tp="9").json()
    assert corpo["situacao"] == "contingencia" and corpo["chave"][34] == "9"
    assert corpo["xml"] and corpo["qrcode"]


def test_resposta_perdida_e_incerta_500_e_a_consulta_acha_autorizada(api, monkeypatch):
    monkeypatch.setenv("ACBR_SIMULAR_SEFAZ", "lenta")
    resposta = _emitir(api)
    assert resposta.status_code == 500 and resposta.json()["erro"] == "incerto"

    from app.simulador import chave_do_ini

    chave = chave_do_ini(INI.format(tp=1), "SP", CONTEXTO["cnpj"])
    consulta = api.post("/v1/nfe/consultar", json={**CONTEXTO, "chave": chave}).json()
    assert consulta["situacao"] == "autorizada"


def test_transmite_o_xml_assinado_em_contingencia(api, monkeypatch):
    assinado = _emitir(api, tp="9").json()
    corpo = api.post("/v1/nfe/transmitir", json={**CONTEXTO, "xml": assinado["xml"]}).json()
    assert corpo["situacao"] == "autorizada" and corpo["chave"] == assinado["chave"]


def test_cancela_a_autorizada(api):
    chave = _emitir(api).json()["chave"]
    corpo = api.post("/v1/nfe/cancelar", json={**CONTEXTO, "chave": chave, "protocolo": "1",
                                               "justificativa": "cliente desistiu da compra"}).json()
    assert corpo["situacao"] == "cancelada" and corpo["xml"]


FAIXA = {"ano": 26, "serie": 50, "numero_inicial": 7, "numero_final": 9, "justificativa": "numeros pulados por falha"}


def test_inutiliza_e_repetir_a_mesma_faixa_continua_inutilizada(api):
    for cstat in ("102", "563"):
        corpo = api.post("/v1/nfe/inutilizar", json={**CONTEXTO, **FAIXA}).json()
        assert (corpo["situacao"], corpo["cstat"]) == ("inutilizada", cstat)
        assert corpo["protocolo"] and corpo["xml"]


def test_numero_ja_usado_nao_se_inutiliza(api):
    _emitir(api)  # série 1, número 42
    corpo = api.post("/v1/nfe/inutilizar", json={**CONTEXTO, **FAIXA, "serie": 1, "numero_inicial": 40,
                                                 "numero_final": 45}).json()
    assert corpo["situacao"] == "rejeitada"


def test_resposta_perdida_da_inutilizacao_e_incerta_e_a_repeticao_confirma(api, monkeypatch):
    monkeypatch.setenv("ACBR_SIMULAR_SEFAZ", "lenta")
    assert api.post("/v1/nfe/inutilizar", json={**CONTEXTO, **FAIXA}).json()["erro"] == "incerto"
    assert api.post("/v1/nfe/inutilizar", json={**CONTEXTO, **FAIXA}).json()["situacao"] == "inutilizada"


def test_faixa_invertida_grande_ou_sem_motivo_e_recusada_sem_sair(api):
    for troca in ({"numero_final": 6}, {"numero_final": 1007}, {"justificativa": "curta"}, {"ano": 2026}, {"serie": 1000}):
        resposta = api.post("/v1/nfe/inutilizar", json={**CONTEXTO, **FAIXA, **troca})
        assert resposta.json()["erro"] == "documento_invalido", troca


def test_status_servico(api, monkeypatch):
    assert api.post("/v1/status-servico", json=CONTEXTO).json()["online"] is True
    monkeypatch.setenv("ACBR_SIMULAR_SEFAZ", "fora")
    assert api.post("/v1/status-servico", json=CONTEXTO).json()["online"] is False
