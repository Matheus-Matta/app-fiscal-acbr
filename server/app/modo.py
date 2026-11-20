"""Os dois jeitos de rodar o comunicador (`ACBR_MODO`).

**nuvem** — o Docker num servidor da internet, falando só por API:

- toda rota `/v1` exige o token (`ACBRLIB_TOKEN`) **e** o corpo cifrado de ponta a
  ponta com a `ACBR_E2E_KEY`, que o PDV/ERP também tem (`sigilo.py`);
- o emitente (CNPJ, UF, certificado A1, CSC) vem **em toda chamada** e nunca é
  gravado: não há `/v1/config/emitente` nem `/v1/config/token`;
- a lib esquece o certificado e o CSC ao fim de cada chamada (`acbrlib.py`);
- não sobe com token fraco (menos de 32 caracteres) ou sem a chave;
- um IP que erra o token `ACBR_TENTATIVAS` vezes fica bloqueado (429) por
  `ACBR_BLOQUEIO_SEGUNDOS`.

**local** — o desktop, o serviço Windows ou um Docker na máquina da loja:

- toda rota `/v1` exige só o token; o corpo é JSON comum, sem cifra;
- os segredos do emitente (A1, senha, CSC) ficam guardados, cifrados com a
  `ACBR_CHAVE_COFRE` (`configuracao.py`), e o PDV manda os dados da emissão (UF,
  ambiente, modelo, fuso) e o documento;
- as rotas `/v1/config/*`, que trocam certificado e token, só atendem a própria
  máquina (`ACBR_CONFIG_REDES`, padrão 127.0.0.1 e ::1). Um PDV da rede emite, mas
  não reconfigura.

Nos dois, o XML da nota não é gravado em disco: volta só na resposta (`acbrlib.py`).
"""
import ipaddress
import math
import os
import threading
import time

NUVEM = "nuvem"
LOCAL = "local"
TOKEN_MINIMO_NUVEM = 32


class ConfiguracaoInvalida(RuntimeError):
    """O comunicador não deve subir assim: a mensagem diz o que corrigir."""


def atual():
    """O modo pedido no ambiente. Sem nada, nuvem: o lado mais restrito."""
    valor = os.environ.get("ACBR_MODO", "").strip().lower() or NUVEM
    if valor not in (NUVEM, LOCAL):
        raise ConfiguracaoInvalida(f"ACBR_MODO={valor!r} não existe: use 'nuvem' ou 'local'.")
    return valor


def conferir_nuvem():
    """Token forte e chave válida, ou o comunicador nem sobe."""
    from app import sigilo

    token = os.environ.get("ACBRLIB_TOKEN", "")
    if len(token) < TOKEN_MINIMO_NUVEM:
        raise ConfiguracaoInvalida(
            f"Modo nuvem: ACBRLIB_TOKEN precisa de ao menos {TOKEN_MINIMO_NUVEM} caracteres "
            "(openssl rand -base64 48).")
    if any(c.isspace() or c == "#" for c in token) or not token.isascii():
        raise ConfiguracaoInvalida("Modo nuvem: ACBRLIB_TOKEN não pode ter espaço, '#' nem acento.")
    try:
        sigilo.validar_chave(os.environ.get("ACBR_E2E_KEY", ""), token)
    except ValueError as erro:
        raise ConfiguracaoInvalida(f"Modo nuvem: {erro}") from None


# ── local: a chave do cofre e quem pode configurar ───────────────────────────
def chave_do_cofre(bruta=None):
    """Os 32 bytes da ACBR_CHAVE_COFRE (ou da ACBR_E2E_KEY, das instalações anteriores).

    `bruta`: confere este valor em vez do que está no ambiente.
    """
    import base64
    import binascii

    if bruta is None:
        bruta = os.environ.get("ACBR_CHAVE_COFRE") or os.environ.get("ACBR_E2E_KEY", "")
    try:
        chave = base64.b64decode(bruta, validate=True)
    except (binascii.Error, ValueError):
        chave = b""
    if len(chave) != 32:
        raise ValueError("ACBR_CHAVE_COFRE inválida: use 32 bytes em base64 (openssl rand -base64 32).")
    return chave


def redes_de_configuracao():
    """As redes de ACBR_CONFIG_REDES. O comunicador local confere ao subir: valor ruim, não sobe."""
    bruto = os.environ.get("ACBR_CONFIG_REDES", "").strip() or "127.0.0.1/32,::1/128"
    redes = []
    for parte in bruto.split(","):
        if parte.strip():
            try:
                redes.append(ipaddress.ip_network(parte.strip(), strict=False))
            except ValueError:
                raise ConfiguracaoInvalida(f"ACBR_CONFIG_REDES: {parte.strip()!r} não é um IP nem uma rede.") from None
    return redes


