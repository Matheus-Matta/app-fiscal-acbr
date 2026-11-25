"""O cStat vira a situação certa, e a falha da lib vira a família certa."""
import pytest

from app import sefaz
from app.acbrlib import _classificar, _do_xml


@pytest.mark.parametrize(("cstat", "situacao"), [
    ("100", "autorizada"), ("150", "autorizada"), ("110", "denegada"), ("217", "nao_encontrada"),
    ("103", "processando"), ("135", "cancelada"), ("778", "rejeitada"),
])
def test_cstat_vira_situacao(cstat, situacao):
    assert sefaz.situacao(cstat) == situacao


def test_servico_paralisado_e_indisponibilidade_nao_recusa():
    with pytest.raises(sefaz.FalhaDeComunicacao):
        sefaz.situacao("108")


@pytest.mark.parametrize(("mensagem", "classe"), [
    ("Erro ao carregar o certificado PFX", sefaz.FalhaDeConfiguracao),
    ("Falha na validação do Schema", sefaz.DocumentoInvalido),
    ("Read timed out", sefaz.FalhaIncerta),
    ("Socket Error # 10061 Connection refused", sefaz.FalhaDeComunicacao),
    ("algo que ninguém previu", sefaz.FalhaIncerta),
])
def test_falha_da_lib_vira_a_familia_certa(mensagem, classe):
    assert isinstance(_classificar(mensagem), classe)


@pytest.mark.parametrize(("mensagem", "motivo"), [
    ("Senha do certificado inválida", "senha_invalida"),
    ("Certificado vencido em 01/01/2026", "certificado_vencido"),
    ("Erro ao carregar o certificado PFX", "certificado_invalido"),
    ("Socket Error # 10061 Connection refused", "sefaz_sem_comunicacao"),
    ("Falha na validação do Schema", ""),
])
def test_a_falha_diz_o_motivo_pelo_nome(mensagem, motivo):
    """O cliente mostra ao operador a providência certa, não a frase da lib."""
    assert _classificar(mensagem).motivo == motivo


def test_sem_a_lib_o_motivo_e_acbrlib_ausente():
    from app.motor import SemLib

    with pytest.raises(sefaz.FalhaDeConfiguracao) as erro:
        SemLib("/app/libs/libacbrnfe64.so").emitir(None)
    assert erro.value.motivo == "acbrlib_ausente"


def test_le_chave_qr_e_digest_do_xml_assinado():
    xml = ('<NFe><infNFe Id="NFe' + "3" * 44 + '"/><DigestValue>abc=</DigestValue>'
           "<infNFeSupl><qrCode><![CDATA[https://qr?p=1]]></qrCode></infNFeSupl></NFe>")
    assert _do_xml(xml) == {"chave": "3" * 44, "qrcode": "https://qr?p=1", "digest_value": "abc="}


# ── a lib durante o envio, a trava e o buffer ────────────────────────────────
@pytest.mark.parametrize(("mensagem", "classe"), [
    # Caiu no meio: a SEFAZ pode ter recebido. Nunca "seguro reenviar".
    ("Erro HTTP: 500 Internal Server Error", sefaz.FalhaIncerta),
    ("Socket Error # 10054 Connection reset by peer", sefaz.FalhaIncerta),
    # Nem saiu: seguro.
    ("Socket Error # 10061 Connection refused", sefaz.FalhaDeComunicacao),
    ("Socket Error # 11001 Host not found", sefaz.FalhaDeComunicacao),
])
def test_durante_o_envio_so_e_sem_comunicacao_o_que_nao_saiu(mensagem, classe):
    assert isinstance(_classificar(mensagem, enviando=True), classe)


def test_fora_do_envio_falha_de_rede_continua_sem_comunicacao():
    assert isinstance(_classificar("Erro HTTP: 500"), sefaz.FalhaDeComunicacao)


#: Mensagem real da ACBrLib (NCM com um dígito), com o "http" do namespace no meio.
ERRO_DE_SCHEMA = ("Falha na validação dos dados da nota: 8\r\n\r\n --> 1839 - Element "
                  "'{http://www.portalfiscal.inf.br/nfe}NCM': [facet 'pattern'] The value '1' is not accepted "
                  "by the pattern '[0-9]{2}|[0-9]{8}'.\n")


