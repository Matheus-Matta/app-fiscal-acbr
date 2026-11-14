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
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app import certificados, configuracao, modelos, sefaz, sigilo
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
    return {**configuracao.resumo(), "motor": motor.nome}


_rota("/v1/config/ler", modelos.Vazio, _ler_config)
_rota("/v1/config/emitente", modelos.Emitente, configuracao.salvar_emitente)
_rota("/v1/config/emitente/remover", modelos.RemoverEmitente, lambda p: configuracao.remover_emitente(p.cnpj))
# O novo token só aparece nesta resposta, cifrada. O anterior deixa de valer na hora.
_rota("/v1/config/token", modelos.TrocarToken, lambda p: {"token": configuracao.trocar_token(p.token)})


if motor.nome == "simulador":
    @app.post("/_simulador/modo", dependencies=[Depends(autenticar)])
    def modo_do_simulador(corpo: dict):
        """Só no simulador: o teste de ponta a ponta troca o "estado da SEFAZ"."""
        os.environ["ACBR_SIMULAR_SEFAZ"] = str(corpo.get("modo", "online"))
        return {"modo": os.environ["ACBR_SIMULAR_SEFAZ"]}
