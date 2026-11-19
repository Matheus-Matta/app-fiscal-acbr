"""A ACBrLib NFe (versão MT) via ctypes — a biblioteca original, sem modificar.

Sequência oficial: `NFE_Inicializar` → `NFE_LimparLista` → `NFE_CarregarINI` →
`NFE_Assinar` → `NFE_Validar` → `NFE_Enviar` (ou `NFE_Consultar`/`NFE_Cancelar`).
Um retorno 0 é a CHAMADA que deu certo; a autorização é o cStat (`sefaz.py`).

A lib não é reentrante para o mesmo handle: um handle por processo, atrás de
uma trava — e o uvicorn roda com UM worker (Dockerfile). A configuração (UF,
ambiente, modelo, certificado, CSC, forma de emissão) é gravada a cada chamada,
porque o comunicador atende qualquer CNPJ que o cliente mandar.

Os valores das enumerações (`Ambiente`, `ModeloDF`, `FormaEmissao`) seguem a
documentação da ACBrLib e são os primeiros a conferir na homologação.
"""
import contextlib
import ctypes
import os
import re
import threading

from app import ini, sefaz

TAMANHO = 1024 * 512
#: Quanto uma chamada espera a vez na trava. A espera soma ao timeout da SEFAZ
#: (30 s) contra o do cliente (ACBRLIB_TIMEOUT, 40 s): esperar demais faria o
#: cliente desistir de uma nota que ainda SERIA enviada. Sem a vez, nada foi
#: enviado — é seguro responder `sem_comunicacao`.
ESPERA_TRAVA = float(os.environ.get("ACBR_ESPERA_TRAVA", "8"))
FORMA_EMISSAO = {"1": "0", "9": "8"}  # teNormal, teOffLine (NFC-e)
_QR = re.compile(r"<qrCode>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</qrCode>", re.S)
_DIGEST = re.compile(r"<DigestValue>(.*?)</DigestValue>", re.S)
_CHAVE = re.compile(r'Id="NFe(\d{44})"')


def fuso_local():
    """O fuso do container no formato da ACBrLib: "-03:00" (6 caracteres)."""
    import time

    if hasattr(time, "tzset"):  # relê o TZ do ambiente (só existe no Unix)
        time.tzset()
    bruto = time.strftime("%z")  # "-0300"
    return f"{bruto[:3]}:{bruto[3:]}"


