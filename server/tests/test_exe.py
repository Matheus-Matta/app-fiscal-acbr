"""A iniciação do .exe grava o .env do modo local, e nunca troca token nem chave em silêncio."""
import base64
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from windows import servico  # noqa: E402

CHAVE = base64.b64encode(b"c" * 32).decode()


@pytest.fixture
def dados(tmp_path, monkeypatch):
    monkeypatch.setenv("ACBR_DATA_DIR", str(tmp_path / "AcbrFiscal"))
    # A permissão real é conferida no .exe; aqui ela prenderia a limpeza do tmp_path.
    monkeypatch.setattr(servico, "_restringir", lambda _pasta: None)
    return tmp_path / "AcbrFiscal"


def test_enter_gera_token_e_chave_do_cofre(dados):
    servico.configurar(entrada=lambda _pergunta: "")
    valores = servico.ler_env(dados / ".env")
    assert valores["ACBR_MODO"] == "local"
    assert len(valores["ACBRLIB_TOKEN"]) >= 32
    assert len(base64.b64decode(valores["ACBR_CHAVE_COFRE"])) == 32
    assert "ACBR_E2E_KEY" not in valores
    assert valores["ACBR_SIMULADOR"] == "0" and valores["ACBR_ALLOWED_ORIGINS"] == ""


def test_grava_o_que_foi_digitado(dados):
    servico.configurar("meu-token-de-acesso", "http://127.0.0.1:8030")
    valores = servico.ler_env(dados / ".env")
    assert valores["ACBRLIB_TOKEN"] == "meu-token-de-acesso"
    assert valores["ACBR_ALLOWED_ORIGINS"] == "http://127.0.0.1:8030"


def test_nao_troca_o_que_ja_esta_configurado_sem_pedir(dados):
    servico.configurar("primeiro-token-local", "")
    chave = servico.ler_env(dados / ".env")["ACBR_CHAVE_COFRE"]
    with pytest.raises(SystemExit):
        servico.configurar("segundo-token-local", "")
    assert servico.ler_env(dados / ".env")["ACBRLIB_TOKEN"] == "primeiro-token-local"
    servico.configurar("segundo-token-local", "", forcar=True)
    valores = servico.ler_env(dados / ".env")
    # O token muda; a chave do cofre não, senão os emitentes guardados ficariam ilegíveis.
    assert valores["ACBRLIB_TOKEN"] == "segundo-token-local" and valores["ACBR_CHAVE_COFRE"] == chave


def test_instalacao_antiga_vira_local_e_mantem_a_chave(dados):
    dados.mkdir(parents=True)
    (dados / ".env").write_text(f"ACBRLIB_TOKEN=antigo-token-local\nACBR_E2E_KEY={CHAVE}\n", encoding="utf-8")
    servico.configurar("novo-token-local-1", "", forcar=True)
    valores = servico.ler_env(dados / ".env")
    assert valores["ACBR_CHAVE_COFRE"] == CHAVE and "ACBR_E2E_KEY" not in valores


def test_forcar_mantem_o_resto_do_env(dados, monkeypatch):
    dados.mkdir(parents=True)
    (dados / ".env").write_text(f"ACBRLIB_TOKEN=antigo-token-local\nACBR_CHAVE_COFRE={CHAVE}\n"
                                "ACBRLIB_PACOTE_URL=https://pacote\nACBR_PORT=8123\n", encoding="utf-8")
    monkeypatch.setenv("ACBR_CHAVE_COFRE", "a-do-ambiente-fica")
    servico.configurar("novo-token-local-1", "", forcar=True)
    valores = servico.ler_env(dados / ".env")
    assert valores["ACBRLIB_PACOTE_URL"] == "https://pacote" and valores["ACBR_PORT"] == "8123"
    assert valores["ACBRLIB_TOKEN"] == "novo-token-local-1" and valores["ACBR_CHAVE_COFRE"] == CHAVE
    import os

    assert os.environ["ACBR_CHAVE_COFRE"] == "a-do-ambiente-fica"  # configurar não mexe no ambiente


@pytest.mark.parametrize("token",["curto", "com espaco no meio", "token#com#cerquilha", "tokên-com-acento-123"])
def test_recusa_token_ruim_e_nao_grava(dados, token):
    with pytest.raises(SystemExit):
        servico.configurar(token, "")
    assert not (dados / ".env").exists()


def test_o_ini_da_lib_troca_os_caminhos_do_linux(dados, monkeypatch):
    servico.configurar("token-do-teste-local", "")
    for variavel in ("ACBRLIB_TOKEN", "ACBR_CHAVE_COFRE", "ACBR_MODO", "ACBR_ALLOWED_ORIGINS", "ACBR_SIMULADOR",
                     "ACBR_LIB_PATH", "ACBR_LIB_EMBUTIDA", "ACBR_SCHEMAS", "ACBR_CONFIG"):
        monkeypatch.setenv(variavel, "")
        monkeypatch.delenv(variavel)
    servico._preparar_ambiente()
    ini = (dados / "ACBrLib.ini").read_text(encoding="utf-8")
    assert "/app/" not in ini and str(dados) in ini


