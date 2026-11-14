"""A ACBrLib instalada sozinha: baixa, confere o SHA-256 e o cabeçalho, e só então troca.

O mesmo desenho do instalador da loja: uma página de erro, um download pela metade ou
uma lib trocada viram aviso — nunca uma lib carregada pelo emissor que assina as notas.
"""
import hashlib
import http.server
import importlib
import io
import tarfile
import threading
import time
import zipfile

import pytest

from app import instalador
from tests.conftest import TOKEN, ClienteSelado

LIB = instalador._CABECALHO + b"conteudo da lib"
SHA = hashlib.sha256(LIB).hexdigest()


def _pacote(tmp_path, *, lib=LIB, nome=instalador.NOME_LIB, formato="tar", extra=None, schemas=True):
    """Como o pacote real: projeto-fiscal/acbr/libs/<lib> e libs/Schemas/NFe/*.xsd."""
    arquivos = {f"projeto-fiscal/acbr/libs/{nome}": lib, "projeto-fiscal/acbr/libs/dependencia.bin": b"dep",
                "projeto-fiscal/acbr/teste_lib.py": b"print()"}
    if schemas:
        arquivos["projeto-fiscal/acbr/libs/Schemas/NFe/nfe_v4.00.xsd"] = b"<xs/>"
        arquivos["projeto-fiscal/acbr/libs/Schemas/NFe/leiauteNFe_v4.00.xsd"] = b"<xs/>"
    arquivos.update(extra or {})
    caminho = tmp_path / ("pacote.zip" if formato == "zip" else "pacote.tar.gz")
    if formato == "zip":
        with zipfile.ZipFile(caminho, "w") as z:
            for nome_arquivo, dados in arquivos.items():
                z.writestr(nome_arquivo, dados)
    else:
        with tarfile.open(caminho, "w:gz") as t:
            for nome_arquivo, dados in arquivos.items():
                info = tarfile.TarInfo(nome_arquivo)
                info.size = len(dados)
                t.addfile(info, io.BytesIO(dados))
    return caminho


@pytest.fixture
def servidor(tmp_path):
    """Um HTTP local servindo tmp_path: o download de verdade, sem internet."""

    class Silencioso(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(tmp_path), **k)

        def log_message(self, *_):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Silencioso)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture
def destino(tmp_path):
    return tmp_path / "dados" / "lib"


# ── instalar ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("formato", ["tar", "zip"])
def test_instala_a_lib_as_dependencias_e_os_schemas(tmp_path, destino, formato):
    resultado = instalador.instalar(arquivo=_pacote(tmp_path, formato=formato), sha256=SHA, destino=destino)

    assert (destino / instalador.NOME_LIB).read_bytes() == LIB
    assert (destino / "dependencia.bin").exists()  # no Windows, as DLLs que a ACBrNFe64.dll usa
    assert sorted(p.name for p in (destino / "Schemas").iterdir()) == ["leiauteNFe_v4.00.xsd", "nfe_v4.00.xsd"]
    assert resultado["sha256"] == SHA and resultado["schemas"] == 2 and resultado["conferida"]
    assert instalador.instalada_confere(destino, SHA)


def test_baixa_pela_url(tmp_path, destino, servidor):
    _pacote(tmp_path)
    instalador.instalar(url=f"{servidor}/pacote.tar.gz", sha256=SHA, destino=destino)
    assert (destino / instalador.NOME_LIB).read_bytes() == LIB


def test_download_exige_o_sha(tmp_path, destino, servidor):
    _pacote(tmp_path)
    with pytest.raises(instalador.FalhaNaInstalacao, match="SHA-256"):
        instalador.instalar(url=f"{servidor}/pacote.tar.gz", destino=destino)
    assert not destino.exists()


def test_lib_que_nao_confere_nao_e_instalada_e_a_anterior_fica(tmp_path, destino):
    instalador.instalar(arquivo=_pacote(tmp_path), sha256=SHA, destino=destino)
    trocada = _pacote(tmp_path, lib=instalador._CABECALHO + b"outra lib")
    with pytest.raises(instalador.FalhaNaInstalacao, match="não confere"):
        instalador.instalar(arquivo=trocada, sha256=SHA, destino=destino)
    assert (destino / instalador.NOME_LIB).read_bytes() == LIB


def test_pagina_de_erro_no_lugar_do_pacote_e_recusada(tmp_path, destino, servidor):
    (tmp_path / "erro.html").write_text("<html>404</html>")
    with pytest.raises(instalador.FalhaNaInstalacao, match="não é um pacote"):
        instalador.instalar(url=f"{servidor}/erro.html", sha256=SHA, destino=destino)


