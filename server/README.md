# Comunicador ACBrLib

Serviço independente que assina e transmite NFC-e/NF-e pela ACBrLib. A mesma API
roda em Docker e em um `.exe` para Windows. Não guarda certificado nem nota: o
certificado e os dados fiscais chegam em cada chamada, cifrados de ponta a ponta.
Arquitetura e contingência: [`docs/FISCAL_ACBRLIB.md`](../docs/FISCAL_ACBRLIB.md).

## Configuração

| Variável | Para quê |
|---|---|
| `ACBRLIB_TOKEN` | Obrigatório. Toda rota `/v1` exige `Authorization: Bearer <token>`. |
| `ACBR_E2E_KEY` | Obrigatória. 32 bytes em base64 (`openssl rand -base64 32`), a chave da cifra. O cliente usa a mesma. Não pode ser igual ao token. |
| `ACBR_ALLOWED_ORIGINS` | Origens de navegador, separadas por vírgula, sem curinga. Fora da lista: 403. Chamada sem `Origin` (programa nativo) segue pelo token. |
| `ACBR_SIMULADOR` | `1` simula a SEFAZ; nada é emitido de verdade. Nunca em produção. |

### Docker

```bash
cp .env.example .env   # preencha o token e a chave
docker compose up -d --build
```

A API fica na porta `ACBR_PORTA` (padrão 8030). A `libacbrnfe64.so` e a pasta
`Schemas` vão em `./libs`.

### Windows (.exe)

`AcbrFiscal-Setup.exe` pede administrador e, ao final, abre `AcbrFiscal.exe configurar`:
digite o token e a chave, ou pressione Enter para gerar, e anote os valores para o PDV.
Eles ficam em `%PROGRAMDATA%\AcbrFiscal\.env`, no mesmo formato do Docker, legível só
pelo serviço, pelos administradores e por quem configurou. O serviço sobe com o Windows
como `NETWORK SERVICE`, em `http://127.0.0.1:8030`.

Para trocar os valores: `AcbrFiscal.exe configurar --forcar`.

Para gerar o instalador, coloque `ACBrNFe64.dll`, as dependências e `Schemas` em
`windows\lib` e rode `windows\gerar.ps1` (Python 3.12 e Inno Setup 6).

Sem a lib, nos dois formatos, o serviço sobe, `/health` responde 503 e toda operação
responde `configuracao`.

## Operações

Todas são `POST` com o corpo cifrado:

| Rota | Campos, além do contexto |
|---|---|
| `/v1/status-servico` | |
| `/v1/nfe/emitir` | `ini`, `tp_emis` (`"1"` normal, `"9"` contingência: só assina) |
| `/v1/nfe/transmitir` | `xml` |
| `/v1/nfe/consultar` | `chave` |
| `/v1/nfe/cancelar` | `chave`, `protocolo`, `justificativa` |

Contexto, em toda chamada:

```json
{
  "uf": "SP", "cnpj": "11222333000181", "ambiente": "2", "modelo": "65", "fuso": "-03:00",
  "certificado": {"pfx_base64": "...", "senha": "..."},
  "csc": {"id": "1", "token": "..."}
}
```

O certificado é conferido antes de chegar à lib. A recusa vem como `erro: configuracao`,
nunca como contingência, com `motivo`: `certificado_ausente`, `senha_invalida`,
`certificado_invalido`, `certificado_vencido` ou `cnpj_diferente`. O A1 da matriz vale
para a filial (mesma raiz de 8 posições).

`GET /health` é aberto e não traz segredo.

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
- Quem controla o PC do PDV ou do serviço lê o certificado na memória.
- Rota, horário e tamanho das chamadas continuam visíveis.

## Testes

```bash
pip install -r requirements.txt pytest httpx && pytest tests
```
