# Comunicador ACBrLib

Serviço independente que assina e transmite NFC-e/NF-e pela ACBrLib. A mesma API
roda em Docker, num serviço Windows (`.exe`) e dentro do desktop ([`../desktop`](../desktop/README.md)).
As chamadas andam cifradas de ponta a ponta. Os dados do emitente (certificado A1, CSC,
UF, ambiente) podem chegar em cada chamada ou ficar guardados no comunicador, cifrados,
gravados pelas rotas `/v1/config/*` (o desktop faz isso por você).
Como integrar um sistema, contingência e instalação da lib: [`docs/INTEGRACAO.md`](../docs/INTEGRACAO.md).

## Configuração

| Variável | Para quê |
|---|---|
| `ACBRLIB_TOKEN` | O token inicial. Toda rota `/v1` exige `Authorization: Bearer <token>`. Depois de trocado por `/v1/config/token`, vale o novo (ver "Token"). |
| `ACBR_E2E_KEY` | Obrigatória. 32 bytes em base64 (`openssl rand -base64 32`), a chave da cifra. O cliente usa a mesma. Não pode ser igual ao token. |
| `ACBR_ALLOWED_ORIGINS` | Origens de navegador, separadas por vírgula, sem curinga. Fora da lista: 403. Chamada sem `Origin` (programa nativo) segue pelo token. |
| `ACBR_SIMULADOR` | `1` simula a SEFAZ; nada é emitido de verdade. Nunca em produção. |
| `ACBR_DATA_DIR` | Onde ficam a configuração guardada, o token trocado, o log e os XML. Docker: `/app/data`. |
| `ACBR_ESPERA_TRAVA` | Segundos que uma chamada espera outra nota terminar (padrão 8). Passou disso: `sem_comunicacao`, motivo `comunicador_ocupado` — nada foi enviado. |
| `ACBR_LIMITE_CORPO` | Tamanho máximo da chamada, em bytes (padrão 8 MB). Acima: 413. |

### Docker

```bash
cp .env.example .env   # preencha o token e a chave
docker compose up -d --build
```

A API fica na porta `ACBR_PORTA` (padrão 8030). A `libacbrnfe64.so` e a pasta
`Schemas` vão em `./libs`. O `HEALTHCHECK` da imagem marca o container `unhealthy`
quando o `/health` responde 503 (lib ausente), sem reiniciá-lo.

Para configurar o emitente sem montar as chamadas na mão, abra o desktop no modo
**Remoto (Docker)** com a URL, o token e a chave deste `.env`.

### Windows (.exe)

`AcbrFiscal-Setup.exe` pede administrador e, ao final, abre `AcbrFiscal.exe configurar`:
digite o token e a chave, ou pressione Enter para gerar, e anote os valores para o PDV.
Eles ficam em `%PROGRAMDATA%\AcbrFiscal\.env`, no mesmo formato do Docker, legível só
pelo serviço, pelos administradores e por quem configurou. O serviço sobe com o Windows
como `NETWORK SERVICE`, em `http://127.0.0.1:8030`.

Para trocar os valores: `AcbrFiscal.exe configurar --forcar`.

Para gerar o instalador, coloque `ACBrNFe64.dll`, as dependências e `Schemas` em
`windows\lib` e rode `windows\gerar.ps1` (Python 3.12 e Inno Setup 6). As dependências
vão para `windows\.venv`, não para o Python do sistema. Com `-SoExe`, gera só o
`AcbrFiscal.exe`, sem instalador (é o que o desktop embute). A lib também é lida de
`<pasta de dados>\lib`, que vale primeiro.

Sem a lib, nos dois formatos, o serviço sobe, `/health` responde 503 e toda operação
responde `configuracao`.

## Operações

Todas são `POST` com o corpo cifrado:

| Rota | Campos, além do contexto |
|---|---|
| `/v1/status-servico` | |
| `/v1/nfe/emitir` | `ini`, `tp_emis` (`"1"` normal, `"9"` contingência: só assina) |
| `/v1/nfe/transmitir` | `xml` (o assinado em contingência, quando a SEFAZ voltar) |
| `/v1/nfe/consultar` | `chave` (44 dígitos) |
| `/v1/nfe/cancelar` | `chave`, `protocolo`, `justificativa` (15 a 255 caracteres) |

Contexto, em toda chamada — todo ele opcional quando há emitente guardado:

```json
{
  "uf": "SP", "cnpj": "11222333000181", "ambiente": "2", "modelo": "65", "fuso": "-03:00",
  "certificado": {"pfx_base64": "...", "senha": "..."},
  "csc": {"id": "1", "token": "..."}
}
```

`ambiente`: `"1"` produção, `"2"` homologação. `modelo`: `"65"` NFC-e, `"55"` NF-e. Valor
fora disso é recusado com `documento_invalido`, motivo `campos_invalidos`.