class AcbrLib:
    nome = "acbrlib"

    def __init__(self, caminho, arquivo_config="/app/config/ACBrLib.ini", schemas=None):
        self.lib = ctypes.CDLL(caminho)
        self.trava = threading.Lock()
        self.handle = ctypes.c_void_p()
        self._ok(self.lib.NFE_Inicializar(ctypes.byref(self.handle), _c(arquivo_config), _c("")))
        if schemas:
            # O do .ini aponta /app/libs; a lib embutida tem os seus em /opt/acbr.
            self._ok(self.lib.NFE_ConfigGravarValor(self.handle, _c("NFe"), _c("PathSchemas"), _c(schemas)))
        # Nos dois modos o XML só volta na resposta: nenhuma cópia fica no comunicador.
        # Guardar a nota é do cliente. Gravado aqui também, caso o .ini diga outra coisa.
        self._ok(self.lib.NFE_ConfigGravarValor(self.handle, _c("NFe"), _c("SalvarGer"), _c("0")))

    # ── chamadas de baixo nível ───────────────────────────────────────────
    @contextlib.contextmanager
    def _vez(self):
        if not self.trava.acquire(timeout=ESPERA_TRAVA):
            raise sefaz.FalhaDeComunicacao(
                "O comunicador está ocupado com outra nota; esta nem foi enviada. Tente de novo.",
                "comunicador_ocupado")
        try:
            yield
        finally:
            try:
                self._esquecer_segredos()
            finally:
                self.trava.release()

    def _esquecer_segredos(self):
        """O A1, a senha e o CSC não ficam na lib entre uma chamada e outra.

        Cada chamada grava os seus de novo (`_configurar`). Falhar aqui não pode
        esconder o resultado da nota: o erro é ignorado.
        """
        for secao, chave in (("DFe", "DadosPFX"), ("DFe", "Senha"), ("NFe", "IdCSC"), ("NFe", "CSC")):
            with contextlib.suppress(Exception):
                self.lib.NFE_ConfigGravarValor(self.handle, _c(secao), _c(chave), _c(""))

    def _ok(self, codigo, enviando=False):
        if codigo < 0:
            raise _classificar(self._ultimo_retorno(), enviando=enviando)

    def _ultimo_retorno(self, tamanho_inicial=TAMANHO):
        # A lib informa em `tamanho` quanto a resposta precisa: se não coube, pede de
        # novo com o buffer do tamanho certo — antes saía cortada em 512 KB, calada.
        capacidade = tamanho_inicial
        while True:
            tamanho = ctypes.c_int(capacidade)
            buffer = ctypes.create_string_buffer(capacidade + 1)
            self.lib.NFE_UltimoRetorno(self.handle, buffer, ctypes.byref(tamanho))
            if tamanho.value <= capacidade:
                return buffer.value.decode("utf-8", "replace")
            capacidade = tamanho.value

    def _texto(self, funcao, *args, enviando=False):
        tamanho = ctypes.c_int(TAMANHO)
        buffer = ctypes.create_string_buffer(TAMANHO + 1)
        self._ok(funcao(self.handle, *args, buffer, ctypes.byref(tamanho)), enviando=enviando)
        if tamanho.value > TAMANHO:  # a resposta não coube: a lib a guarda no último retorno
            return self._ultimo_retorno(tamanho.value)
        return buffer.value.decode("utf-8", "replace")

    def _configurar(self, pedido, tp_emis="1"):
        valores = {
            ("DFe", "UF"): pedido.uf,
            ("DFe", "DadosPFX"): pedido.certificado.pfx_base64,
            ("DFe", "Senha"): pedido.certificado.senha,
            ("NFe", "Ambiente"): "0" if pedido.ambiente == "1" else "1",
            ("NFe", "ModeloDF"): "1" if pedido.modelo == "65" else "0",
            ("NFe", "IdCSC"): pedido.csc.id,
            ("NFe", "CSC"): pedido.csc.token,
            ("NFe", "VersaoQRCode"): "2",
            ("NFe", "FormaEmissao"): FORMA_EMISSAO.get(tp_emis, "0"),
            # O dhEmi chega SEM fuso; deixado à lib, ela lia o do sistema (UTC
            # no container) e a nota das 22:36 de Brasília saía +00:00 — três
            # horas "atrasada", rejeição 704. 2 = tzManual (ACBrUtil.DateTime).
            ("DFe", "TimeZone.Modo"): "2",
            ("DFe", "TimeZone.Str"): pedido.fuso or fuso_local(),
        }
        for (secao, chave), valor in valores.items():
            self._ok(self.lib.NFE_ConfigGravarValor(self.handle, _c(secao), _c(chave), _c(valor or "")))

    def _xml_atual(self):
        return self._texto(self.lib.NFE_ObterXml, ctypes.c_int(0))

    # ── operações do contrato ─────────────────────────────────────────────
    def emitir(self, pedido):
        with self._vez():
            self._configurar(pedido, pedido.tp_emis)
            self._ok(self.lib.NFE_LimparLista(self.handle))
            self._ok(self.lib.NFE_CarregarINI(self.handle, _c(pedido.ini)))
            self._ok(self.lib.NFE_Assinar(self.handle))
            self._ok(self.lib.NFE_Validar(self.handle))
            assinado = self._xml_atual()
            if pedido.tp_emis == "9":
                return {"situacao": "contingencia", **_do_xml(assinado), "xml": assinado}
            return self._enviar(pedido)

    def transmitir(self, pedido):
        with self._vez():
            self._configurar(pedido, "9")
            self._ok(self.lib.NFE_LimparLista(self.handle))
            self._ok(self.lib.NFE_CarregarXML(self.handle, _c(pedido.xml)))
            return self._enviar(pedido)

    def _enviar(self, pedido):
        resposta = ini.ler(self._texto(self.lib.NFE_Enviar, ctypes.c_int(1), ctypes.c_bool(False),
                                       ctypes.c_bool(True), ctypes.c_bool(False), enviando=True))
        nota = ini.primeira(resposta, "nfe", "retorno", "envio")
        cstat = nota.get("cstat", "")
        if cstat in sefaz.DUPLICIDADE:
            return self._consultar_chave(pedido, nota.get("chdfe") or _do_xml(self._xml_atual())["chave"])
        return self._resultado(nota, xml=self._xml_atual())

    def consultar(self, pedido):
        with self._vez():
            self._configurar(pedido)
            return self._consultar_chave(pedido, pedido.chave)

    def _consultar_chave(self, _pedido, chave):
        resposta = ini.ler(self._texto(self.lib.NFE_Consultar, _c(chave), ctypes.c_bool(False)))
        return self._resultado(ini.primeira(resposta, "consulta", "retorno"), chave=chave)

    def cancelar(self, pedido):
        with self._vez():
            self._configurar(pedido)
            resposta = ini.ler(self._texto(self.lib.NFE_Cancelar, _c(pedido.chave), _c(pedido.justificativa),
                                           _c(pedido.cnpj), ctypes.c_int(1), enviando=True))
            return self._resultado(ini.primeira(resposta, "evento", "cancelamento", "retorno"),
                                   chave=pedido.chave)

    def status_servico(self, pedido):
        with self._vez():
            self._configurar(pedido)
            resposta = ini.primeira(ini.ler(self._texto(self.lib.NFE_StatusServico)), "status")
        cstat = resposta.get("cstat", "")
        return {"online": cstat == "107", "cstat": cstat, "motivo": resposta.get("xmotivo", "")}

    @staticmethod
    def _resultado(campos, *, xml="", chave=""):
        cstat = campos.get("cstat", "")
        return {"situacao": sefaz.situacao(cstat), "cstat": cstat, "motivo": campos.get("xmotivo", ""),
                "chave": campos.get("chdfe") or campos.get("chnfe") or chave,
                "protocolo": campos.get("nprot", ""), "recebido_em": campos.get("dhrecbto", ""),
                "xml": xml, **({k: v for k, v in _do_xml(xml).items() if k != "chave"} if xml else {})}