def test_endereco_que_nao_responde_vira_aviso(destino):
    with pytest.raises(instalador.FalhaNaInstalacao, match="Não consegui baixar"):
        instalador.instalar(url="http://127.0.0.1:9/nada.tar.gz", sha256=SHA, destino=destino)


def test_arquivo_sem_cabecalho_de_biblioteca_e_recusado(tmp_path, destino):
    falsa = _pacote(tmp_path, lib=b"<html>nao sou uma lib</html>")
    with pytest.raises(instalador.FalhaNaInstalacao, match="não é uma biblioteca"):
        instalador.instalar(arquivo=falsa, destino=destino)


def test_pacote_da_outra_plataforma_explica(tmp_path, destino):
    outra = "libacbrnfe64.so" if instalador.WINDOWS else "ACBrNFe64.dll"
    with pytest.raises(instalador.FalhaNaInstalacao, match="pacote de"):
        instalador.instalar(arquivo=_pacote(tmp_path, nome=outra), destino=destino)


def test_pacote_sem_schemas_e_recusado(tmp_path, destino):
    with pytest.raises(instalador.FalhaNaInstalacao, match="Schemas"):
        instalador.instalar(arquivo=_pacote(tmp_path, schemas=False), destino=destino)


def test_zip_com_caminho_para_fora_da_pasta_e_recusado(tmp_path, destino):
    malicioso = _pacote(tmp_path, formato="zip", extra={"../../fora.txt": b"x"})
    with pytest.raises(instalador.FalhaNaInstalacao, match="fora da pasta"):
        instalador.instalar(arquivo=malicioso, destino=destino)
    assert not (tmp_path.parent / "fora.txt").exists()


def test_tar_com_caminho_para_fora_da_pasta_e_recusado(tmp_path, destino):
    malicioso = _pacote(tmp_path, extra={"../../fora.txt": b"x"})
    with pytest.raises(instalador.FalhaNaInstalacao):
        instalador.instalar(arquivo=malicioso, destino=destino)
    assert not (tmp_path.parent / "fora.txt").exists()


def test_reinstalar_troca_a_pasta_inteira(tmp_path, destino):
    instalador.instalar(arquivo=_pacote(tmp_path, extra={"projeto-fiscal/acbr/libs/velha.bin": b"v"}),
                        destino=destino)
    instalador.instalar(arquivo=_pacote(tmp_path), destino=destino)
    assert not (destino / "velha.bin").exists()
    assert not list(destino.parent.glob("lib.*"))  # nada de pasta temporária esquecida