def pode_configurar(ip):
    """Se este IP pode chamar /v1/config/* no modo local."""
    try:
        endereco = ipaddress.ip_address(ip or "")
    except ValueError:
        return False
    if endereco.version == 6 and endereco.ipv4_mapped:
        endereco = endereco.ipv4_mapped
    try:
        redes = redes_de_configuracao()
    except ConfiguracaoInvalida:
        return False  # mudou no meio do caminho e ficou inválida: o lado seguro é recusar
    return any(endereco in rede for rede in redes)


# ── nuvem: bloqueio de quem erra o token ─────────────────────────────────────
def _inteiro(variavel, valor, padrao):
    bruto = valor if valor is not None else os.environ.get(variavel, "").strip() or padrao
    try:
        numero = int(bruto)
    except (TypeError, ValueError):
        numero = 0
    if numero < 1:
        raise ConfiguracaoInvalida(f"{variavel}={bruto!r}: use um número inteiro maior que zero.")
    return numero


def quem_conta(ip):
    """A chave do bloqueio para este IP.

    IPv6 conta pela rede /64: é o que um provedor entrega a um só cliente, e contar
    por endereço deixaria quem tem uma /64 trocar de endereço a cada chute. IPv4
    escrito como IPv6 (::ffff:1.2.3.4) conta como o próprio IPv4.
    """
    try:
        endereco = ipaddress.ip_address(ip or "")
    except ValueError:
        return ip or ""
    if endereco.version == 6 and endereco.ipv4_mapped:
        return str(endereco.ipv4_mapped)
    if endereco.version == 6:
        # Pelo número, e não pelo texto: o texto pode trazer a zona (fe80::1%eth0).
        return str(ipaddress.IPv6Network((int(endereco) >> 64 << 64, 64)))
    return str(endereco)


class Bloqueio:
    """Conta os erros de token por IP (IPv6: por /64) numa janela; passou do limite, bloqueia."""

    def __init__(self, tentativas=None, segundos=None):
        self.tentativas = _inteiro("ACBR_TENTATIVAS", tentativas, 10)
        self.segundos = _inteiro("ACBR_BLOQUEIO_SEGUNDOS", segundos, 900)
        self._erros = {}
        self._bloqueados = {}
        self._trava = threading.Lock()
        self._limpo_em = None

    def restante(self, ip, agora=None):
        """Segundos de bloqueio que ainda faltam para este IP (0: liberado)."""
        agora = time.monotonic() if agora is None else agora
        ip = quem_conta(ip)
        with self._trava:
            ate = self._bloqueados.get(ip, 0)
            if ate <= agora:
                self._bloqueados.pop(ip, None)
                return 0
            return math.ceil(ate - agora)

    #: De quanto em quanto tempo a memória é varrida. Varrer a cada erro custaria uma
    #: passada por todos os IPs a cada chute — num ataque distribuído, CPU de graça.
    LIMPEZA_SEGUNDOS = 60

    def _limpar(self, agora):
        """Esquece erros fora da janela e bloqueios vencidos: IPs que nunca voltam saem."""
        if self._limpo_em is not None and agora - self._limpo_em < self.LIMPEZA_SEGUNDOS:
            return
        self._limpo_em = agora
        self._erros = {k: v for k, v in self._erros.items() if agora - v[1] <= self.segundos}
        self._bloqueados = {k: ate for k, ate in self._bloqueados.items() if ate > agora}

    def errou(self, ip, agora=None):
        """Conta um erro. True quando este erro bloqueou o IP (para registrar só uma vez)."""
        agora = time.monotonic() if agora is None else agora
        ip = quem_conta(ip)
        with self._trava:
            self._limpar(agora)
            quantos, inicio = self._erros.get(ip, (0, agora))
            if agora - inicio > self.segundos:  # sobra de uma janela antiga, ainda não varrida
                quantos, inicio = 0, agora
            quantos += 1
            if quantos >= self.tentativas:
                self._bloqueados[ip] = agora + self.segundos
                self._erros.pop(ip, None)
                return True
            self._erros[ip] = (quantos, inicio)
            return False

    def acertou(self, ip):
        ip = quem_conta(ip)
        with self._trava:
            self._erros.pop(ip, None)
