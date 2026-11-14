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
    """O backend mostra ao operador a providência certa, não a frase da lib."""
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
