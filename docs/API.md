# Referência da API do Comunicador Fiscal

Para quem escreve o cliente: PDV, ERP, backend. O comunicador assina e transmite NFC-e e
NF-e pela ACBrLib; o cliente monta o documento (INI da ACBrLib), guarda a nota e decide o
que fazer com cada resposta. **O que fazer em cada caso** (contingência, consulta,
reenvio) está em [`INTEGRACAO.md`](INTEGRACAO.md); **como instalar e operar**, em
[`USO.md`](USO.md).

- [1. Visão geral](#1-visão-geral)
- [2. Autenticação e segurança](#2-autenticação-e-segurança)
- [3. A cifra de ponta a ponta (modo nuvem)](#3-a-cifra-de-ponta-a-ponta-modo-nuvem)
- [4. O contexto do emitente](#4-o-contexto-do-emitente)
- [5. Operações fiscais](#5-operações-fiscais)
- [6. Configuração](#6-configuração)
- [7. Saúde (`/health`)](#7-saúde-health)
- [8. Erros](#8-erros)
- [9. Limites e tempos](#9-limites-e-tempos)
- [10. Simulador](#10-simulador)
- [11. Exemplos de cliente](#11-exemplos-de-cliente)

---

## 1. Visão geral

A mesma API roda em dois modos, escolhidos no comunicador por `ACBR_MODO`:

| | **nuvem** | **local** |
|---|---|---|
| Onde roda | Docker num servidor da internet | desktop (Windows/Linux), serviço Windows ou Docker na loja |
| Endereço | `https://fiscal.suaempresa.com.br` (atrás de um proxy HTTPS) | `http://127.0.0.1:8030`, ou `http://<IP do PC>:8030` na rede da loja |
| Cabeçalho | `Authorization: Bearer <token>` | `Authorization: Bearer <token>` |
| Corpo | **envelope cifrado** ([seção 3](#3-a-cifra-de-ponta-a-ponta-modo-nuvem)) | JSON comum |
| Emitente (CNPJ, UF, A1, CSC) | **em toda chamada** | A1 e CSC guardados no comunicador; a chamada traz UF, ambiente, modelo e o documento |
| Rotas de configuração | `/v1/config/ler` e `/v1/config/lib` | todas, **só do próprio computador** |

Para saber em que modo um comunicador está: `GET /health` → `"modo"`.

Todas as rotas `/v1/*` são `POST` com corpo JSON (`Content-Type: application/json`) e
respondem JSON em UTF-8. Nos exemplos deste documento, os corpos aparecem **em claro**: no
modo local é exatamente o que vai e volta; na nuvem é o texto que vai **dentro** do envelope.

## 2. Autenticação e segurança

**Token.** Toda rota `/v1/*` exige `Authorization: Bearer <token>`. Errado ou ausente: `401`.

- Nuvem: o token é o `ACBRLIB_TOKEN` do `.env` (32+ caracteres). Não se troca pela API.
- Local: o token inicial é o do `.env` (o desktop gera um na primeira vez); a tela **Acesso**
  do desktop ou `POST /v1/config/token` gera outro, que passa a valer na hora.

**Bloqueio por tentativas (nuvem).** O IP que errar o token 10 vezes (`ACBR_TENTATIVAS`)
recebe `429` com `Retry-After` por 15 minutos (`ACBR_BLOQUEIO_SEGUNDOS`), **mesmo com o
token certo**. IPv6 conta pela rede /64.

**Cifra (nuvem).** Além do token, o corpo vai cifrado com a `ACBR_E2E_KEY`, que o cliente e
o comunicador têm. O token sozinho não monta uma chamada. Ver [seção 3](#3-a-cifra-de-ponta-a-ponta-modo-nuvem).

**Configuração só da própria máquina (local).** `/v1/config/*` responde `403` a quem não
está em `ACBR_CONFIG_REDES` (padrão `127.0.0.1` e `::1`). Um PDV da rede emite com o token,
mas não troca certificado, CSC nem token.

**Navegador (CORS).** Chamada com cabeçalho `Origin` só passa se a origem estiver em
`ACBR_ALLOWED_ORIGINS` (sem curinga); fora da lista, `403` — mesmo com o token. Programa
nativo (sem `Origin`) segue só pelo token. O comunicador também responde ao *preflight* de
rede privada do Chrome (página da internet chamando `127.0.0.1`).

**No modo local não há cifra:** o token e o documento andam em claro entre o PDV e o
comunicador. Por isso o padrão é ouvir só `127.0.0.1`; aceitar PDVs da rede é para a rede
da loja, confiável.

## 3. A cifra de ponta a ponta (modo nuvem)

AES-256-GCM. Da `ACBR_E2E_KEY` (32 bytes em base64) derivam-se duas chaves com
HKDF-SHA256, **sem salt**, 32 bytes:

| Sentido | `info` do HKDF |
|---|---|
| pedido (cliente → comunicador) | `acbr-e2e-v1 pedido` |
| resposta (comunicador → cliente) | `acbr-e2e-v1 resposta` |

**Pedido.** O JSON da operação é cifrado e vai num envelope:

```json
{"v": 1, "ts": 1794000000, "nonce": "<12 bytes aleatórios em base64>", "dados": "<base64 de cifrado+tag>"}
```

- `ts`: hora atual em segundos Unix. Tolerância de 5 minutos para cada lado.
- `nonce`: 12 bytes aleatórios, **novos a cada tentativa**. Repetir um envelope dá `409`.
- `dados`: base64 de *texto cifrado* seguido da *tag* GCM de 16 bytes.
- Dados autenticados (AAD), em UTF-8, com `\n` entre as partes:

```text
acbr-e2e-v1\nPOST\n/v1/nfe/emitir\n<ts>\n<nonce do pedido, em base64>
```

O AAD amarra o pedido à rota e ao horário: um envelope capturado não serve em outra rota
nem fora da janela.

**Resposta.** Mesmo status HTTP do resultado, corpo:

```json
{"v": 1, "nonce": "<12 bytes em base64>", "dados": "<base64 de cifrado+tag>"}
```

```text
AAD = acbr-e2e-v1\n<status HTTP>\n<nonce do PEDIDO>
```

O AAD amarra a resposta a **este** pedido e a **este** status: ninguém no caminho troca um
`503` por um `200`.

**Regras do cliente:**

1. Só confie numa resposta que **abriu com a chave**.
2. Resposta sem envelope (`401`, `403`, `404`, `429`, `413`, ou `{"erro": "sigilo", ...}`) não é
   decisão fiscal: qualquer um no caminho poderia forjá-la. Trate como "sem resposta" —
   depois de um envio, **consulte antes de reenviar**.
3. Cada tentativa: novo `nonce`, novo envelope.

Implementações prontas e testadas contra o comunicador:
[`exemplos/cliente_nuvem.py`](exemplos/cliente_nuvem.py) (Python) e
[`exemplos/cliente-nuvem.mjs`](exemplos/cliente-nuvem.mjs) (Node 18+). A do próprio
servidor está em [`server/app/sigilo.py`](../server/app/sigilo.py).

| `erro: sigilo`, `motivo` | Status | Causa |
|---|---|---|
| `envelope_invalido` | 400 | corpo em claro, ou fora do formato |
| `fora_da_janela` | 400 | relógios com mais de 5 minutos de diferença |
| `nao_decifrou` | 400 | chave diferente, ou dados alterados no caminho |
| `repetida` | 409 | envelope já recebido |
| `corpo_grande` | 413 | acima de `ACBR_LIMITE_CORPO` (8 MB) |
| `e2e_sem_chave` | 500 | o comunicador está sem `ACBR_E2E_KEY` válida |

## 4. O contexto do emitente

Toda operação fiscal aceita estes campos, além dos seus próprios:

| Campo | Tipo | Valores | Nuvem | Local |
|---|---|---|---|---|
| `cnpj` | texto | 14 posições (12 alfanuméricas + 2 dígitos; aceita pontuação) | **obrigatório** | opcional (único emitente guardado) |
| `uf` | texto | `AC` … `TO` | **obrigatório** | **obrigatório** |
| `ambiente` | texto | `"1"` produção, `"2"` homologação | **obrigatório** | **obrigatório** |
| `modelo` | texto | `"65"` NFC-e, `"55"` NF-e | **obrigatório** | **obrigatório** |
| `fuso` | texto | `"-03:00"`; vazio = o do sistema | opcional | opcional |
| `certificado` | objeto | `{"pfx_base64": "<.pfx em base64>", "senha": "..."}` | obrigatório com a ACBrLib | opcional (o guardado) |
| `csc` | objeto | `{"id": "1", "token": "..."}` (NFC-e) | obrigatório na NFC-e | opcional (o guardado) |
| `referencia` | texto | livre | aceito e ignorado | aceito e ignorado |

**Nuvem:** sem `cnpj`, `uf`, `ambiente` ou `modelo` → `configuracao`,
`dados_do_emitente_ausentes`. Não há padrão para `ambiente` de propósito: esquecê-lo não
pode virar uma nota de homologação que o cliente acha que é de produção. Nada disso é
gravado; o certificado só passa pela memória da lib e é apagado ao fim da chamada.

**Local:** só os segredos ficam guardados (certificado A1 + senha e CSC, pelo CNPJ). Os
dados da emissão — `uf`, `ambiente`, `modelo`, `fuso`, e no INI o regime, CST, CSOSN,
IBS/CBS — vêm em toda chamada; sem `uf`, `ambiente` ou `modelo` → `configuracao`,
`dados_do_emitente_ausentes`. Certificado e CSC vazios na chamada = os guardados. Sem
`cnpj` vale o único emitente; com mais de um → `emitente_nao_informado`.

**Conferência do certificado**, antes de chegar à lib (a recusa é `configuracao`, nunca
contingência): `certificado_ausente`, `senha_invalida`, `certificado_invalido`,
`certificado_vencido`, `cnpj_diferente`. O A1 da matriz vale para a filial (mesma raiz de 8
posições do CNPJ).

## 5. Operações fiscais

### O resultado

Uma operação que **chegou à SEFAZ e voltou** responde `200` com:

| Campo | Descrição |
|---|---|
| `situacao` | `autorizada`, `rejeitada`, `denegada`, `cancelada`, `nao_encontrada`, `processando` ou `contingencia` |
| `cstat`, `motivo` | o código e o texto da SEFAZ |
| `chave` | 44 dígitos |
| `protocolo`, `recebido_em` | da autorização (ou do evento, no cancelamento) |
| `xml` | o XML assinado / `nfeProc` autorizado. **Guarde-o: o comunicador não fica com cópia** |
| `qrcode`, `digest_value` | NFC-e: para o DANFE |

`200` não quer dizer autorizada: **quem diz o destino da nota é a `situacao`** (e o `cstat`).
Duplicidade (cStat 204/539) não chega como recusa: o comunicador consulta e devolve a
situação real. Serviço paralisado (108/109) chega como `erro: sem_comunicacao`.

### `POST /v1/status-servico`

Corpo: só o contexto. Diz se a SEFAZ da UF está atendendo.

```json
// local
{}
// → 200
{"online": true, "cstat": "107", "motivo": "Serviço em operação"}
```

### `POST /v1/nfe/emitir`

| Campo | Obrigatório | |
|---|---|---|
| `ini` | sim | a nota no formato INI da ACBrLib NFe (`[Identificacao]`, `[Emitente]`, `[Produto001]`…) |
| `tp_emis` | não | `"1"` normal (padrão) · `"9"` contingência offline da NFC-e: **só assina**, não transmite |

```json
// local, certificado e CSC guardados
{"uf": "SP", "ambiente": "1", "modelo": "65", "fuso": "-03:00", "ini": "[Identificacao]\ncNF=12345678\nmod=65\nserie=1\nnNF=42\n..."}
// → 200
{"situacao": "autorizada", "cstat": "100", "motivo": "Autorizado o uso da NF-e",
 "chave": "35261011222333000181650010000000421123456786", "protocolo": "135260000000042",
 "recebido_em": "2026-11-19T16:26:32-03:00", "xml": "<nfeProc ...>", "qrcode": "https://...", "digest_value": "..."}
```

```json
// nuvem: o contexto inteiro, dentro do envelope
{"cnpj": "11222333000181", "uf": "SP", "ambiente": "1", "modelo": "65", "fuso": "-03:00",
 "certificado": {"pfx_base64": "MIIK...", "senha": "..."}, "csc": {"id": "1", "token": "..."},
 "ini": "[Identificacao]\n..."}
```

**Contingência** (`"tp_emis": "9"`, com `tpEmis=9` no INI): a nota é assinada aqui, sem
SEFAZ:

```json
{"situacao": "contingencia", "chave": "35261011222333000181650010000000439123456789",
 "xml": "<NFe Id=\"NFe3526...\">...", "qrcode": "https://...", "digest_value": "..."}
```

Guarde o `xml`: é ele que vai em `/v1/nfe/transmitir` quando a SEFAZ voltar (prazo: 24 h).

### `POST /v1/nfe/transmitir`

| Campo | Obrigatório | |
|---|---|---|
| `xml` | sim | o XML assinado em contingência, **exatamente como veio** (não refaça `dhEmi` nem a chave) |

Responde o resultado, com a mesma chave da contingência.

### `POST /v1/nfe/consultar`

| Campo | Obrigatório | |
|---|---|---|
| `chave` | sim | 44 dígitos |

```json
{"chave": "35261011222333000181650010000000421123456786"}
// → 200, a nota existe
{"situacao": "autorizada", "cstat": "100", "chave": "3526...", "protocolo": "...", ...}
// → 200, a SEFAZ não a tem: pode transmitir/emitir de novo
{"situacao": "nao_encontrada", "cstat": "217", "motivo": "NF-e não consta na base"}
```

### `POST /v1/nfe/cancelar`

| Campo | Obrigatório | |
|---|---|---|
| `chave` | sim | 44 dígitos |
| `protocolo` | sim | o da autorização |
| `justificativa` | sim | 15 a 255 caracteres |

```json
{"chave": "3526...", "protocolo": "135260000000042", "justificativa": "cliente desistiu da compra"}
// → 200
{"situacao": "cancelada", "cstat": "135", "motivo": "Evento registrado", "chave": "3526...", "protocolo": "135260000000099"}
```

NFC-e: em geral até 30 minutos depois da autorização (regra da SEFAZ de cada UF).

### `POST /v1/nfe/inutilizar`

Números que nunca viraram nota. Além do contexto: `ano` (dois dígitos, `26`), `serie`,
`numero_inicial`, `numero_final` (no máximo 1000 números) e `justificativa` (15 a 255).

Resposta: `situacao` `inutilizada` ou `rejeitada`, `cstat`, `motivo`, `protocolo`,
`recebido_em` e `xml`. Repetir a mesma faixa responde `inutilizada` (cStat 563 ou 206), às
vezes sem protocolo.

## 6. Configuração

| Rota | Nuvem | Local |
|---|---|---|
| `/v1/config/ler` | ✓ (só a lib) | ✓ (emitentes e lib), só da própria máquina |
| `/v1/config/lib` | ✓ | ✓, só da própria máquina |
| `/v1/config/emitente` | `404` | ✓, só da própria máquina |
| `/v1/config/emitente/remover` | `404` | ✓, só da própria máquina |
| `/v1/config/token` | `404` | ✓, só da própria máquina |

No desktop, tudo isso é feito pelas telas; as rotas servem para automatizar.

### `POST /v1/config/ler`

Corpo `{}`. Nada secreto volta: do certificado, só titular e validade; do CSC, se existe.

```json
// local → 200
{"modo": "local", "motor": "acbrlib", "token": "configurado",
 "emitentes": [{"cnpj": "11222333000181",
   "certificado": {"presente": true, "titular": "EMPRESA LTDA:11222333000181", "cnpj": "11222333000181",
                   "vence_em": "2027-03-01", "vencido": false},
   "csc": {"id": "1", "configurado": true}}],
 "lib": {"pacote_url": "", "sha256": "", "situacao": "parada", "mensagem": ""}}
```

`token`: `ambiente` (vale o do `.env`), `configurado` (trocado pela API) ou `ausente`. Na
nuvem, a resposta traz só `modo`, `motor` e `lib`.

### `POST /v1/config/emitente` (local)

Grava (ou atualiza) os segredos de um emitente: só o certificado A1 + senha e o CSC, pelo
CNPJ. UF, ambiente, modelo e fuso não se gravam (vêm em cada emissão; se vierem aqui, são
ignorados). O A1 é conferido na hora (senha, validade, CNPJ), com as mesmas recusas da emissão.

```json
{"cnpj": "11.222.333/0001-81",
 "certificado": {"pfx_base64": "MIIK...", "senha": "..."}, "csc": {"id": "1", "token": "..."}}
```

`certificado` ou `csc` ausentes (ou `null`) mantêm os guardados. Responde o mesmo que `ler`.
Fica em `configuracao.bin`, cifrado com a `ACBR_CHAVE_COFRE`.

### `POST /v1/config/emitente/remover` (local)

`{"cnpj": "11222333000181"}` → o mesmo que `ler`. Não cadastrado: `emitente_nao_configurado`.

### `POST /v1/config/token` (local)

`{}` gera um token; `{"token": "..."}` usa este (16+ caracteres, sem espaço, `#` nem acento).

```json
{"token": "4OJ5MclZGeMEL6VvcqJ9GdJYymtPIZDfminDqv1QhLg"}
```

É a única vez que ele aparece. O anterior deixa de valer **na hora**; atualize os PDVs.
Esqueceu? Apague `acesso.json` na pasta de dados e o do `.env` volta a valer.

### `POST /v1/config/lib`

`{"url": "...", "sha256": "..."}` baixa, confere (SHA-256 e cabeçalho ELF/MZ) e instala uma
ACBrLib, sem reiniciar. Só age quando **não há lib carregada**: com a que vem no
comunicador, responde `configuracao`, `lib_ja_carregada`.

```json
// → 200
{"ok": true, "lib": ".../lib/libacbrnfe64.so", "schemas": 201, "sha256": "...", "conferida": true,
 "mensagem": "ACBrLib instalada (201 Schemas).", "motor": "acbrlib"}
```

## 7. Saúde (`/health`)

`GET /health`, aberto (sem token), sem segredo:

```json
{"ok": true, "modo": "nuvem", "motor": "acbrlib", "lib": true, "simulador": false}
```

| `motor` | Significa |
|---|---|
| `acbrlib` | emite de verdade |
| `simulador` | `ACBR_SIMULADOR=1`: nada é emitido |
| `ausente` | sem a ACBrLib: responde `503` com `mensagem` (o `HEALTHCHECK` do Docker marca o container `unhealthy`) |

## 8. Erros

Um erro do comunicador vem como (cifrado na nuvem, quando o pedido chegou a ser aberto):

```json
{"erro": "sem_comunicacao", "motivo": "comunicador_ocupado", "mensagem": "texto para o operador"}
```

**O `erro` decide o que o cliente faz**; o `motivo` diz a providência; a `mensagem` é para
mostrar.

| HTTP | `erro` | Significa | O cliente faz |
|---|---|---|---|
| 503 | `sem_comunicacao` | a nota **não saiu** | contingência (`tp_emis: "9"`) ou tentar depois |
| 500 | `incerto` | a nota **pode ter saído** | **consultar antes de qualquer reenvio** |
| 422 | `documento_invalido` | schema, assinatura, INI ou campo fora do contrato | corrigir; repetir dá o mesmo erro |
| 500 | `configuracao` | certificado, CSC, lib ou emitente | nada sai até corrigir; **nunca** vira contingência |
| 400/409/413 | `sigilo` | o envelope não passou ([seção 3](#3-a-cifra-de-ponta-a-ponta-modo-nuvem)) | tratar como sem resposta |

| `erro` | `motivo` | Quando |
|---|---|---|
| `sem_comunicacao` | `sefaz_sem_comunicacao` | SEFAZ fora, ou serviço paralisado (cStat 108/109) |
| `sem_comunicacao` | `comunicador_ocupado` | outra nota ocupou a lib por mais de 8 s; nada foi enviado |
| `incerto` | `sefaz_sem_resposta` | a conexão caiu depois do envio |
| `incerto` | `falha_interna` | erro inesperado no comunicador (detalhe no log dele) |
| `documento_invalido` | `campos_invalidos` | campo fora do contrato ou JSON quebrado (só o nome do campo volta, nunca o valor) |
| `configuracao` | `certificado_ausente`, `senha_invalida`, `certificado_invalido`, `certificado_vencido`, `cnpj_diferente` | o A1 |
| `configuracao` | `dados_do_emitente_ausentes` | faltou `uf`, `ambiente` ou `modelo` (e, na nuvem, `cnpj`) |
| `configuracao` | `emitente_nao_configurado`, `emitente_nao_informado` | local: nenhum emitente, ou mais de um e sem `cnpj` |
| `configuracao` | `configuracao_ilegivel`, `cofre_sem_chave` | local: o cofre não abre com a `ACBR_CHAVE_COFRE` |
| `configuracao` | `acbrlib_ausente` | o comunicador está sem a lib |
| `configuracao` | `lib_ja_carregada`, `instalacao_falhou`, `instalacao_em_andamento` | `/v1/config/lib` |
| `documento_invalido` | `token_curto`, `token_invalido` | `/v1/config/token` |
| `sigilo` | `cifra_no_modo_local` | local recebeu um envelope cifrado; nada foi executado |

Respostas **sem** corpo fiscal (sem `erro`; trate como "sem resposta"):

| HTTP | Quando |
|---|---|
| 401 | token ausente ou errado (`{"detail": ...}`) |
| 403 | origem de navegador fora da lista; no local, `/v1/config/*` de fora da máquina |
| 404 | rota inexistente (na nuvem, `/v1/config/emitente`, `/remover`, `/token`) |
| 429 | nuvem: IP bloqueado por errar o token; `Retry-After` em segundos |

## 9. Limites e tempos

| | |
|---|---|
| Corpo da chamada | 8 MB (`ACBR_LIMITE_CORPO`); acima, `413` |
| Uma nota por vez | a ACBrLib atende uma chamada de cada vez; a seguinte espera até 8 s (`ACBR_ESPERA_TRAVA`), depois `comunicador_ocupado` |
| SEFAZ | 30 s de timeout na lib |
| **Timeout do cliente** | use **60 s** ou mais: menos que isso, o cliente desiste de uma nota que ainda pode ser enviada |
| Relógio (nuvem) | até 5 min de diferença entre cliente e comunicador |
| Séries | uma série por ponto de emissão: dois emissores na mesma série repetem número (539/613) |

## 10. Simulador

Com `ACBR_SIMULADOR=1`, o comunicador responde sem ir à SEFAZ, para desenvolver o cliente
sem lib nem certificado. Ele **nunca se passa pela SEFAZ**: o `motivo` diz
"SIMULADO — sem valor fiscal" e `ambiente: "1"` (produção) é recusado.

`POST /_simulador/modo` (com o token; corpo em claro, também na nuvem) troca o
comportamento, para testar cada caminho:

| `{"modo": ...}` | A próxima emissão |
|---|---|
| `online` | autorizada (cStat 100) |
| `fora` | `sem_comunicacao` (503) — teste a contingência |
| `lenta` | `incerto` (500) — teste a consulta antes do reenvio |
| `recusa` | rejeitada (cStat 778) |

## 11. Exemplos de cliente

**Local, com `curl`:**

```bash
TOKEN=...   # tela Acesso do desktop
curl -s http://127.0.0.1:8030/v1/nfe/emitir \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"ini": "[Identificacao]\ncNF=12345678\nmod=65\nserie=1\nnNF=42\n..."}'
```

**Local, em Python** (só a biblioteca padrão):

```python
import json, urllib.request

def chamar(rota, corpo, token, url="http://127.0.0.1:8030"):
    pedido = urllib.request.Request(url + rota, json.dumps(corpo).encode(), method="POST",
                                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(pedido, timeout=60) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as erro:  # 4xx/5xx também trazem JSON
        return erro.code, json.load(erro)
```

**Nuvem:** use [`exemplos/cliente_nuvem.py`](exemplos/cliente_nuvem.py) ou
[`exemplos/cliente-nuvem.mjs`](exemplos/cliente-nuvem.mjs) — fazem a cifra e devolvem
`(status, resposta aberta)`, ou levantam `SemResposta` quando não há resposta confiável.

```python
from cliente_nuvem import Comunicador, SemResposta

fiscal = Comunicador("https://fiscal.suaempresa.com.br", TOKEN, CHAVE_E2E)
try:
    status, nota = fiscal.chamar("/v1/nfe/emitir", {**contexto, "ini": ini})
except SemResposta:
    ...  # pode ter saído: consulte a chave antes de reenviar
```

**O fluxo de uma venda**, em qualquer linguagem:

```text
emitir(tp_emis "1")
├─ 200 situacao autorizada        → grava chave, protocolo e XML; imprime o DANFE
├─ 200 situacao rejeitada         → mostra o motivo; corrige e emite com o MESMO número
├─ 503 sem_comunicacao            → emitir(tp_emis "9", tpEmis=9 no INI) → DANFE de contingência
│                                   depois: transmitir(o mesmo XML)
├─ 500 incerto / sem resposta     → consultar(chave): autorizada → pronto; nao_encontrada → emitir de novo
└─ 500 configuracao               → avisa o operador; nada sai até corrigir
```

Os detalhes (contingência, duplicidade, números, recusas comuns do INI) estão em
[`INTEGRACAO.md`](INTEGRACAO.md).
