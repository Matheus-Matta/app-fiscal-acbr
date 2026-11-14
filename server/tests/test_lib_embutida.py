"""A lib embutida na imagem vale quando ninguém montou outra.

Com a libacbrnfe64.so em embutida/ no build, ela vai DENTRO da imagem, em
/opt/acbr: quem instala não copia o arquivo à mão. A montada em /app/libs
continua tendo precedência — é como se testa uma versão nova da lib sem
esperar uma imagem nova.
"""
import pytest

from app import motor


class LibFalsa:
    def __init__(self, caminho, _config, schemas=None):
        self.caminho = caminho
        self.schemas = schemas
        self.nome = "acbrlib"


@pytest.fixture
def caminhos(monkeypatch, tmp_path):
    monkeypatch.delenv("ACBR_SIMULADOR", raising=False)
    montada, embutida = tmp_path / "montada.so", tmp_path / "embutida.so"
    monkeypatch.setenv("ACBR_LIB_PATH", str(montada))
    monkeypatch.setenv("ACBR_LIB_EMBUTIDA", str(embutida))
    # Instalação completa: a lib e a pasta dos Schemas da NF-e.
    (tmp_path / "schemas-ok").mkdir()
    monkeypatch.setenv("ACBR_SCHEMAS", str(tmp_path / "schemas-ok"))
    monkeypatch.setattr("app.acbrlib.AcbrLib", LibFalsa)
    return montada, embutida


def test_sem_lib_montada_usa_a_embutida_na_imagem(caminhos):
    _montada, embutida = caminhos
    embutida.write_bytes(b"so")

    assert motor.criar_motor().caminho == str(embutida)


def test_a_montada_pela_loja_tem_precedencia(caminhos):
    montada, embutida = caminhos
    montada.write_bytes(b"so")
    embutida.write_bytes(b"so")

    assert motor.criar_motor().caminho == str(montada)


def test_sem_nenhuma_continua_recusando_com_a_providencia(caminhos):
    assert motor.criar_motor().nome == "ausente"


def test_lib_que_nao_carrega_nao_derruba_o_comunicador(caminhos, monkeypatch):
    """Arquivo corrompido ou de outra arquitetura: o `ctypes` levanta OSError
    no carregamento. Sem tratar, o container caía no boot e reiniciava em laço."""
    _montada, embutida = caminhos
    embutida.write_bytes(b"isto nao e uma .so")

    def falha(_caminho, _config, **_extra):
        raise OSError("invalid ELF header")

    monkeypatch.setattr("app.acbrlib.AcbrLib", falha)

    escolhido = motor.criar_motor()

    assert escolhido.nome == "ausente"
    assert "invalid ELF header" in escolhido.mensagem


def test_lib_sem_os_schemas_avisa_antes_de_emitir(caminhos, monkeypatch, tmp_path):
    """A ACBrLib valida o XML contra os Schemas da NF-e antes de enviar. Sem a
    pasta, TODA nota falhava na validação com uma mensagem técnica; agora o
    comunicador diz o que falta e onde pôr, antes de tentar."""
    montada, _ = caminhos
    montada.write_bytes(b"so")
    monkeypatch.setenv("ACBR_SCHEMAS", str(tmp_path / "Schemas"))

    escolhido = motor.criar_motor()

    assert escolhido.nome == "ausente"
    assert "Schemas" in escolhido.mensagem


def test_lib_com_os_schemas_carrega(caminhos, monkeypatch, tmp_path):
    montada, _ = caminhos
    montada.write_bytes(b"so")
    (tmp_path / "Schemas").mkdir()
    monkeypatch.setenv("ACBR_SCHEMAS", str(tmp_path / "Schemas"))

    assert motor.criar_motor().nome == "acbrlib"


def test_a_embutida_usa_os_schemas_que_estao_ao_lado_dela(caminhos, monkeypatch, tmp_path):
    """Antes os Schemas eram procurados só em /app/libs: a lib embutida sem nada
    montado subia dizendo "faltam os Schemas", com eles dentro da imagem."""
    _montada, embutida = caminhos
    monkeypatch.delenv("ACBR_SCHEMAS")
    embutida.write_bytes(b"so")
    (tmp_path / "Schemas").mkdir()

    escolhida = motor.criar_motor()
    assert escolhida.caminho == str(embutida) and escolhida.schemas == str(tmp_path / "Schemas")