@pytest.mark.parametrize("enviando", [False, True])
@pytest.mark.parametrize("mensagem", [
    ERRO_DE_SCHEMA,
    ERRO_DE_SCHEMA.replace("ç", "�").replace("ã", "�"),  # a lib nem sempre responde em UTF-8
    "Falha na validação dos dados da nota: 8",
    "Element '{http://www.portalfiscal.inf.br/nfe}xProd': [facet 'maxLength'] The value 'Senha do certificado'",
])
def test_erro_de_schema_e_do_documento_e_nunca_falta_de_rede(mensagem, enviando):
    assert isinstance(_classificar(mensagem, enviando=enviando), sefaz.DocumentoInvalido)


class LibQueFalha:
    """Tudo dá certo, menos a etapa `falha`, que deixa `mensagem` no último retorno."""

    def __init__(self, falha, mensagem):
        self.falha, self.mensagem, self.chamadas = falha, mensagem, []

    def __getattr__(self, nome):
        def chamada(*_args):
            self.chamadas.append(nome)
            return -10 if nome == self.falha else 0
        return chamada

    def NFE_UltimoRetorno(self, _handle, buffer, tamanho):
        buffer.value = self.mensagem.encode()
        tamanho._obj.value = len(buffer.value)
        return 0


def _pedido(**campos):
    from types import SimpleNamespace as N

    return N(uf="RJ", ambiente="2", modelo="65", fuso="-03:00", cnpj="11222333000181", ini="[infNFe]", xml="<NFe/>",
             certificado=N(pfx_base64="", senha=""), csc=N(id="1", token=""), **{"tp_emis": "1", **campos})


@pytest.mark.parametrize("etapa", ["NFE_CarregarINI", "NFE_Assinar", "NFE_Validar"])
@pytest.mark.parametrize("mensagem", [
    ERRO_DE_SCHEMA, "XmlNode não pode ser nulo.", "Erro HTTP qualquer", "timeout", "algo que ninguém previu",
])
def test_antes_do_envio_a_falha_nunca_e_de_rede_nem_incerta(etapa, mensagem):
    lib = LibQueFalha(etapa, mensagem)
    with pytest.raises(sefaz.DocumentoInvalido):
        _motor_com(lib).emitir(_pedido())
    assert "NFE_Enviar" not in lib.chamadas


def test_certificado_que_falha_ao_assinar_continua_configuracao():
    with pytest.raises(sefaz.FalhaDeConfiguracao) as erro:
        _motor_com(LibQueFalha("NFE_Assinar", "Certificado vencido em 01/01/2026")).emitir(_pedido())
    assert erro.value.motivo == "certificado_vencido"


def test_xml_de_contingencia_ilegivel_e_do_documento():
    with pytest.raises(sefaz.DocumentoInvalido):
        _motor_com(LibQueFalha("NFE_CarregarXML", "Erro ao ler http://x")).transmitir(_pedido())


def test_no_envio_a_classificacao_por_texto_continua_valendo():
    with pytest.raises(sefaz.FalhaIncerta):
        _motor_com(LibQueFalha("NFE_Enviar", "Socket Error # 10054 Connection reset by peer")).emitir(_pedido())


@pytest.mark.parametrize("nt", [True, False])
def test_no_windows_a_pasta_da_lib_vem_primeiro_no_path(monkeypatch, tmp_path, nt):
    """Sem isto a DLL não acha a libxml2 ao lado dela e nenhuma nota é assinada."""
    import os
    from types import SimpleNamespace

    from app import acbrlib

    ambiente = {"PATH": os.pathsep.join(["outra", str(tmp_path), "mais"])}
    monkeypatch.setattr(acbrlib, "os", SimpleNamespace(name="nt" if nt else "posix", path=os.path, pathsep=os.pathsep,
                                                       environ=ambiente))
    for _ in range(2):  # repetir não acumula
        acbrlib._achar_dlls_vizinhas(str(tmp_path / "ACBrNFe64.dll"))
    esperado = [str(tmp_path), "outra", "mais"] if nt else ["outra", str(tmp_path), "mais"]
    assert ambiente["PATH"].split(os.pathsep) == esperado


