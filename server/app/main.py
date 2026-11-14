"""A API do comunicador: o cliente chama, a ACBrLib executa, a resposta volta.

Igual no Docker, no serviço Windows e no desktop. Os corpos andam cifrados de ponta
a ponta (`sigilo.py`). Os dados do emitente chegam na chamada ou ficam guardados
(`configuracao.py`, gravados pelas rotas `/v1/config/*`). Cada falha vira o `erro`
que o cliente classifica: é o que decide contingência (`sem_comunicacao`), consulta
(`incerto`), recusa e configuração.
"""
import json
import logging
import os
import threading
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app import certificados, configuracao, instalador, modelos, sefaz, sigilo
from app.motor import criar_motor

log = logging.getLogger("acbr")
if not logging.getLogger().handlers:  # o .exe configura o seu (arquivo); o Docker usa este
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

# Sem /docs: os corpos são cifrados, e a página só revelaria que o serviço existe.
app = FastAPI(title="Comunicador ACBrLib", version="1.1", docs_url=None, redoc_url=None, openapi_url=None)
motor = criar_motor()

ORIGENS = {o.strip().rstrip("/") for o in os.environ.get("ACBR_ALLOWED_ORIGINS", "").split(",") if o.strip()}
#: Um XML de NF-e grande tem centenas de KB; o teto só barra o abuso.
LIMITE_CORPO = int(os.environ.get("ACBR_LIMITE_CORPO", str(8 * 1024 * 1024)))

app.add_middleware(CORSMiddleware, allow_origins=sorted(ORIGENS), allow_methods=["GET", "POST"],
                   allow_headers=["Authorization", "Content-Type"])


@app.middleware("http")
async def _origem_permitida(request, proxima):
    # CORS sozinho só esconde a resposta: a chamada ainda executaria no servidor.
    origem = request.headers.get("origin")
    if origem is not None and origem.rstrip("/") not in ORIGENS:
        return JSONResponse({"detail": "Origem não permitida."}, status_code=403)
    tamanho = request.headers.get("content-length", "")
    if tamanho.isdigit() and int(tamanho) > LIMITE_CORPO:
        return JSONResponse({"erro": "sigilo", "motivo": "corpo_grande",
                             "mensagem": "Chamada grande demais."}, status_code=413)
    resposta = await proxima(request)
    # Página da internet chamando 127.0.0.1/rede local: o Chrome pede esta licença
    # no preflight (Private Network Access). Só chega aqui origem da lista.
    if origem is not None and request.headers.get("access-control-request-private-network") == "true":
        resposta.headers["Access-Control-Allow-Private-Network"] = "true"
    return resposta


_ERROS = {
    sefaz.FalhaDeComunicacao: (503, "sem_comunicacao"),
    # 500 e não 504: um 504 o cliente lê como "comunicador fora", e aqui o
    # envio PODE ter acontecido — o certo é consultar.
    sefaz.FalhaIncerta: (500, "incerto"),
    sefaz.DocumentoInvalido: (422, "documento_invalido"),
    sefaz.FalhaDeConfiguracao: (500, "configuracao"),
}


def autenticar(authorization: str = Header(default="")):
    recebido = authorization.removeprefix("Bearer ").strip()
    try:
        confere = configuracao.token_confere(recebido)
    except UnicodeEncodeError:
        confere = False
    if confere is None:
        raise HTTPException(status_code=401, detail="ACBRLIB_TOKEN não configurado neste serviço.")
    if not confere:
        raise HTTPException(status_code=401, detail="token inválido")


def _selado(request, status, corpo):
    """A resposta cifrada, ou em claro quando o pedido nem chegou a ser aberto."""
    nonce = getattr(request.state, "nonce", None)
    if nonce is None:
        return JSONResponse(corpo, status_code=status)
    claro = json.dumps(corpo, ensure_ascii=False).encode()
    return JSONResponse(sigilo.selar_resposta(claro, status, nonce), status_code=status)