def _do_xml(xml):
    """Chave, QR Code e digest de um XML assinado."""
    def achar(padrao):
        return (padrao.search(xml or "") or [None, ""])[1]

    return {"chave": achar(_CHAVE), "qrcode": achar(_QR).strip(), "digest_value": achar(_DIGEST)}


#: Falhas que só acontecem ANTES de a nota sair: nome não resolve, conexão recusada,
#: rede inacessível (códigos Winsock 11001, 10061, 10065, 10051).
_ANTES_DO_ENVIO = ("resolver", "could not resolve", "host not found", "host desconhecido", "connection refused",
                   "conexão recusada", "conexao recusada", "11001", "10061", "10065", "10051",
                   "network is unreachable", "rede inacess")
_COMUNICACAO = ("socket", "conex", "http", "host", "resolver", "winsock")


def _classificar(mensagem, enviando=False):
    """A falha da lib vira a família do contrato (docs/INTEGRACAO.md).

    `enviando`: a falha veio de uma chamada que transmite (envio, cancelamento).
    Aí, falha de comunicação só é `sem_comunicacao` ("seguro reenviar ou entrar
    em contingência") quando é das que acontecem antes de a nota sair; o resto —
    "Erro HTTP 500", conexão caída no meio — pode ter chegado à SEFAZ: `incerto`.
    """
    texto = mensagem.lower()
    if any(p in texto for p in ("certificado", "pfx", "senha", "csc", "biblioteca")):
        return sefaz.FalhaDeConfiguracao(mensagem, _motivo_de_configuracao(texto))
    if any(p in texto for p in ("schema", "validar", "rejei", "ini inv")):
        return sefaz.DocumentoInvalido(mensagem)
    if any(p in texto for p in ("timeout", "tempo limite", "timed out", "read timed")):
        return sefaz.FalhaIncerta(mensagem, "sefaz_sem_resposta")
    if any(p in texto for p in _COMUNICACAO):
        if not enviando or any(p in texto for p in _ANTES_DO_ENVIO):
            return sefaz.FalhaDeComunicacao(mensagem, "sefaz_sem_comunicacao")
        return sefaz.FalhaIncerta(mensagem, "sefaz_sem_resposta")
    # Falha não reconhecida durante o envio: tratar como INCERTA é o lado seguro —
    # o cliente consulta antes de qualquer reenvio.
    return sefaz.FalhaIncerta(mensagem)


def _motivo_de_configuracao(texto):
    if "senha" in texto:
        return "senha_invalida"
    if any(p in texto for p in ("vencid", "expirad", "expired")):
        return "certificado_vencido"
    if any(p in texto for p in ("certificado", "pfx")):
        return "certificado_invalido"
    return ""


def _c(texto):
    return str(texto).encode("utf-8")
