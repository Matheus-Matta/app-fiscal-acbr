"""O .exe: a mesma API do Docker, com o mesmo .env, em http://127.0.0.1:8030.

Serve ao serviço Windows (instalador.iss) e ao desktop, que o abre com
ACBR_DATA_DIR apontando para a pasta do usuário e grava o .env antes.

    AcbrFiscal.exe configurar         define token, chave e origens (grava o .env)
    AcbrFiscal.exe                    sobe a API
    AcbrFiscal.exe instalar-tarefa    sobe sozinho com o Windows (pede administrador)
    AcbrFiscal.exe remover-tarefa

O .env fica em %PROGRAMDATA%\\AcbrFiscal, legível só pelo serviço, pelos
administradores e por quem configurou.
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


def pasta_dados():
    padrao = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "AcbrFiscal"
    return Path(os.environ.get("ACBR_DATA_DIR") or padrao)


def pasta_programa():
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent


def ler_env(caminho):
    valores = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            valores[chave.strip()] = valor.strip()
    return valores


def _restringir(pasta):
    """Tira a herança: sem isto, qualquer usuário do PC lê o .env em ProgramData."""
    quem = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=True)
    sids = (*SIDS_FIXOS, quem.stdout.strip().split(",")[-1].strip('"'))
    permissoes = [f"*{sid}:(OI)(CI)F" for sid in sids]
    subprocess.run(["icacls", str(pasta), "/inheritance:r", "/grant:r", *permissoes],
                   capture_output=True, text=True, check=True)


def configurar(token=None, chave=None, origens=None, forcar=False, simulador=False, entrada=input):
    from app import sigilo

    pasta = pasta_dados()
    arquivo = pasta / ".env"
    if arquivo.exists() and not forcar:
        # Trocar em silêncio derrubaria todo PDV que já usa os valores atuais.
        raise SystemExit(f"Já configurado em {arquivo}. Use --forcar para trocar o token e a chave.")

    token = token if token is not None else entrada("Token de acesso (Enter gera um): ").strip()
    token = token or secrets.token_urlsafe(32)
    chave = chave if chave is not None else entrada("Chave de criptografia (Enter gera uma): ").strip()
    chave = chave or base64.b64encode(secrets.token_bytes(32)).decode()
    origens = origens if origens is not None else entrada("Origens de navegador permitidas (Enter: nenhuma): ").strip()
    try:
        sigilo.validar_chave(chave, token)
    except ValueError as erro:
        raise SystemExit(str(erro)) from None
    if any(c.isspace() or c == "#" for c in token):
        raise SystemExit("O token não pode ter espaço nem '#'.")

    pasta.mkdir(parents=True, exist_ok=True)
    # A pasta primeiro: o arquivo já nasce herdando a permissão restrita.
    _restringir(pasta)
    corpo = (f"ACBRLIB_TOKEN={token}\nACBR_E2E_KEY={chave}\nACBR_ALLOWED_ORIGINS={origens}\n"
             f"ACBR_SIMULADOR={'1' if simulador else '0'}\n")
    arquivo.write_text(corpo, encoding="utf-8", newline="\n")
    print(f"\nConfigurado em {arquivo}. Coloque estes valores no PDV:\n"
          f"  ACBRLIB_TOKEN={token}\n  ACBR_E2E_KEY={chave}\n")


def _preparar_ambiente():
    arquivo = pasta_dados() / ".env"
    if not arquivo.exists():
        if not sys.stdin or not sys.stdin.isatty():
            raise SystemExit(f"Falta {arquivo}. Rode: AcbrFiscal.exe configurar")
        configurar()
    # O que já está no ambiente vale sobre o arquivo, como no Docker.
    for chave, valor in ler_env(arquivo).items():
        os.environ.setdefault(chave, valor)

    dados = pasta_dados()
    # A configuração guardada (`app/configuracao.py`) mora junto do .env.
    os.environ.setdefault("ACBR_DATA_DIR", str(dados))
    # A lib na pasta de dados vale primeiro: o desktop portátil se extrai numa pasta
    # temporária a cada início, e é lá (em dados\lib) que a loja a copia. A do
    # programa só vale se estiver lá (o instalador do serviço a põe); sem nenhuma,
    # a mensagem de "lib ausente" aponta a pasta de dados.
    junto_do_programa = pasta_programa() / "lib"
    lib = junto_do_programa if (not (dados / "lib").is_dir() and (junto_do_programa / "ACBrNFe64.dll").exists()) \
        else dados / "lib"
    ini = dados / "ACBrLib.ini"
    base = (Path(getattr(sys, "_MEIPASS", pasta_programa().parent)) / "config" / "ACBrLib.ini").read_text(encoding="utf-8")
    ini.write_text(base.replace("/app/data", str(dados)).replace("/app/libs", str(lib)), encoding="utf-8")
    os.environ.setdefault("ACBR_LIB_PATH", str(lib / "ACBrNFe64.dll"))
    os.environ.setdefault("ACBR_LIB_EMBUTIDA", str(lib / "ACBrNFe64.dll"))
    os.environ.setdefault("ACBR_SCHEMAS", str(lib / "Schemas"))
    os.environ.setdefault("ACBR_CONFIG", str(ini))


def _registrar_log():
    pasta = pasta_dados() / "log"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = logging.handlers.RotatingFileHandler(pasta / "servico.log", maxBytes=2_000_000, backupCount=3,
                                                   encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
                        handlers=[arquivo, logging.StreamHandler()] if sys.stderr else [arquivo])


def servir():
    _preparar_ambiente()
    _registrar_log()
    import uvicorn

    from app.main import app  # depois do .env: o app lê o ambiente ao ser importado

    # UM worker: a ACBrLib não é reentrante para o mesmo handle (`app/acbrlib.py`).
    uvicorn.run(app, host=os.environ.get("ACBR_HOST", "127.0.0.1"),
                port=int(os.environ.get("ACBR_PORT", PORTA_PADRAO)), log_config=None)


def instalar_tarefa():
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
    subprocess.run(["schtasks", "/End", "/TN", TAREFA], check=False)
    subprocess.run(["schtasks", "/Delete", "/F", "/TN", TAREFA], check=False)


def main(argv=None):
    leitor = argparse.ArgumentParser(prog="AcbrFiscal", description="Comunicador ACBrLib local.")
    comandos = leitor.add_subparsers(dest="comando")
    conf = comandos.add_parser("configurar")
    conf.add_argument("--token")
    conf.add_argument("--chave")
    conf.add_argument("--origens")
    conf.add_argument("--forcar", action="store_true")
    conf.add_argument("--simulador", action="store_true", help="SEFAZ simulada; nada é emitido de verdade")
    comandos.add_parser("instalar-tarefa")
    comandos.add_parser("remover-tarefa")
    argumentos = leitor.parse_args(argv)

    if argumentos.comando == "configurar":
        configurar(argumentos.token, argumentos.chave, argumentos.origens, argumentos.forcar, argumentos.simulador)
    elif argumentos.comando == "instalar-tarefa":
        instalar_tarefa()
    elif argumentos.comando == "remover-tarefa":
        remover_tarefa()
    else:
        servir()


if __name__ == "__main__":
    main()