@app.exception_handler(sigilo.Recusa)
async def _recusa(request, erro):
    log.warning("%s recusada: %s", request.url.path, erro.motivo)
    return JSONResponse({"erro": "sigilo", "motivo": erro.motivo, "mensagem": erro.mensagem},
                        status_code=erro.status)


@app.exception_handler(sefaz.FalhaFiscal)
async def _falha(request, erro):
    status, codigo = next(((s, c) for classe, (s, c) in _ERROS.items() if isinstance(erro, classe)),
                          (500, "incerto"))
    log.warning("%s -> %s %s (%s)", request.url.path, codigo, erro.motivo or "-", str(erro)[:300])
    return _selado(request, status, {"erro": codigo, "motivo": erro.motivo, "mensagem": str(erro)})


# ── a ACBrLib instalada sozinha (app/instalador.py) ──────────────────────────
_instalacao = {"situacao": "parada", "mensagem": ""}
_trava_instalacao = threading.Lock()


def _instalar(url=None, sha256=None):
    """Baixa, confere e instala; depois troca o motor, sem reiniciar. Uma por vez."""
    global motor
    if not _trava_instalacao.acquire(blocking=False):
        raise sefaz.FalhaDeConfiguracao("Já há uma instalação da ACBrLib em andamento.", "instalacao_em_andamento")
    try:
        _instalacao.update(situacao="instalando", mensagem="Baixando e instalando a ACBrLib…")
        if motor.nome == "ausente":
            motor.informar_instalacao("Instalando a ACBrLib agora…")
        try:
            resultado = instalador.instalar(url=url, sha256=sha256)
        except instalador.FalhaNaInstalacao as erro:
            _instalacao.update(situacao="falhou", mensagem=str(erro))
            if motor.nome == "ausente":
                motor.informar_instalacao(f"A instalação automática falhou: {erro}")
            raise sefaz.FalhaDeConfiguracao(str(erro), "instalacao_falhou") from None
        _instalacao.update(situacao="instalada", mensagem=resultado["mensagem"])
        if motor.nome != "simulador":
            motor = criar_motor()
        return resultado
    finally:
        _trava_instalacao.release()


def _instalar_ao_subir():
    try:
        _instalar()
    except sefaz.FalhaFiscal as erro:
        log.warning("ACBrLib não instalada automaticamente: %s", erro)
    except Exception:  # a instalação nunca derruba o comunicador
        log.exception("falha inesperada ao instalar a ACBrLib")


# Sem lib e com pacote configurado: instala em segundo plano. O comunicador já
# responde enquanto isso (o /health diz "Instalando a ACBrLib agora…").
if motor.nome == "ausente" and instalador.precisa_instalar():
    threading.Thread(target=_instalar_ao_subir, name="instalar-acbrlib", daemon=True).start()


@app.get("/health")
def health():
    corpo = {"ok": motor.nome != "ausente", "motor": motor.nome, "lib": motor.nome == "acbrlib",
             "simulador": motor.nome == "simulador"}
    if motor.nome == "ausente":
        # 503 marca o container unhealthy (HEALTHCHECK do Dockerfile) — visível, sem reiniciar.
        return JSONResponse({**corpo, "mensagem": motor.mensagem}, status_code=503)
    return corpo


