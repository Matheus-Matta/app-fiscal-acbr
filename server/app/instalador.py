"""Instala a ACBrLib sozinho: baixa o pacote, confere e põe a lib e os Schemas no lugar.

O mesmo desenho do instalador da loja do StarChef, aqui dentro do comunicador para
valer em qualquer lugar (Docker, serviço Windows, desktop):

- O pacote (`.tar.gz` ou `.zip`) vem de `ACBRLIB_PACOTE_URL`. Link do MediaFire é
  aceito: o direto muda a cada visita e é lido da página do arquivo.
- A lib é conferida pelo SHA-256 (`ACBRLIB_SO_SHA256`) e pelo cabeçalho (ELF no
  Linux, MZ no Windows) ANTES de ir para o lugar: uma página de erro, um download
  pela metade ou uma lib trocada viram aviso — nunca uma lib carregada pelo
  emissor que assina as notas da empresa.
- Vai para a pasta de dados (`<ACBR_DATA_DIR>/lib`), inteira ou nada: a pasta nova
  só substitui a antiga depois de pronta.
- Nunca derruba o comunicador: sem a lib ele sobe igual e diz o que falta.

Sem `ACBRLIB_PACOTE_URL` no ambiente vale o pacote de referência abaixo (só há o de
Linux); com a variável vazia, a instalação automática fica desligada.

    python -m app.instalador [--url URL --sha256 HASH | --arquivo PACOTE] [--destino PASTA]
"""
import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

log = logging.getLogger("acbr.instalador")

WINDOWS = os.name == "nt"
NOME_LIB = "ACBrNFe64.dll" if WINDOWS else "libacbrnfe64.so"
_CABECALHO = b"MZ" if WINDOWS else b"\x7fELF"
#: ACBrLibNFe 1.5.0.488 (SVN trunk2 r48608, Linux-x86_64-MT, glibc 2.34+).
PACOTE_PADRAO = {
    "posix": ("https://www.mediafire.com/file/hd3t2w7uqc2r6b3/acbr-fiscal-linux-x64.tar.gz/file",
              "deec61a921b830516ad3d7f5833aee7cb69603391eb497e649296ecc5522b3f0"),
    "nt": ("", ""),
}
TAMANHO_MAXIMO = 300 * 1024 * 1024
AGENTE = "Mozilla/5.0"
_MEDIAFIRE = re.compile(r"https://download\d*\.mediafire\.com/[^\"' <>]+")


class FalhaNaInstalacao(Exception):
    """Não instalou. A mensagem diz por quê e o que fazer; nada foi trocado."""


def pacote_configurado():
    """(url, sha256) do ambiente, ou o de referência desta plataforma."""
    url_padrao, sha_padrao = PACOTE_PADRAO["nt" if WINDOWS else "posix"]
    url = os.environ.get("ACBRLIB_PACOTE_URL")
    if url is None:
        return url_padrao, os.environ.get("ACBRLIB_SO_SHA256") or sha_padrao
    return url.strip(), (os.environ.get("ACBRLIB_SO_SHA256") or "").strip().lower()


def pasta_instalada():
    if os.environ.get("ACBR_LIB_INSTALADA"):
        return Path(os.environ["ACBR_LIB_INSTALADA"])
    return Path(os.environ.get("ACBR_DATA_DIR") or "/app/data") / "lib"