**Com emitente guardado**, a chamada pode trazer só o documento (`{"ini": "..."}`). Sem
`cnpj`, vale o único emitente cadastrado; com mais de um, informe o `cnpj`. Campo que vem
na chamada vale sobre o guardado; certificado e CSC vazios na chamada = os guardados.
Sem emitente e sem dados na chamada: `configuracao`, motivo `emitente_nao_configurado`.

O certificado é conferido antes de chegar à lib. A recusa vem como `erro: configuracao`,
nunca como contingência, com `motivo`: `certificado_ausente`, `senha_invalida`,
`certificado_invalido`, `certificado_vencido` ou `cnpj_diferente`. O A1 da matriz vale
para a filial (mesma raiz de 8 posições).

`GET /health` é aberto e não traz segredo.

## Configuração guardada

Também `POST` e cifradas, com o mesmo token:

| Rota | Corpo | Responde |
|---|---|---|
| `/v1/config/ler` | `{}` | emitentes **sem segredo** (titular e validade do A1, se há CSC) e a origem do token |
| `/v1/config/emitente` | `cnpj`, `uf`, `ambiente`, `modelo`, `fuso`, `certificado`, `csc` | o mesmo de `ler` |
| `/v1/config/emitente/remover` | `cnpj` | o mesmo de `ler` |
| `/v1/config/token` | `token` (vazio: gera um) | `{"token": "..."}` — a única vez que ele aparece |

Em `/v1/config/emitente`, `certificado` ou `csc` ausentes (`null`) mantêm os guardados.
O A1 é conferido na hora de gravar (senha, validade, CNPJ), com as mesmas recusas da emissão.

Fica em `ACBR_DATA_DIR`:

- `configuracao.bin`: os emitentes, cifrados (AES-256-GCM) com uma chave derivada da
  `ACBR_E2E_KEY`. Trocar a chave deixa o arquivo ilegível (`configuracao_ilegivel`):
  cadastre de novo.
- `acesso.json`: o SHA-256 do token trocado pela API.

### Token

O `ACBRLIB_TOKEN` do `.env` é o inicial. `/v1/config/token` grava um novo, que passa a
valer **no lugar** dele, na hora; o anterior recebe 401. Esqueceu o novo? Apague
`acesso.json` e o do `.env` volta a valer, sem perder os emitentes. O mesmo token dá
acesso às notas e à configuração.

## O que fica gravado

Além da configuração guardada: o log da lib (`data/log`) e o XML de cada nota
(`data/xml`, `SalvarGer=1` no `config/ACBrLib.ini`) — cópia de segurança; a fonte da
verdade continua sendo o cliente.

## Erros do comunicador

O `motivo` de cada `erro` diz a providência. Os que não vêm da SEFAZ nem do certificado:

| `erro` | `motivo` | Quando |
|---|---|---|
| `sem_comunicacao` | `comunicador_ocupado` | outra nota ocupou a lib por mais de `ACBR_ESPERA_TRAVA`; nada foi enviado |
| `incerto` | `sefaz_sem_resposta` | a conexão caiu depois do envio: consulte antes de reenviar |
| `incerto` | `falha_interna` | erro inesperado no comunicador (detalhe no log) |
| `configuracao` | `emitente_nao_configurado`, `emitente_nao_informado`, `configuracao_ilegivel` | ver "Configuração guardada" |
| `documento_invalido` | `campos_invalidos` | campo fora do contrato (só o nome do campo volta) |

Durante o envio, falha de rede só vira `sem_comunicacao` quando a nota com certeza não
saiu (nome não resolve, conexão recusada); o resto é `incerto`.

## Cifra de ponta a ponta

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

**Regras do cliente:**

- Só confie em resposta que abrir com a chave. Ela prova que veio do serviço, para este
  pedido e com este status.
- Resposta sem envelope (`erro: sigilo`, 401, 403) não traz decisão fiscal, porque
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

- O token vai em claro no cabeçalho, mas sozinho não abre nem monta uma chamada.
- A chave é fixa: quem a obtiver e tiver gravado o tráfego lê as chamadas antigas.
  Se ela vazar, troque-a e troque também a senha do certificado.
- A lista de `nonce` já vistos fica na memória: logo depois de o serviço reiniciar, uma
  chamada capturada nos últimos 5 minutos seria aceita uma vez mais. Na emissão, a
  duplicidade é tratada (consulta); um cancelamento repetido é recusado pela SEFAZ.
- Quem controla o PC do PDV ou do serviço lê o certificado na memória.
- Rota, horário e tamanho das chamadas continuam visíveis.

## Testes

```bash
pip install -r requirements-dev.txt && ruff check . && pytest tests
```