def test_pasta_lib_vazia_nao_esconde_a_dll_que_vem_no_exe(dados, monkeypatch, tmp_path):
    """O botão "Abrir pasta" cria dados\\lib vazia: a DLL ao lado do .exe tem de continuar valendo."""
    programa = tmp_path / "programa"
    (programa / "lib").mkdir(parents=True)
    (programa / "lib" / servico.NOME_LIB).write_bytes(b"lib")
    monkeypatch.setattr(servico, "pasta_programa", lambda: programa)
    servico.configurar("token-do-teste-local", "")
    (dados / "lib").mkdir()
    for variavel in ("ACBRLIB_TOKEN", "ACBR_CHAVE_COFRE", "ACBR_MODO", "ACBR_ALLOWED_ORIGINS", "ACBR_SIMULADOR",
                     "ACBR_LIB_PATH", "ACBR_LIB_EMBUTIDA", "ACBR_CONFIG"):
        monkeypatch.setenv(variavel, "")
        monkeypatch.delenv(variavel)
    monkeypatch.setattr(servico.sys, "_MEIPASS", str(Path(__file__).resolve().parent.parent), raising=False)
    servico._preparar_ambiente()
    import os

    assert os.environ["ACBR_LIB_PATH"] == str(programa / "lib" / servico.NOME_LIB)


def test_env_salvo_com_bom_le_a_primeira_variavel(dados):
    dados.mkdir(parents=True)
    (dados / ".env").write_text("ACBR_MODO=local\nACBRLIB_TOKEN=x\n", encoding="utf-8-sig")
    assert servico.ler_env(dados / ".env")["ACBR_MODO"] == "local"


def test_env_antigo_sem_modo_sobe_local(dados, monkeypatch):
    dados.mkdir(parents=True)
    (dados / ".env").write_text(f"ACBRLIB_TOKEN=antigo\nACBR_E2E_KEY={CHAVE}\n", encoding="utf-8")
    for variavel in ("ACBRLIB_TOKEN", "ACBR_E2E_KEY", "ACBR_MODO", "ACBR_LIB_PATH", "ACBR_LIB_EMBUTIDA",
                     "ACBR_CONFIG"):
        monkeypatch.setenv(variavel, "")
        monkeypatch.delenv(variavel)
    servico._preparar_ambiente()
    import os

    assert os.environ["ACBR_MODO"] == "local"


# ── Linux: o desktop AppImage ────────────────────────────────────────────────
so_linux = pytest.mark.skipif(servico.WINDOWS, reason="só no Linux (atalho simbólico, LD_LIBRARY_PATH)")


def _sistema(tmp_path, *nomes):
    pasta = tmp_path / "usr-lib"
    pasta.mkdir()
    for nome in nomes:
        (pasta / nome).write_bytes(b"\x7fELF")
    return pasta


def test_acha_a_libxml2_so2_antes_das_outras(tmp_path):
    pasta = _sistema(tmp_path, "libxml2.so.16", "libxml2.so.2", "libxml2.so.2.9.14")
    assert servico.achar_libxml2([str(pasta)]) == pasta / "libxml2.so.2"
    assert servico.achar_libxml2([str(tmp_path / "nao-existe")]) is None


@so_linux
def test_cria_o_atalho_libxml2_so_e_pede_para_reabrir(tmp_path, monkeypatch):
    pasta = _sistema(tmp_path, "libxml2.so.2")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/outra")
    assert servico.garantir_libxml2(tmp_path / "dados", [str(pasta)]) is True
    atalho = tmp_path / "dados" / "compat" / "libxml2.so"
    assert atalho.is_symlink() and atalho.resolve() == (pasta / "libxml2.so.2").resolve()
    import os

    assert os.environ["LD_LIBRARY_PATH"] == f"{tmp_path / 'dados' / 'compat'}:/opt/outra"
    # Já reaberto com o caminho certo: não pede de novo (sem laço de execv).
    assert servico.garantir_libxml2(tmp_path / "dados", [str(pasta)]) is False


@so_linux
def test_sem_libxml2_avisa_e_segue(tmp_path, capsys):
    assert servico.garantir_libxml2(tmp_path / "dados", [str(tmp_path / "vazia")]) is False
    assert "libxml2" in capsys.readouterr().err


@so_linux
def test_pasta_de_dados_do_linux(monkeypatch, tmp_path):
    monkeypatch.delenv("ACBR_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert servico.pasta_dados() == tmp_path / "AcbrFiscal"


def test_no_windows_nao_mexe_na_libxml2(monkeypatch, tmp_path):
    monkeypatch.setattr(servico, "WINDOWS", True)
    assert servico.garantir_libxml2(tmp_path, [str(tmp_path)]) is False
    assert not (tmp_path / "compat").exists()
