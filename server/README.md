# Comunicador ACBrLib

Serviço independente que assina e transmite NFC-e/NF-e pela ACBrLib. A mesma API roda em
Docker, num serviço Windows (`.exe`) e dentro do desktop ([`../desktop`](../desktop/README.md)),
em um de dois modos (`ACBR_MODO`):

| | **nuvem** (padrão do Docker) | **local** (desktop, serviço Windows, Docker na loja) |
|---|---|---|
| Para quê | Docker num servidor da internet, falado só por API | O comunicador na máquina da loja |
| Autenticação | `Authorization: Bearer <token>` | `Authorization: Bearer <token>` |
| Corpo | Cifrado de ponta a ponta com a `ACBR_E2E_KEY` (o PDV tem a mesma) | JSON comum |
| Emitente (CNPJ, UF, A1, CSC) | Vem **em toda chamada**. Nunca é gravado | A1 e CSC guardados no comunicador, cifrados. O PDV manda UF, ambiente, modelo e o documento |
| `/v1/config/emitente`, `/token` | Não existem | Só atendem a própria máquina |
| XML das notas | Só na resposta; nada fica no disco | Só na resposta; nada fica no disco |
| Defesas extras | Não sobe com token fraco; bloqueio por tentativas | Configuração só da própria máquina |

Uso: [`docs/USO.md`](../docs/USO.md) · API completa: [`docs/API.md`](../docs/API.md) · decisões do cliente: [`docs/INTEGRACAO.md`](../docs/INTEGRACAO.md).

## Configuração

| Variável | Modo | Para quê |
|---|---|---|
| `ACBR_MODO` | — | `nuvem` ou `local`. Ausente: `nuvem` (o `.exe` e o desktop usam `local`). Outro valor: não sobe. |
| `ACBRLIB_TOKEN` | os dois | Toda rota `/v1` exige `Authorization: Bearer <token>`. Nuvem: no mínimo 32 caracteres, sem espaço, `#` nem acento, ou o comunicador não sobe. Local: é o token inicial (ver "Token"); sem ele e sem um token trocado, não sobe. |
| `ACBR_E2E_KEY` | nuvem | Obrigatória. 32 bytes em base64 (`openssl rand -base64 32`), a chave da cifra. O cliente usa a mesma. Não pode ser igual ao token. |
| `ACBR_TENTATIVAS` / `ACBR_BLOQUEIO_SEGUNDOS` | nuvem | O IP (IPv6: a rede /64 inteira) que errar o token 10 vezes (padrão) fica 900 s (padrão) recebendo 429, com `Retry-After`, mesmo com o token certo. Valor que não seja inteiro maior que zero: não sobe. |
| `FORWARDED_ALLOW_IPS` | nuvem | O IP do proxy HTTPS na frente do comunicador. Com ele, o bloqueio conta o IP real (`X-Forwarded-For`), e não bloqueia o proxy inteiro. |
| `ACBR_CHAVE_COFRE` | local | 32 bytes em base64: cifra os emitentes guardados. Ausente, vale a `ACBR_E2E_KEY` (instalações anteriores). Sem nenhuma das duas, ou inválida: não sobe. |
| `ACBR_CONFIG_REDES` | local | Quem chama `/v1/config/*`. Padrão: `127.0.0.1/32,::1/128`. IP ou rede inválida: não sobe. |
| `ACBR_ALLOWED_ORIGINS` | os dois | Origens de navegador, separadas por vírgula, sem curinga. Fora da lista: 403. Chamada sem `Origin` (programa nativo) segue pelo token. |
| `ACBR_SIMULADOR` | os dois | `1` simula a SEFAZ; nada é emitido de verdade. Nunca em produção. |
| `ACBR_DATA_DIR` | os dois | A lib instalada e o log; no local, também a configuração guardada e o token trocado. Docker: `/app/data`. |
| `ACBR_ESPERA_TRAVA` | os dois | Segundos que uma chamada espera outra nota terminar (padrão 8). Passou disso: `sem_comunicacao`, motivo `comunicador_ocupado` — nada foi enviado. |
| `ACBRLIB_PACOTE_URL` / `ACBRLIB_SO_SHA256` | os dois | Opcional: um pacote da ACBrLib para o comunicador baixar, conferir e instalar quando **não há lib nenhuma**. Ausentes: nada é baixado — a lib vem no repositório. |
| `ACBR_LIMITE_CORPO` | os dois | Tamanho máximo da chamada, em bytes (padrão 8 MB). Acima: 413. |

### Docker na nuvem

```bash
cp .env.example .env   # ACBR_MODO=nuvem, um token de 32+ caracteres e a ACBR_E2E_KEY
docker compose up -d --build
```

