"""O comunicador empacotado (PyInstaller): a mesma API do Docker, com o mesmo .env, em
http://127.0.0.1:8030. `AcbrFiscal.exe` no Windows, `AcbrFiscal` no Linux.

Serve ao serviço Windows (instalador.iss) e ao desktop (Windows e Linux), que o abre
com ACBR_DATA_DIR apontando para a pasta do usuário e grava o .env antes. Roda no modo
local (`app/modo.py`): o PDV usa só o token, e o emitente fica guardado aqui.

    AcbrFiscal configurar         define o token e as origens (grava o .env)
    AcbrFiscal                    sobe a API
    AcbrFiscal instalar-tarefa    sobe sozinho com o Windows (pede administrador; só Windows)
    AcbrFiscal remover-tarefa
    AcbrFiscal instalar-lib [--url URL --sha256 HASH | --arquivo PACOTE]

O .env fica em %PROGRAMDATA%\\AcbrFiscal (Windows) ou ~/.local/share/AcbrFiscal (Linux),
legível só por quem configurou (e, no Windows, pelo serviço e pelos administradores).
"""
import argparse
import base64
import logging
import logging.handlers
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

TAREFA = "AcbrFiscal"
SID_SERVICO = "S-1-5-20"  # NETWORK SERVICE: alcança a SEFAZ sem ser administrador.
SIDS_FIXOS = ("S-1-5-18", "S-1-5-32-544", SID_SERVICO)  # SYSTEM, Administradores, o serviço
PORTA_PADRAO = "8030"

XML_TAREFA = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers><BootTrigger><Enabled>true</Enabled></BootTrigger></Triggers>
  <Principals><Principal id="servico"><UserId>{sid}</UserId><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowHardTerminate>true</AllowHardTerminate>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
  </Settings>
  <Actions Context="servico"><Exec><Command>{exe}</Command></Exec></Actions>
