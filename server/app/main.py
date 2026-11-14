"""A API do comunicador: o cliente chama, a ACBrLib executa, a resposta volta.

Igual no Docker e no .exe. Sem estado e sem banco: certificado, CSC e dados fiscais
chegam em cada chamada, cifrados de ponta a ponta (`sigilo.py`), e nada disso é
gravado. Cada falha vira o `erro` que o cliente classifica: é o que decide
contingência (`sem_comunicacao`), consulta (`incerto`), recusa e configuração.
"""
import json
import os
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app import certificados, modelos, sefaz, sigilo
from app.motor import criar_motor

# Sem /docs: os corpos são cifrados, e a página só revelaria que o serviço existe.
app = FastAPI(title="Comunicador ACBrLib", version="1.0", docs_url=None, redoc_url=None, openapi_url=None)
motor = criar_motor()

ORIGENS = {o.strip().rstrip("/") for o in os.environ.get("ACBR_ALLOWED_ORIGINS", "").split(",") if o.strip()}

app.add_middleware(CORSMiddleware, allow_origins=sorted(ORIGENS), allow_methods=["GET", "POST"],
                   allow_headers=["Authorization", "Content-Type"])


@app.middleware("http")
async def _origem_permitida(request, proxima):
    # CORS sozinho só esconde a resposta: a chamada ainda executaria no servidor.
    origem = request.headers.get("origin")
    if origem is not None and origem.rstrip("/") not in ORIGENS:
        return JSONResponse({"detail": "Origem não permitida."}, status_code=403)
    return await proxima(request)


_ERROS = {
    sefaz.FalhaDeComunicacao: (503, "sem_comunicacao"),
    # 500 e não 504: um 504 o cliente lê como "comunicador fora", e aqui o
    # envio PODE ter acontecido — o certo é consultar.
    sefaz.FalhaIncerta: (500, "incerto"),
    sefaz.DocumentoInvalido: (422, "documento_invalido"),
    sefaz.FalhaDeConfiguracao: (500, "configuracao"),
}


def autenticar(authorization: str = Header(default="")):
    esperado = os.environ.get("ACBRLIB_TOKEN", "")
    if not esperado:
        raise HTTPException(status_code=401, detail="ACBRLIB_TOKEN não configurado neste serviço.")
    recebido = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(recebido.encode(), esperado.encode()):
        raise HTTPException(status_code=401, detail="token inválido")


def _selado(request, status, corpo):
    """A resposta cifrada, ou em claro quando o pedido nem chegou a ser aberto."""
    nonce = getattr(request.state, "nonce", None)
    if nonce is None:
        return JSONResponse(corpo, status_code=status)
    claro = json.dumps(corpo, ensure_ascii=False).encode()
    return JSONResponse(sigilo.selar_resposta(claro, status, nonce), status_code=status)


@app.exception_handler(sigilo.Recusa)
async def _recusa(_request, erro):
    return JSONResponse({"erro": "sigilo", "motivo": erro.motivo, "mensagem": erro.mensagem},
                        status_code=erro.status)


@app.exception_handler(sefaz.FalhaFiscal)
async def _falha(request, erro):
    for classe, (status, codigo) in _ERROS.items():
        if isinstance(erro, classe):
            return _selado(request, status, {"erro": codigo, "motivo": erro.motivo, "mensagem": str(erro)})
    return _selado(request, 500, {"erro": "incerto", "mensagem": f"Falha inesperada: {erro}"})


@app.get("/health")
def health():
    corpo = {"ok": motor.nome != "ausente", "motor": motor.nome, "lib": motor.nome == "acbrlib",
             "simulador": motor.nome == "simulador"}
    if motor.nome == "ausente":
        # 503 marca o container unhealthy no `docker ps` — visível, sem reiniciar.
        return JSONResponse({**corpo, "mensagem": motor.mensagem}, status_code=503)
    return corpo


def _operacao(caminho, modelo, nome):
    async def abrir(request: Request):
        corpo, request.state.nonce = sigilo.abrir_pedido(await request.body(), request.method, caminho)
        try:
            return modelo.model_validate_json(corpo)
        except ValidationError as erro:
            # Só o nome dos campos: o erro padrão ecoaria o corpo, com certificado e senha.
            campos = ", ".join(".".join(map(str, e["loc"])) or "corpo" for e in erro.errors(include_input=False))
            raise sefaz.DocumentoInvalido(f"Campos inválidos: {campos}.", "campos_invalidos") from None

    def executar(request: Request, pedido=Depends(abrir)):
        conferido = certificados.conferir(pedido, exigir=motor.nome == "acbrlib")
        return _selado(request, 200, getattr(motor, nome)(conferido))

    app.post(caminho, dependencies=[Depends(autenticar)])(executar)


_operacao("/v1/status-servico", modelos.Contexto, "status_servico")
_operacao("/v1/nfe/emitir", modelos.Emitir, "emitir")
_operacao("/v1/nfe/transmitir", modelos.Transmitir, "transmitir")
_operacao("/v1/nfe/consultar", modelos.Consultar, "consultar")
_operacao("/v1/nfe/cancelar", modelos.Cancelar, "cancelar")


if motor.nome == "simulador":
    @app.post("/_simulador/modo", dependencies=[Depends(autenticar)])
    def modo_do_simulador(corpo: dict):
        """Só no simulador: o teste de ponta a ponta troca o "estado da SEFAZ"."""
        os.environ["ACBR_SIMULAR_SEFAZ"] = str(corpo.get("modo", "online"))
        return {"modo": os.environ["ACBR_SIMULAR_SEFAZ"]}