def _rota(caminho, modelo, funcao):
    """Uma rota cifrada: abre o envelope, valida o corpo, executa e sela a resposta."""

    async def abrir(request: Request):
        bruto = await request.body()
        if len(bruto) > LIMITE_CORPO:
            raise sigilo.Recusa(413, "corpo_grande", "Chamada grande demais.")
        corpo, request.state.nonce = sigilo.abrir_pedido(bruto, request.method, caminho)
        try:
            return modelo.model_validate_json(corpo)
        except ValidationError as erro:
            # Só o nome dos campos: o erro padrão ecoaria o corpo, com certificado e senha.
            campos = ", ".join(".".join(map(str, e["loc"])) or "corpo" for e in erro.errors(include_input=False))
            raise sefaz.DocumentoInvalido(f"Campos inválidos: {campos}.", "campos_invalidos") from None

    def executar(request: Request, pedido=Depends(abrir)):
        inicio = time.monotonic()
        try:
            resultado = funcao(pedido)
        except sefaz.FalhaFiscal:
            raise
        except Exception as erro:
            # Sem isto saía o 500 padrão, em claro e sem pista. Depois de um envio, o
            # lado seguro é "incerto": o cliente consulta antes de reenviar.
            log.exception("%s falhou inesperadamente", caminho)
            raise sefaz.FalhaIncerta(f"Falha inesperada no comunicador ({type(erro).__name__}).",
                                     "falha_interna") from erro
        log.info("%s cnpj=%s situacao=%s cstat=%s chave=%s %.1fs", caminho, getattr(pedido, "cnpj", "") or "-",
                 resultado.get("situacao", "-"), resultado.get("cstat", "-"), resultado.get("chave", "-"),
                 time.monotonic() - inicio)
        return _selado(request, 200, resultado)

    app.post(caminho, dependencies=[Depends(autenticar)])(executar)


def _fiscal(nome):
    def chamar(pedido):
        pedido = configuracao.completar(pedido)
        conferido = certificados.conferir(pedido, exigir=motor.nome == "acbrlib")
        return getattr(motor, nome)(conferido)

    return chamar


_rota("/v1/status-servico", modelos.Contexto, _fiscal("status_servico"))
_rota("/v1/nfe/emitir", modelos.Emitir, _fiscal("emitir"))
_rota("/v1/nfe/transmitir", modelos.Transmitir, _fiscal("transmitir"))
_rota("/v1/nfe/consultar", modelos.Consultar, _fiscal("consultar"))
_rota("/v1/nfe/cancelar", modelos.Cancelar, _fiscal("cancelar"))


# ── configuração (desktop e painel) ──────────────────────────────────────────
def _ler_config(_pedido):
    url, sha256 = instalador.pacote_configurado()
    lib = {"pacote_url": url, "sha256": sha256, **_instalacao}
    if motor.nome == "ausente":
        lib["mensagem_motor"] = motor.mensagem
    return {**configuracao.resumo(), "motor": motor.nome, "lib": lib}


def _instalar_pela_api(pedido):
    if motor.nome == "acbrlib":
        raise sefaz.FalhaDeConfiguracao(
            "A ACBrLib já está carregada. Para trocar de versão, mude ACBRLIB_PACOTE_URL e "
            "ACBRLIB_SO_SHA256 e reinicie o comunicador: ele instala a nova sozinho.", "lib_ja_carregada")
    resultado = _instalar(pedido.url or None, pedido.sha256 or None)
    return {**resultado, "motor": motor.nome}


_rota("/v1/config/ler", modelos.Vazio, _ler_config)
_rota("/v1/config/emitente", modelos.Emitente, configuracao.salvar_emitente)
_rota("/v1/config/lib", modelos.InstalarLib, _instalar_pela_api)
_rota("/v1/config/emitente/remover", modelos.RemoverEmitente, lambda p: configuracao.remover_emitente(p.cnpj))
# O novo token só aparece nesta resposta, cifrada. O anterior deixa de valer na hora.
_rota("/v1/config/token", modelos.TrocarToken, lambda p: {"token": configuracao.trocar_token(p.token)})


if motor.nome == "simulador":
    @app.post("/_simulador/modo", dependencies=[Depends(autenticar)])
    def modo_do_simulador(corpo: dict):
        """Só no simulador: o teste de ponta a ponta troca o "estado da SEFAZ"."""
        os.environ["ACBR_SIMULAR_SEFAZ"] = str(corpo.get("modo", "online"))
        return {"modo": os.environ["ACBR_SIMULAR_SEFAZ"]}