class LibDeResposta:
    """Responde `dados` como a ACBrLib: diz o tamanho e só copia o que cabe."""

    def __init__(self, dados):
        self.dados = dados

    def _copiar(self, buffer, tamanho):
        capacidade = tamanho._obj.value
        tamanho._obj.value = len(self.dados)
        if len(self.dados) <= capacidade:
            buffer.value = self.dados

    def NFE_StatusServico(self, _handle, buffer, tamanho):
        self._copiar(buffer, tamanho)
        return 0

    def NFE_UltimoRetorno(self, _handle, buffer, tamanho):
        self._copiar(buffer, tamanho)
        return 0


def _motor_com(lib):
    import threading

    from app.acbrlib import AcbrLib

    motor = AcbrLib.__new__(AcbrLib)
    motor.lib, motor.handle, motor.trava = lib, None, threading.Lock()
    return motor


def test_resposta_maior_que_o_buffer_volta_inteira():
    from app.acbrlib import TAMANHO

    grande = b"[Status]\nxMotivo=" + b"x" * (TAMANHO * 2) + b"\n"
    motor = _motor_com(LibDeResposta(grande))
    assert motor._texto(motor.lib.NFE_StatusServico).encode() == grande


def test_com_a_trava_ocupada_responde_sem_comunicacao_sem_enviar(monkeypatch):
    import app.acbrlib

    monkeypatch.setattr(app.acbrlib, "ESPERA_TRAVA", 0.01)
    motor = _motor_com(LibDeResposta(b""))
    motor.trava.acquire()
    with pytest.raises(sefaz.FalhaDeComunicacao) as erro:
        with motor._vez():
            pass
    assert erro.value.motivo == "comunicador_ocupado"


# ── inutilização e o XML do evento ───────────────────────────────────────────
class LibQueResponde:
    """A última chamada fica em `args`; a resposta é o INI `texto`."""

    def __init__(self, texto):
        self.texto, self.args = texto, None

    def __getattr__(self, _nome):
        def chamada(*args):
            if len(args) > 6 or _nome == "NFE_Cancelar":
                self.args, buffer, tamanho = args, args[-2], args[-1]
                buffer.value = self.texto.encode()
                tamanho._obj.value = len(buffer.value)
            return 0
        return chamada


def _inutilizacao(**campos):
    return _pedido(ano=26, serie=50, numero_inicial=7, numero_final=9, justificativa="numeros pulados por falha", **campos)


def test_inutilizar_passa_os_parametros_na_ordem_da_lib():
    lib = LibQueResponde("[Inutilizacao]\nCStat=102\nXMotivo=Homologada\nNProt=135\nXml=<a b=\"c\"/>")
    corpo = _motor_com(lib).inutilizar(_inutilizacao())
    cnpj, motivo, *numeros = lib.args[1:-2]
    assert (cnpj, motivo) == (b"11222333000181", b"numeros pulados por falha")
    assert [n.value for n in numeros] == [26, 65, 50, 7, 9]  # ano, modelo, série, inicial, final
    assert (corpo["situacao"], corpo["protocolo"], corpo["xml"]) == ("inutilizada", "135", '<a b="c"/>')


@pytest.mark.parametrize(("cstat", "situacao"), [("102", "inutilizada"), ("563", "inutilizada"), ("206", "inutilizada"),
                                                 ("241", "rejeitada"), ("256", "rejeitada"), ("999", "rejeitada")])
def test_cstat_da_inutilizacao(cstat, situacao):
    assert sefaz.situacao_da_inutilizacao(cstat) == situacao


def test_inutilizacao_paralisada_ou_sem_resposta_nunca_vira_recusa():
    with pytest.raises(sefaz.FalhaDeComunicacao):
        sefaz.situacao_da_inutilizacao("108")
    with pytest.raises(sefaz.FalhaIncerta):
        _motor_com(LibQueResponde("[Inutilizacao]\nXMotivo=")).inutilizar(_inutilizacao())


@pytest.mark.parametrize(("xml", "esperado"), [("<procEventoNFe/>", "<procEventoNFe/>"), ("", ""), ("C:/caminho.xml", "")])
def test_cancelamento_devolve_o_xml_do_evento(xml, esperado):
    lib = LibQueResponde(f"[CANCELAMENTO]\nCStat=135\nNProt=9\nXML={xml}")
    corpo = _motor_com(lib).cancelar(_pedido(chave="3" * 44, justificativa="cliente desistiu da compra"))
    assert (corpo["situacao"], corpo["xml"]) == ("cancelada", esperado)
