# Comunicador Fiscal ACBr

Emite NFC-e/NF-e pela ACBrLib. A mesma API, com token, origens permitidas e chamadas
cifradas de ponta a ponta, roda de três jeitos:

| Onde | Para quê |
|---|---|
| [`server/`](server/README.md) — Docker | Servidor da loja ou nuvem. Configurado pela API (`/v1/config/*`), com o token inicial no `.env`. |
| [`server/windows`](server/README.md#windows-exe) — serviço Windows | O mesmo, instalado como tarefa do Windows (Inno Setup). |
| [`desktop/`](desktop/README.md) — `.exe` portátil | O PC da loja sem depender de internet: tela de configuração (emitente, certificado, CSC, token), comunicador embutido, fica na bandeja e faz a contingência offline local. Também configura um Docker remoto. |

Integração com o backend StarChef: [`docs/FISCAL_ACBRLIB.md`](docs/FISCAL_ACBRLIB.md).
