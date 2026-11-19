# Comunicador Fiscal ACBr

Emite NFC-e/NF-e pela ACBrLib. A mesma API roda em dois modos (`ACBR_MODO`):

| Modo | Onde | Como o PDV/ERP chama |
|---|---|---|
| **nuvem** | [`server/`](server/README.md) — Docker num servidor da internet | Só por API: token **e** corpo cifrado com a chave do `.env`. O emitente (certificado A1, senha, CSC, UF, CNPJ) vai em toda chamada e nunca é gravado; o XML volta na resposta e não fica no servidor. Não sobe com token fraco; bloqueia quem erra o token. |
| **local** | [`desktop/`](desktop/README.md) — `.exe` portátil (Windows) ou AppImage (Linux); [`server/windows`](server/README.md#windows-exe) — serviço Windows; ou o Docker na loja | Só o token. O XML também só volta na resposta. O emitente é configurado nesta máquina (tela do desktop) e o PDV manda só o documento. Funciona sem internet, com a contingência offline local. A configuração só se altera da própria máquina. |

A ACBrLib (Linux e Windows) vem neste repositório, com as licenças em
[`server/licencas`](server/licencas/LEIA-ME.md): nada é baixado para emitir.

| GitHub Actions | O que gera |
|---|---|
| [`ci.yml`](.github/workflows/ci.yml) | testes do servidor e do desktop; a imagem sobe com a lib |
| [`imagem.yml`](.github/workflows/imagem.yml) | imagem Docker **Linux** (`linux/amd64`) em `ghcr.io/<dono>/comunicador-fiscal` |
| [`desktop.yml`](.github/workflows/desktop.yml) | desktop **Windows** (`.exe`) e **Linux** (AppImage), no Release da tag |

Uma tag `vX.Y.Z` dispara a imagem e o desktop juntos.

## Documentação

| | Para quem |
|---|---|
| [**Guia de uso**](docs/USO.md) | quem instala e opera: desktop Windows/Linux, Docker na nuvem e na loja, homologação, problemas comuns |
| [**Referência da API**](docs/API.md) | quem programa o PDV/ERP: rotas, campos, respostas, erros, a cifra da nuvem e [clientes de exemplo](docs/exemplos) |
| [Integração](docs/INTEGRACAO.md) | as decisões do cliente: contingência, consulta, duplicidade, recusas do INI |
| [Comunicador (server)](server/README.md) · [Desktop](desktop/README.md) | variáveis de ambiente, build e detalhes de cada parte |