def sha256_de(caminho):
    resumo = hashlib.sha256()
    with open(caminho, "rb") as entrada:
        for bloco in iter(lambda: entrada.read(1 << 20), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def instalada_confere(pasta, sha256=""):
    """A lib e os Schemas estão na pasta e, havendo SHA esperado, é aquela lib."""
    lib = Path(pasta) / NOME_LIB
    if not lib.is_file() or not (Path(pasta) / "Schemas").is_dir():
        return False
    return not sha256 or sha256_de(lib) == sha256.lower()


# ── download e extração ──────────────────────────────────────────────────────
def _abrir(url, timeout=60):
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise FalhaNaInstalacao(f"Endereço do pacote inválido: {url}")
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": AGENTE}), timeout=timeout)


def _link_direto(url):
    if "mediafire.com/file/" not in url:
        return url
    with _abrir(url) as resposta:
        pagina = resposta.read(2 * 1024 * 1024).decode("utf-8", "replace")
    achado = _MEDIAFIRE.search(pagina)
    if not achado:
        raise FalhaNaInstalacao("O link de download não foi encontrado na página do MediaFire.")
    return achado.group(0)


def _baixar(url, destino):
    try:
        with _abrir(_link_direto(url), timeout=120) as resposta, open(destino, "wb") as saida:
            total = 0
            while bloco := resposta.read(1 << 20):
                total += len(bloco)
                if total > TAMANHO_MAXIMO:
                    raise FalhaNaInstalacao("O pacote baixado é grande demais.")
                saida.write(bloco)
    except FalhaNaInstalacao:
        raise
    except OSError as erro:  # URLError, HTTPError, timeout
        raise FalhaNaInstalacao(f"Não consegui baixar o pacote ({erro}).") from None


def _extrair(pacote, pasta):
    """Abre .zip ou .tar(.gz) sem deixar nenhum arquivo escapar da pasta."""
    raiz = Path(pasta).resolve()
    try:
        if zipfile.is_zipfile(pacote):
            with zipfile.ZipFile(pacote) as arquivo:
                for nome in arquivo.namelist():
                    if not (raiz / nome).resolve().is_relative_to(raiz):
                        raise FalhaNaInstalacao("O pacote tem caminhos fora da pasta: recusado.")
                arquivo.extractall(raiz)
        else:
            with tarfile.open(pacote) as arquivo:
                arquivo.extractall(raiz, filter="data")
    except (tarfile.TarError, zipfile.BadZipFile, OSError) as erro:
        raise FalhaNaInstalacao(f"O arquivo não é um pacote .zip nem .tar.gz válido ({erro}).") from None


def _achar_lib(pasta):
    for caminho in Path(pasta).rglob("*"):
        if caminho.is_file() and caminho.name.lower() == NOME_LIB.lower():
            return caminho
    raise FalhaNaInstalacao(f"O pacote não tem a {NOME_LIB}"
                            + (" (é o pacote de Linux?)." if WINDOWS else " (é o pacote de Windows?)."))


def _achar_schemas(lib):
    candidatos = [lib.parent / "Schemas" / "NFe", lib.parent / "Schemas"]
    candidatos += sorted(p for p in lib.parent.rglob("NFe") if p.is_dir())
    for pasta in candidatos:
        if pasta.is_dir() and any(pasta.glob("*.xsd")):
            return pasta
    raise FalhaNaInstalacao("O pacote não tem os Schemas da NF-e (a pasta Schemas/NFe, com os .xsd).")


def _trocar(nova, destino):
    """A pasta nova no lugar da antiga, sem deixar o destino pela metade."""
    em_uso = f"A lib em {destino} está em uso: feche o comunicador e tente de novo."
    antiga = destino.with_name(destino.name + ".antiga")
    shutil.rmtree(antiga, ignore_errors=True)
    if destino.exists():
        try:
            destino.rename(antiga)
        except PermissionError:  # Windows: a DLL carregada prende a pasta
            raise FalhaNaInstalacao(em_uso) from None
        except OSError:
            # Overlayfs (docker build): pasta de uma camada anterior não se renomeia
            # (EXDEV). A nova já está pronta ao lado: apaga a velha e põe a nova.
            try:
                shutil.rmtree(destino)
            except OSError:
                raise FalhaNaInstalacao(em_uso) from None
    try:
        nova.rename(destino)
    except OSError:
        shutil.move(str(nova), str(destino))
    shutil.rmtree(antiga, ignore_errors=True)


def instalar(*, url=None, arquivo=None, sha256=None, destino=None):
    """Instala a partir de `url` (exige `sha256`) ou de um `arquivo` local. Devolve o resumo."""
    if url is None and arquivo is None:
        url, sha_configurado = pacote_configurado()
        sha256 = sha256 or sha_configurado
    sha256 = (sha256 or "").strip().lower()
    if url and not sha256:
        raise FalhaNaInstalacao("Informe o SHA-256 da lib (ACBRLIB_SO_SHA256): sem ele o download não é conferido.")
    if not url and not arquivo:
        raise FalhaNaInstalacao("Nenhum pacote configurado (ACBRLIB_PACOTE_URL).")
    if sha256 and not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise FalhaNaInstalacao("O SHA-256 precisa ter 64 caracteres hexadecimais.")

    destino = Path(destino) if destino else pasta_instalada()
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="acbrlib-") as temporaria:
        pacote = Path(temporaria) / "pacote"
        if arquivo:
            if not Path(arquivo).is_file():
                raise FalhaNaInstalacao(f"Arquivo não encontrado: {arquivo}")
            shutil.copyfile(arquivo, pacote)
        else:
            log.info("baixando a ACBrLib de %s", urllib.parse.urlsplit(url).netloc)
            _baixar(url, pacote)
        extraida = Path(temporaria) / "x"
        _extrair(pacote, extraida)
        lib = _achar_lib(extraida)
        with open(lib, "rb") as entrada:
            if entrada.read(len(_CABECALHO)) != _CABECALHO:
                raise FalhaNaInstalacao(f"A {NOME_LIB} do pacote não é uma biblioteca de verdade.")
        obtido = sha256_de(lib)
        if sha256 and obtido != sha256:
            raise FalhaNaInstalacao(f"A lib baixada não confere com o SHA-256 esperado (veio {obtido[:16]}…). "
                                    "Nada foi instalado.")
        schemas = _achar_schemas(lib)

        # Monta a pasta nova ao lado do destino (mesmo disco: a troca é um rename).
        nova = Path(tempfile.mkdtemp(prefix=destino.name + ".nova-", dir=destino.parent))
        try:
            for item in lib.parent.iterdir():  # a lib e as que a acompanham (no Windows, as DLLs)
                if item.is_file():
                    shutil.copy2(item, nova / item.name)
            (nova / "Schemas").mkdir()
            for xsd in schemas.glob("*.xsd"):
                shutil.copy2(xsd, nova / "Schemas" / xsd.name)
            if not WINDOWS:
                os.chmod(nova, 0o755)
            _trocar(nova, destino)
        except BaseException:
            shutil.rmtree(nova, ignore_errors=True)
            raise
    total = len(list((destino / "Schemas").glob("*.xsd")))
    log.info("ACBrLib instalada em %s (%d Schemas, sha256 %s)", destino, total, obtido[:16])
    return {"ok": True, "pasta": str(destino), "lib": str(destino / NOME_LIB), "schemas": total, "sha256": obtido,
            "conferida": bool(sha256), "mensagem": f"ACBrLib instalada ({total} Schemas)."}


def precisa_instalar():
    """(url, sha256) quando há pacote configurado e a pasta instalada não confere; senão None."""
    url, sha256 = pacote_configurado()
    if not url or instalada_confere(pasta_instalada(), sha256):
        return None
    return url, sha256


def main(argv=None):
    leitor = argparse.ArgumentParser(prog="python -m app.instalador", description="Instala a ACBrLib.")
    leitor.add_argument("--url")
    leitor.add_argument("--arquivo")
    leitor.add_argument("--sha256")
    leitor.add_argument("--destino")
    argumentos = leitor.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    try:
        resultado = instalar(url=argumentos.url, arquivo=argumentos.arquivo, sha256=argumentos.sha256,
                             destino=argumentos.destino)
    except FalhaNaInstalacao as erro:
        print(json.dumps({"ok": False, "mensagem": str(erro)}, ensure_ascii=False))
        return 1
    print(json.dumps(resultado, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