</Task>
"""


WINDOWS = os.name == "nt"
#: O nome da ACBrLib em cada sistema (o mesmo de app/instalador.py).
NOME_LIB = "ACBrNFe64.dll" if WINDOWS else "libacbrnfe64.so"
#: Onde o Linux costuma guardar a libxml2 (Debian/Ubuntu multiarch, Fedora/RHEL, Arch).
PASTAS_DE_SISTEMA = ("/usr/lib/x86_64-linux-gnu", "/lib/x86_64-linux-gnu", "/usr/lib64", "/lib64", "/usr/lib", "/lib")


def pasta_dados():
    if WINDOWS:
        padrao = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "AcbrFiscal"
    else:
        padrao = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "AcbrFiscal"
    return Path(os.environ.get("ACBR_DATA_DIR") or padrao)


def pasta_programa():
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent


def ler_env(caminho):
    valores = {}
    for linha in caminho.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            valores[chave.strip()] = valor.strip()
    return valores


def _restringir(pasta):
    """Tira a herança: sem isto, qualquer usuário do PC lê o .env em ProgramData."""
    if not WINDOWS:
        os.chmod(pasta, 0o700)  # Linux: só o dono lê o token e a chave do cofre
        return
    quem =subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=True)
    sids = (*SIDS_FIXOS, quem.stdout.strip().split(",")[-1].strip('"'))
    permissoes = [f"*{sid}:(OI)(CI)F" for sid in sids]
    subprocess.run(["icacls", str(pasta), "/inheritance:r", "/grant:r", *permissoes],
                   capture_output=True, text=True, check=True)


def _nova_chave():
    return base64.b64encode(secrets.token_bytes(32)).decode()


def configurar(token=None, origens=None, forcar=False, simulador=False, entrada=input):
    """Grava o .env do modo local: o token que o PDV usa e a chave do cofre (gerada)."""
    from app import modo

    pasta = pasta_dados()
    arquivo = pasta / ".env"
    anterior = ler_env(arquivo) if arquivo.exists() else {}
    if anterior and not forcar:
        # Trocar em silêncio derrubaria todo PDV que já usa o token atual.
        raise SystemExit(f"Já configurado em {arquivo}. Use --forcar para trocar o token.")

    token = token if token is not None else entrada("Token de acesso (Enter gera um): ").strip()
    token = token or secrets.token_urlsafe(32)
    origens = origens if origens is not None else entrada("Origens de navegador permitidas (Enter: nenhuma): ").strip()
    if any(c.isspace() or c == "#" for c in token) or not token.isascii():
        raise SystemExit("O token não pode ter espaço, '#' nem acento.")
    if len(token) < 16:
        raise SystemExit("O token precisa de ao menos 16 caracteres.")
    # A chave do cofre não muda com --forcar: trocá-la deixaria os emitentes guardados ilegíveis.
    # Instalações anteriores guardavam com a ACBR_E2E_KEY: ela vira a chave do cofre.
    chave = anterior.get("ACBR_CHAVE_COFRE") or anterior.get("ACBR_E2E_KEY") or _nova_chave()
    try:
        modo.chave_do_cofre(chave)
    except ValueError as erro:
        raise SystemExit(str(erro)) from None
    if token == chave:
        raise SystemExit("O token não pode ser igual à chave do cofre.")
    if any(c in "\r\n" for c in origens):
        raise SystemExit("As origens não podem ter quebra de linha.")

    pasta.mkdir(parents=True, exist_ok=True)
    # A pasta primeiro: o arquivo já nasce herdando a permissão restrita.
    _restringir(pasta)
    # O que não é desta tela (ACBRLIB_PACOTE_URL, ACBR_PORT, ACBR_HOST...) fica como estava.
    # A ACBR_E2E_KEY antiga sai: virou a chave do cofre, e o modo local não usa cifra.
    valores = {chave_env: valor for chave_env, valor in anterior.items() if chave_env != "ACBR_E2E_KEY"}
    valores.update({"ACBR_MODO": "local", "ACBRLIB_TOKEN": token, "ACBR_CHAVE_COFRE": chave,
                    "ACBR_ALLOWED_ORIGINS": origens, "ACBR_SIMULADOR": "1" if simulador else "0"})
    corpo = "".join(f"{nome}={valor}\n" for nome, valor in valores.items())
    arquivo.write_text(corpo, encoding="utf-8", newline="\n")
    print(f"\nConfigurado em {arquivo}. Coloque este token no PDV (Authorization: Bearer):\n"
          f"  ACBRLIB_TOKEN={token}\n")


def _preparar_ambiente():
    arquivo = pasta_dados() / ".env"
    if not arquivo.exists():
        if not sys.stdin or not sys.stdin.isatty():
            raise SystemExit(f"Falta {arquivo}. Rode: AcbrFiscal.exe configurar")
        configurar()
    # O que já está no ambiente vale sobre o arquivo, como no Docker.
    for chave, valor in ler_env(arquivo).items():
        os.environ.setdefault(chave, valor)
    # O .exe é o comunicador da loja: local, a não ser que o .env diga outra coisa.
    os.environ.setdefault("ACBR_MODO", "local")

    dados = pasta_dados()
    # A configuração guardada (`app/configuracao.py`) mora junto do .env.
    os.environ.setdefault("ACBR_DATA_DIR", str(dados))
    # A lib na pasta de dados vale primeiro: o desktop portátil se extrai numa pasta
    # temporária a cada início, e é lá (em dados\lib) que a loja a copia. A do
    # programa só vale se estiver lá (o instalador do serviço a põe); sem nenhuma,
    # a mensagem de "lib ausente" aponta a pasta de dados.
    # Pela DLL, e não pela pasta: uma dados\lib vazia (o botão "Abrir pasta" a cria)
    # escondia a lib que vem junto no .exe.
    junto_do_programa = pasta_programa() / "lib"
    lib = junto_do_programa if (not (dados / "lib" / NOME_LIB).exists()
                                and (junto_do_programa / NOME_LIB).exists()) else dados / "lib"
    ini = dados / "ACBrLib.ini"
    base = (Path(getattr(sys, "_MEIPASS", pasta_programa().parent)) / "config" / "ACBrLib.ini").read_text(encoding="utf-8")
    ini.write_text(base.replace("/app/data", str(dados)).replace("/app/libs", str(lib)), encoding="utf-8")
    os.environ.setdefault("ACBR_LIB_PATH", str(lib / NOME_LIB))
    os.environ.setdefault("ACBR_LIB_EMBUTIDA", str(lib / NOME_LIB))
    # Os Schemas: os que estão ao lado da lib escolhida (app/motor.py).
    os.environ.setdefault("ACBR_CONFIG", str(ini))


def _registrar_log():
    pasta = pasta_dados() / "log"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = logging.handlers.RotatingFileHandler(pasta / "servico.log", maxBytes=2_000_000, backupCount=3,
                                                   encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
                        handlers=[arquivo, logging.StreamHandler()] if sys.stderr else [arquivo])


def achar_libxml2(pastas=PASTAS_DE_SISTEMA):
    """A libxml2 do sistema (Linux). A .so.2 primeiro: é a ABI com que a ACBrLib foi feita."""
    achadas = [Path(p) / nome for p in pastas if os.path.isdir(p)
               for nome in sorted(os.listdir(p)) if nome.startswith("libxml2.so.")]
    preferidas = [a for a in achadas if a.name == "libxml2.so.2"] + achadas
    return next((a for a in preferidas if a.is_file()), None)


def garantir_libxml2(dados, pastas=PASTAS_DE_SISTEMA):
    """Linux: a ACBrLib abre "libxml2.so", sem versão, e esse nome só existe com o pacote
    -dev. Sem ele a lib carrega, o /health responde 200 e a primeira nota falha na
    ASSINATURA. Cria o atalho em <dados>/compat e o põe no LD_LIBRARY_PATH.

    True quando o LD_LIBRARY_PATH mudou: o carregador do Linux só o lê quando o
    processo começa, e quem chamou precisa se reabrir (`servir`).
    """
    if WINDOWS:
        return False
    alvo = achar_libxml2(pastas)
    if alvo is None:
        print("aviso: libxml2 não encontrada — instale o pacote libxml2 (a assinatura das notas precisa dela)",
              file=sys.stderr)
        return False
    compat = Path(dados) / "compat"
    compat.mkdir(parents=True, exist_ok=True)
    atalho = compat / "libxml2.so"
    if not atalho.is_symlink() or os.readlink(atalho) != str(alvo):
        atalho.unlink(missing_ok=True)
        atalho.symlink_to(alvo)
    caminhos = [c for c in os.environ.get("LD_LIBRARY_PATH", "").split(":") if c]
    if str(compat) in caminhos:
        return False
    os.environ["LD_LIBRARY_PATH"] = ":".join([str(compat), *caminhos])
    return True


def servir():
    _preparar_ambiente()
    if garantir_libxml2(pasta_dados()):
        # Reabre o mesmo processo (o mesmo PID) já com o LD_LIBRARY_PATH novo.
        argumentos = sys.argv if getattr(sys, "frozen", False) else [sys.executable, *sys.argv]
        os.execv(sys.executable, argumentos)
    _registrar_log()
    import uvicorn

    from app.main import app  # depois do .env: o app lê o ambiente ao ser importado

    # UM worker: a ACBrLib não é reentrante para o mesmo handle (`app/acbrlib.py`).
    uvicorn.run(app, host=os.environ.get("ACBR_HOST", "127.0.0.1"),
                port=int(os.environ.get("ACBR_PORT", PORTA_PADRAO)), log_config=None)


def instalar_tarefa():
    if not WINDOWS:
        raise SystemExit("A tarefa é do Windows. No Linux, use o desktop (inicia com o sistema) "
                         "ou o Docker (docker compose up -d).")
    # A tarefa não recebe `configurar`: o serviço só lê, e o .env já precisa existir.
    if not (pasta_dados() / ".env").exists():
        raise SystemExit("Rode 'AcbrFiscal.exe configurar' antes.")
    xml = XML_TAREFA.format(sid=SID_SERVICO, exe=sys.executable)
    try:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "tarefa.xml"
            caminho.write_text(xml, encoding="utf-16")
            subprocess.run(["schtasks", "/Create", "/F", "/TN", TAREFA, "/XML", str(caminho)], check=True)
        subprocess.run(["schtasks", "/Run", "/TN", TAREFA], check=True)
    except subprocess.CalledProcessError:
        raise SystemExit("Não foi possível registrar a tarefa. Rode como administrador.") from None


def remover_tarefa():
    if not WINDOWS:
        raise SystemExit("A tarefa é do Windows.")
    subprocess.run(["schtasks", "/End", "/TN", TAREFA], check=False)
    subprocess.run(["schtasks", "/Delete", "/F", "/TN", TAREFA], check=False)


def instalar_lib(url=None, arquivo=None, sha256=None):
    r"""A ACBrLib em <dados>\lib, como o comunicador faz sozinho ao subir (app/instalador.py)."""
    os.environ.setdefault("ACBR_DATA_DIR", str(pasta_dados()))
    argumentos = [*(["--url", url] if url else []), *(["--arquivo", arquivo] if arquivo else []),
                  *(["--sha256", sha256] if sha256 else []), "--destino", str(pasta_dados() / "lib")]
    from app import instalador

    raise SystemExit(instalador.main(argumentos))


def main(argv=None):
    leitor = argparse.ArgumentParser(prog="AcbrFiscal", description="Comunicador ACBrLib local.")
    comandos = leitor.add_subparsers(dest="comando")
    conf = comandos.add_parser("configurar")
    conf.add_argument("--token")
    conf.add_argument("--origens")
    conf.add_argument("--forcar", action="store_true")
    conf.add_argument("--simulador", action="store_true", help="SEFAZ simulada; nada é emitido de verdade")
    comandos.add_parser("instalar-tarefa")
    comandos.add_parser("remover-tarefa")
    lib = comandos.add_parser("instalar-lib", help="baixa (ou abre) o pacote da ACBrLib, confere e instala")
    lib.add_argument("--url")
    lib.add_argument("--arquivo")
    lib.add_argument("--sha256")
    argumentos = leitor.parse_args(argv)

    if argumentos.comando == "configurar":
        configurar(argumentos.token, argumentos.origens, argumentos.forcar, argumentos.simulador)
    elif argumentos.comando == "instalar-tarefa":
        instalar_tarefa()
    elif argumentos.comando == "remover-tarefa":
        remover_tarefa()
    elif argumentos.comando == "instalar-lib":
        instalar_lib(argumentos.url, argumentos.arquivo, argumentos.sha256)
    else:
        servir()


if __name__ == "__main__":
    main()