def test_link_do_mediafire_e_lido_da_pagina(monkeypatch):
    pagina = b'<a href="https://download1326.mediafire.com/abc/pacote.tar.gz" id="downloadButton">'

    class Resposta(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    monkeypatch.setattr(instalador, "_abrir", lambda _url, timeout=60: Resposta(pagina))
    assert instalador._link_direto("https://www.mediafire.com/file/x/pacote.tar.gz/file") == \
        "https://download1326.mediafire.com/abc/pacote.tar.gz"


def test_cli_devolve_json(tmp_path, destino, capsys):
    assert instalador.main(["--arquivo", str(_pacote(tmp_path)), "--destino", str(destino)]) == 0
    assert '"ok": true' in capsys.readouterr().out
    assert instalador.main(["--url", "http://127.0.0.1:9/x", "--destino", str(destino)]) == 1


# ── o pacote configurado ─────────────────────────────────────────────────────
def test_sem_variavel_vale_o_pacote_de_referencia(monkeypatch):
    monkeypatch.delenv("ACBRLIB_PACOTE_URL")
    monkeypatch.delenv("ACBRLIB_SO_SHA256", raising=False)
    url, sha = instalador.pacote_configurado()
    assert (url, sha) == instalador.PACOTE_PADRAO["nt" if instalador.WINDOWS else "posix"]


def test_variavel_vazia_desliga_a_instalacao_automatica(monkeypatch):
    monkeypatch.setenv("ACBRLIB_PACOTE_URL", "")
    assert instalador.precisa_instalar() is None


def test_ja_instalada_e_conferida_nao_baixa_de_novo(tmp_path, destino, monkeypatch):
    instalador.instalar(arquivo=_pacote(tmp_path), destino=destino)
    monkeypatch.setenv("ACBR_LIB_INSTALADA", str(destino))
    monkeypatch.setenv("ACBRLIB_PACOTE_URL", "http://exemplo/pacote.tar.gz")
    monkeypatch.setenv("ACBRLIB_SO_SHA256", SHA)
    assert instalador.precisa_instalar() is None
    monkeypatch.setenv("ACBRLIB_SO_SHA256", "0" * 64)  # outra versão configurada
    assert instalador.precisa_instalar() == ("http://exemplo/pacote.tar.gz", "0" * 64)


# ── no comunicador ───────────────────────────────────────────────────────────
class LibFalsa:
    nome = "acbrlib"

    def __init__(self, caminho, _config, schemas=None):
        self.caminho, self.schemas = caminho, schemas


@pytest.fixture
def sem_lib(ambiente, monkeypatch, tmp_path, destino):
    monkeypatch.delenv("ACBR_SIMULADOR", raising=False)
    monkeypatch.setenv("ACBR_LIB_PATH", str(tmp_path / "nao-montada" / instalador.NOME_LIB))
    monkeypatch.setenv("ACBR_LIB_EMBUTIDA", str(tmp_path / "nao-embutida" / instalador.NOME_LIB))
    monkeypatch.setenv("ACBR_LIB_INSTALADA", str(destino))
    monkeypatch.setattr("app.acbrlib.AcbrLib", LibFalsa)
    return monkeypatch


def _cliente():
    import app.main

    modulo = importlib.reload(app.main)
    cliente = ClienteSelado(modulo.app)
    cliente.headers["Authorization"] = f"Bearer {TOKEN}"
    return modulo, cliente


def test_instalada_que_nao_e_a_configurada_nao_e_carregada(tmp_path, destino, sem_lib):
    instalador.instalar(arquivo=_pacote(tmp_path), destino=destino)
    sem_lib.setenv("ACBRLIB_SO_SHA256", "0" * 64)
    from app import motor

    assert motor.criar_motor().nome == "ausente"
    sem_lib.setenv("ACBRLIB_SO_SHA256", SHA)
    escolhido = motor.criar_motor()
    assert escolhido.nome == "acbrlib" and escolhido.schemas == str(destino / "Schemas")


def test_sobe_instala_sozinho_e_passa_a_emitir_sem_reiniciar(tmp_path, servidor, sem_lib):
    _pacote(tmp_path)
    sem_lib.setenv("ACBRLIB_PACOTE_URL", f"{servidor}/pacote.tar.gz")
    sem_lib.setenv("ACBRLIB_SO_SHA256", SHA)
    modulo, cliente = _cliente()
    for _ in range(100):
        if modulo.motor.nome == "acbrlib":
            break
        time.sleep(0.05)
    assert cliente.get("/health").json()["lib"] is True
    assert cliente.post("/v1/config/ler", json={}).json()["lib"]["situacao"] == "instalada"


def test_instalacao_que_falha_fica_no_health_e_o_comunicador_segue(sem_lib):
    sem_lib.setenv("ACBRLIB_PACOTE_URL", "http://127.0.0.1:9/pacote.tar.gz")
    sem_lib.setenv("ACBRLIB_SO_SHA256", SHA)
    modulo, cliente = _cliente()
    for _ in range(100):
        if modulo._instalacao["situacao"] == "falhou":
            break
        time.sleep(0.05)
    corpo = cliente.get("/health").json()
    assert corpo["ok"] is False and "instalação automática falhou" in corpo["mensagem"]


def test_instalar_pela_api(tmp_path, servidor, sem_lib):
    _pacote(tmp_path)
    modulo, cliente = _cliente()
    assert modulo.motor.nome == "ausente"
    resposta = cliente.post("/v1/config/lib", json={"url": f"{servidor}/pacote.tar.gz", "sha256": SHA})
    assert resposta.status_code == 200 and resposta.json()["motor"] == "acbrlib"
    # Carregada, não se troca com o comunicador no ar.
    assert cliente.post("/v1/config/lib", json={}).json()["motivo"] == "lib_ja_carregada"


def test_instalar_pela_api_com_sha_errado_explica(tmp_path, servidor, sem_lib):
    _pacote(tmp_path)
    _modulo, cliente = _cliente()
    resposta = cliente.post("/v1/config/lib", json={"url": f"{servidor}/pacote.tar.gz", "sha256": "1" * 64})
    assert resposta.json()["motivo"] == "instalacao_falhou" and "não confere" in resposta.json()["mensagem"]


def test_pasta_que_nao_se_renomeia_e_trocada_mesmo_assim(tmp_path, destino, monkeypatch):
    """No `docker build` (overlayfs), a pasta de uma camada anterior devolve EXDEV ao
    ser renomeada: a troca apaga a velha e põe a nova, em vez de dizer "em uso"."""
    import errno
    import pathlib

    instalador.instalar(arquivo=_pacote(tmp_path, extra={"projeto-fiscal/acbr/libs/velha.bin": b"v"}),
                        destino=destino)
    renomear = pathlib.Path.rename

    def exdev(self, alvo):
        if self == destino:
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return renomear(self, alvo)

    monkeypatch.setattr(pathlib.Path, "rename", exdev)
    instalador.instalar(arquivo=_pacote(tmp_path), destino=destino)
    assert (destino / instalador.NOME_LIB).read_bytes() == LIB and not (destino / "velha.bin").exists()
