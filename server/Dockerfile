# Comunicador Fiscal ACBrLib (server/README.md, docs/INTEGRACAO.md).
#
# Debian, e não Alpine: a libacbrnfe64.so é compilada contra a glibc. A lib NÃO
# vem no repositório: o comunicador a baixa e confere sozinho (app/instalador.py).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ACBR_MODO=nuvem \
    ACBR_DATA_DIR=/app/data \
    ACBR_LIB_PATH=/app/libs/libacbrnfe64.so \
    ACBR_CONFIG=/app/config/ACBrLib.ini \
    TZ=America/Sao_Paulo

WORKDIR /app

# libxml2 + OpenSSL: assinatura e validação; fontconfig/fontes: impressão do DANFE.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 openssl ca-certificates libfontconfig1 fontconfig fonts-dejavu-core tzdata \
    && rm -rf /var/lib/apt/lists/* \
    # A ACBrLib abre "libxml2.so", sem versão, e o pacote só traz o .so.2 (o
    # nome curto é do libxml2-dev). Sem o atalho a lib carrega e o /health
    # responde 200, mas a ASSINATURA do XML falha na primeira nota.
    && ln -sf "$(ls /usr/lib/*-linux-gnu/libxml2.so.2 | head -n 1)" /usr/lib/libxml2.so \
    && ldconfig \
    # O fuso do SISTEMA também, onde a ACBrLib o procura (/etc/timezone, que
    # dizia Etc/UTC). O comunicador já o grava a cada nota (TimeZone.Str):
    # isto é a segunda defesa contra a nota sair em UTC (rejeição 704).
    && ln -sf /usr/share/zoneinfo/America/Sao_Paulo /etc/localtime \
    && echo America/Sao_Paulo > /etc/timezone

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY config/ ./config/

# Onde a ACBrLib pode estar, na ordem em que vale (app/motor.py):
#   1. /app/libs      montada pela instalação (volume ./libs)
#   2. /opt/acbr      EMBUTIDA na imagem: a de embutida/, que vem no repositório
#                     (ACBrLibNFe r48608, licenças em licencas/). Nada é baixado.
#   3. /app/data/lib  instalada por /v1/config/lib ou ACBRLIB_PACOTE_URL, se alguém
#                     quiser outra versão sem refazer a imagem.
# Trocar a embutida no build: --build-arg ACBRLIB_PACOTE_URL e ACBRLIB_SO_SHA256 (o
# arg fica no histórico da imagem; com link privado, baixe antes para embutida/).
COPY embutida/ /opt/acbr/
ARG ACBRLIB_PACOTE_URL=""
ARG ACBRLIB_SO_SHA256=""
RUN if [ -n "$ACBRLIB_PACOTE_URL" ]; then \
        python -m app.instalador --url "$ACBRLIB_PACOTE_URL" --sha256 "$ACBRLIB_SO_SHA256" --destino /opt/acbr; \
    fi
# Depois do RUN: o instalador troca a pasta inteira, e as licenças têm de ficar.
COPY licencas/ /opt/acbr/LICENCAS/
ENV LD_LIBRARY_PATH=/app/libs:/opt/acbr:/app/data/lib

EXPOSE 8030

# Sem isto o 503 do /health (lib ausente) não aparecia no `docker ps`. A imagem slim
# não tem curl: o próprio Python confere. Não reinicia sozinho — só fica visível.
# O start-period cobre o primeiro download da lib.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8030/health', timeout=4)"]

# UM worker: a ACBrLib não é reentrante para o mesmo handle (`app/acbrlib.py`).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8030", "--workers", "1"]