Ponha um proxy HTTPS na frente (nginx, Traefik, Caddy) e informe o IP dele em
`FORWARDED_ALLOW_IPS`. O token e a chave vão para o PDV/ERP, e só para ele.

A API fica na porta `ACBR_PORTA` (padrão 8030). **A ACBrLib vem no repositório**
([`embutida/`](embutida/LEIAME.md)) e o `docker build` a põe dentro da imagem: nada é baixado
para emitir. Para outra versão, troque a de `embutida/` ou monte uma em `./libs`. Licenças:
[`licencas/`](licencas/LEIA-ME.md). Detalhes em [`docs/INTEGRACAO.md`](../docs/INTEGRACAO.md#a-acbrlib). O `HEALTHCHECK` da imagem marca o container `unhealthy`
quando o `/health` responde 503 (lib ausente), sem reiniciá-lo.

### Docker na loja (modo local)

No `.env`: `ACBR_MODO=local`, o `ACBRLIB_TOKEN` e a `ACBR_CHAVE_COFRE`. As chamadas do
próprio host chegam ao container pela rede do Docker, e não por 127.0.0.1: publique a
porta só em `127.0.0.1` (`docker-compose.yml`) e libere a rede do Docker em
`ACBR_CONFIG_REDES` (por exemplo `127.0.0.1/32,::1/128,172.16.0.0/12`). Grave o emitente
com `POST /v1/config/emitente` a partir do host.

### Windows (.exe)

`AcbrFiscal-Setup.exe` pede administrador e, ao final, abre `AcbrFiscal.exe configurar`:
digite o token, ou pressione Enter para gerar, e anote-o para o PDV. A chave do cofre é
gerada sozinha. Tudo fica em `%PROGRAMDATA%\AcbrFiscal\.env` (`ACBR_MODO=local`), legível
só pelo serviço, pelos administradores e por quem configurou. O serviço sobe com o Windows
como `NETWORK SERVICE`, em `http://127.0.0.1:8030`.

Para trocar o token: `AcbrFiscal.exe configurar --forcar` (a chave do cofre fica, e os
emitentes guardados continuam valendo). Um `.env` de versão anterior, sem `ACBR_MODO`, sobe
como local, com a `ACBR_E2E_KEY` dele valendo como chave do cofre.

Para gerar o instalador, rode `windows\gerar.ps1` (Python 3.12 e Inno Setup 6): a
`ACBrNFe64.dll`, as dependências e os `Schemas` já estão em `windows\lib`, no repositório, e
vão junto. Para refazer a DLL a partir do código do ACBr: `windows\compilar-acbrlib.ps1
-Revisao 48608` (Lazarus 64 bits e SVN). As dependências
vão para `windows\.venv`, não para o Python do sistema. Com `-SoExe`, gera só o
`AcbrFiscal.exe`, sem instalador (é o que o desktop embute). A lib também é lida de
`<pasta de dados>\lib`, que vale primeiro.

O mesmo comunicador para Linux (o que o desktop AppImage embute): `linux/gerar.sh` →
`linux/saida/AcbrFiscal/AcbrFiscal`, com a lib de `embutida/` ao lado. No Linux, os dados ficam
em `~/.local/share/AcbrFiscal` (ou `ACBR_DATA_DIR`), com permissão só do dono, e não há tarefa
de inicialização (`instalar-tarefa` é do Windows).

Sem a lib, nos dois formatos, o serviço sobe, `/health` responde 503 e toda operação
responde `configuracao`.

## Operações

Todas são `POST` — na nuvem, com o corpo cifrado (ver "Cifra de ponta a ponta"):

| Rota | Campos, além do contexto |
|---|---|
| `/v1/status-servico` | |
| `/v1/nfe/emitir` | `ini`, `tp_emis` (`"1"` normal, `"9"` contingência: só assina) |
| `/v1/nfe/transmitir` | `xml` (o assinado em contingência, quando a SEFAZ voltar) |
| `/v1/nfe/consultar` | `chave` (44 dígitos) |
| `/v1/nfe/cancelar` | `chave`, `protocolo`, `justificativa` (15 a 255 caracteres). A resposta traz em `xml` o do **evento** |
| `/v1/nfe/inutilizar` | `ano` (dois dígitos), `serie`, `numero_inicial`, `numero_final` (até 1000 por chamada), `justificativa` (15 a 255) |

O contexto:

```json
{
  "uf": "SP", "cnpj": "11222333000181", "ambiente": "2", "modelo": "65", "fuso": "-03:00",
  "certificado": {"pfx_base64": "...", "senha": "..."},
  "csc": {"id": "1", "token": "..."}
}
```

`ambiente`: `"1"` produção, `"2"` homologação. `modelo`: `"65"` NFC-e, `"55"` NF-e. Valor
fora disso é recusado com `documento_invalido`, motivo `campos_invalidos`.

**Na nuvem**, o contexto vai inteiro em toda chamada: `cnpj`, `uf`, `ambiente` e `modelo`
sempre (sem padrão: esquecer o `ambiente` não pode virar homologação calada), e o
certificado e o CSC sempre que a lib precisar deles. Faltou algum dos quatro:
`configuracao`, motivo `dados_do_emitente_ausentes`. Nada disso é gravado: o certificado só passa pela
memória da lib, que o esquece ao fim da chamada.

**No local**, só os segredos ficam guardados (certificado A1 + senha e CSC, pelo CNPJ). A
chamada traz o resto: `uf`, `ambiente` e `modelo` sempre (faltou algum: `configuracao`,
motivo `dados_do_emitente_ausentes`), o `fuso`, e no INI o regime, CST e IBS/CBS. Sem
`cnpj`, vale o único emitente cadastrado; com mais de um, informe o `cnpj`. Certificado e
CSC vazios na chamada = os guardados. Sem emitente e sem certificado na chamada:
`configuracao`, motivo `emitente_nao_configurado`.

O certificado é conferido antes de chegar à lib. A recusa vem como `erro: configuracao`,
nunca como contingência, com `motivo`: `certificado_ausente`, `senha_invalida`,
`certificado_invalido`, `certificado_vencido` ou `cnpj_diferente`. O A1 da matriz vale
para a filial (mesma raiz de 8 posições).

`GET /health` é aberto e não traz segredo: `ok`, `modo`, `motor`, `lib`, `simulador`.

## Configuração pela API

| Rota | Modo | Corpo | Responde |
|---|---|---|---|
| `/v1/config/ler` | os dois | `{}` | `modo`, `motor` e o estado da lib. No local, também os emitentes **sem segredo** (titular e validade do A1, se há CSC) e a origem do token |
| `/v1/config/lib` | os dois | `url`, `sha256` (vazios: o pacote configurado) | baixa, confere e instala a ACBrLib, sem reiniciar. Com a lib já carregada: `lib_ja_carregada` |
| `/v1/config/emitente` | local | `cnpj`, `certificado`, `csc` (só os segredos; UF, ambiente, modelo e fuso vêm na emissão) | o mesmo de `ler` |
| `/v1/config/emitente/remover` | local | `cnpj` | o mesmo de `ler` |
| `/v1/config/token` | local | `token` (vazio: gera um) | `{"token": "..."}` — a única vez que ele aparece |

No local, todas as rotas `/v1/config/*` respondem 403 a quem não está em
`ACBR_CONFIG_REDES` (padrão: só a própria máquina). Um PDV da rede emite com o token,
mas não troca o certificado nem o token.

Em `/v1/config/emitente`, `certificado` ou `csc` ausentes (`null`) mantêm os guardados.
O A1 é conferido na hora de gravar (senha, validade, CNPJ), com as mesmas recusas da emissão.

Fica em `ACBR_DATA_DIR` (só no local):

- `configuracao.bin`: os emitentes, cifrados (AES-256-GCM) com uma chave derivada da
  `ACBR_CHAVE_COFRE`. Trocar a chave deixa o arquivo ilegível (`configuracao_ilegivel`):
  cadastre de novo. Sem chave nenhuma: `cofre_sem_chave`.
- `acesso.json`: o SHA-256 do token trocado pela API.

### Token

No local, o `ACBRLIB_TOKEN` do `.env` é o inicial. `/v1/config/token` grava um novo, que
passa a valer **no lugar** dele, na hora; o anterior recebe 401. Esqueceu o novo? Apague
`acesso.json` e o do `.env` volta a valer, sem perder os emitentes.

Na nuvem, vale só o `ACBRLIB_TOKEN` do `.env`; um `acesso.json` no volume é ignorado.
Para trocar, mude o `.env` e reinicie o container.

## O que fica gravado

- **Nuvem**: o log da lib (`data/log`) e a lib instalada (`data/lib`). Nenhum XML, nenhum
  certificado, nenhuma configuração de emitente. O XML assinado/autorizado volta na
  resposta, e guardá-lo é do cliente.
- **Local**: além disso, só a configuração guardada (`configuracao.bin`, cifrada) e o
  token trocado (`acesso.json`). O XML segue a mesma regra da nuvem: volta na resposta,
  e o comunicador não guarda cópia (`SalvarGer=0`).

## Erros do comunicador

O `motivo` de cada `erro` diz a providência. Os que não vêm da SEFAZ nem do certificado:

| `erro` | `motivo` | Quando |
|---|---|---|
| `sem_comunicacao` | `comunicador_ocupado` | outra nota ocupou a lib por mais de `ACBR_ESPERA_TRAVA`; nada foi enviado |
| `incerto` | `sefaz_sem_resposta` | a conexão caiu depois do envio: consulte antes de reenviar |
| `incerto` | `falha_interna` | erro inesperado no comunicador (detalhe no log) |
| `configuracao` | `dados_do_emitente_ausentes` | a chamada não trouxe `uf`, `ambiente` ou `modelo` (na nuvem, também o `cnpj`) |
| `configuracao` | `emitente_nao_configurado`, `emitente_nao_informado`, `configuracao_ilegivel`, `cofre_sem_chave` | local: ver "Configuração pela API" |
| `documento_invalido` | `campos_invalidos` | campo fora do contrato, ou JSON quebrado (só o nome do campo volta) |
| `sigilo` | `cifra_no_modo_local` | local: chegou um envelope cifrado (PDV configurado para a nuvem ou de versão anterior). Nada foi executado: mande JSON comum |

| Status sem corpo fiscal | Quando |
|---|---|
| 401 | token ausente ou errado |
| 403 | origem de navegador fora da lista; no local, `/v1/config/*` de fora de `ACBR_CONFIG_REDES` |
| 404 | na nuvem, `/v1/config/emitente`, `/remover` e `/token` |
| 429 | na nuvem, IP bloqueado por errar o token demais (`Retry-After` diz quando tentar) |

Durante o envio, falha de rede só vira `sem_comunicacao` quando a nota com certeza não
saiu (nome não resolve, conexão recusada); o resto é `incerto`.

## Cifra de ponta a ponta (modo nuvem)

AES-256-GCM. A partir da `ACBR_E2E_KEY` decodificada, deriva-se uma chave por sentido com
HKDF-SHA256, sem salt, 32 bytes, e `info` igual a `acbr-e2e-v1 pedido` ou
`acbr-e2e-v1 resposta`. Em cada envelope:

- `nonce`: 12 bytes aleatórios, em base64, nunca reaproveitados.
- `dados`: base64 de `texto cifrado + tag de 16 bytes`.
- Os dados autenticados (AAD) são o texto abaixo em UTF-8, com `\n` entre as partes.

**Pedido**, com o JSON da operação como texto claro:

```json
{"v": 1, "ts": 1794000000, "nonce": "...", "dados": "..."}
```

```text
AAD = acbr-e2e-v1 \n POST \n /v1/nfe/emitir \n <ts> \n <nonce do pedido>
```

`ts` é a hora atual em segundos Unix, com tolerância de 5 minutos.

**Resposta**, com o mesmo status HTTP do resultado:

```json
{"v": 1, "nonce": "...", "dados": "..."}
```

```text
AAD = acbr-e2e-v1 \n <status HTTP> \n <nonce do pedido>
```

Uma implementação de referência, em Python, está em [`app/sigilo.py`](app/sigilo.py)
(`selar_pedido` e `abrir_resposta`).

**Regras do cliente:**

- Só confie em resposta que abrir com a chave. Ela prova que veio do serviço, para este
  pedido e com este status.
- Resposta sem envelope (`erro: sigilo`, 401, 403, 429) não traz decisão fiscal, porque
  qualquer um no caminho poderia forjá-la. Trate como "sem resposta": depois de um envio,
  consulte antes de reenviar.
- Toda tentativa precisa de novo `nonce` e novo envelope. A repetição recebe 409.

| `motivo` de `erro: sigilo` | Causa |
|---|---|
| `envelope_invalido` | Corpo em claro ou fora do formato |
| `fora_da_janela` | Relógios com mais de 5 minutos de diferença |
| `nao_decifrou` | Chave diferente, ou dados alterados no caminho |
| `repetida` | Chamada já recebida |

**O que a cifra não cobre:**

- O token vai no cabeçalho; sem HTTPS, ele anda em claro. Sozinho, não abre nem monta
  uma chamada — mas use sempre o proxy HTTPS.
- A chave é fixa: quem a obtiver e tiver gravado o tráfego lê as chamadas antigas.
  Se ela vazar, troque-a e troque também a senha do certificado.
- A lista de `nonce` já vistos fica na memória: logo depois de o serviço reiniciar, uma
  chamada capturada nos últimos 5 minutos seria aceita uma vez mais. Na emissão, a
  duplicidade é tratada (consulta); um cancelamento repetido é recusado pela SEFAZ.
  O bloqueio por tentativas também zera ao reiniciar.
- Quem controla o servidor ou o PC do PDV lê o certificado na memória durante a chamada.
- Rota, horário e tamanho das chamadas continuam visíveis.

**No modo local não há cifra**: o token e o documento andam em claro entre o PDV e o
comunicador. Por isso o padrão é ouvir só `127.0.0.1`; aceitar PDVs da rede é para uma
rede da loja, confiável.

## Testes

```bash
pip install -r requirements-dev.txt && ruff check . && pytest tests
```
