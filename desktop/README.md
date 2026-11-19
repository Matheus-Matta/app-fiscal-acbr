# Comunicador Fiscal — desktop

Um arquivo só, sem instalador, para o computador da loja — **Windows** (`.exe` portátil) ou
**Linux** (AppImage). Ele abre a tela de configuração e
sobe por baixo o comunicador ([`../server`](../server/README.md)) no **modo local**: o
emitente é configurado aqui, e o PDV chama só com o token. Sem internet, a nota sai em
contingência offline ali mesmo.

O Docker na nuvem não se configura por aqui: lá o emitente vai em cada chamada do PDV/ERP
([`docs/INTEGRACAO.md`](../docs/INTEGRACAO.md#qual-comunicador-o-cliente-chama)).

| | Windows x64 | Linux x64 |
|---|---|---|
| Arquivo | `ComunicadorFiscal-<versão>.exe` | `ComunicadorFiscal-<versão>-x86_64.AppImage` |
| ACBrLib dentro | `server/windows/lib` (DLL + OpenSSL + libxml2) | `server/embutida` (a mesma da imagem Docker) |
| Precisa no sistema | nada | glibc 2.34+ (Ubuntu 22.04+, Debian 12+), `libxml2`, `libssl3` e, para abrir o AppImage, `libfuse2` (`libfuse2t64` no Ubuntu 24.04+) |
| Iniciar com o sistema | item de login do Windows | `~/.config/autostart/comunicador-fiscal.desktop` |
| Dados | `%APPDATA%\Comunicador Fiscal\servidor` | `~/.config/Comunicador Fiscal/servidor` |

No Linux, o comunicador cria sozinho o atalho `libxml2.so` que a ACBrLib procura (sem ele a lib
carrega, mas a assinatura falha) e se reabre com ele. A assinatura foi conferida tanto com a
libxml2 `.so.2` (Ubuntu 22.04/24.04, Debian 12) quanto com a `.so.16` (Ubuntu 26.04).
No GNOME, o ícone da bandeja precisa da extensão AppIndicator.

Os dois são gerados pelo GitHub Actions ([`desktop.yml`](../.github/workflows/desktop.yml)): numa
tag `vX.Y.Z` eles vão para o Release, com o `SHA256SUMS.txt`.

- **Fechar a janela não encerra**: o comunicador continua no ícone da bandeja. Para encerrar,
  use "Sair" no menu da bandeja.
- **Iniciar com o Windows** (página Status ou bandeja): abre direto na bandeja, sem janela.
- Abrir o `.exe` de novo só mostra a janela que já está aberta.

## Telas

| Tela | O que faz |
|---|---|
| **Status** | Se o comunicador está no ar, se a ACBrLib está instalada, teste da SEFAZ e o registro do comunicador. |
| **Emitente** | Substitui o login: CNPJ, UF, ambiente, modelo, fuso, certificado A1 (.pfx + senha) e CSC. Ficam guardados e cifrados no comunicador; o A1 é conferido ao gravar. |
| **Acesso e conexão** | O endereço e o token que o PDV usa. Gera um token novo. Porta, PDVs da rede local, origens de navegador e SEFAZ simulada. |

O emitente, o certificado e o token só se alteram neste computador: um PDV da rede emite,
mas recebe 403 se tentar reconfigurar.

## A biblioteca ACBr

**Ela já vem dentro do `.exe`** (`server\windows\lib`, no repositório): nada é baixado.
Licenças: [`server/licencas`](../server/licencas/LEIA-ME.md). Para usar outra versão sem
gerar o `.exe` de novo, na tela **Status**, cartão "Biblioteca ACBr" (aparece quando falta a lib):

- **Baixar e instalar**: o endereço do pacote (`.zip`/`.tar.gz`, link do MediaFire aceito) e
  o SHA-256 da lib. Fica gravado no `.env`: se a lib sumir, ele a reinstala ao abrir.
- **Escolher pacote no computador…**: um pacote já baixado.

O pacote de Windows tem `ACBrNFe64.dll`, as DLLs que a acompanham e `Schemas/NFe`. Uma lib
instalada assim fica em `%APPDATA%\Comunicador Fiscal\servidor\lib` ("Abrir pasta") e vale
antes da que vem no `.exe`.

Na mesma pasta `servidor` ficam o `.env` (`ACBR_MODO=local`, o token e a chave do cofre,
gerados na primeira vez), a configuração guardada (`configuracao.bin`, cifrada) e o log. O XML de
cada nota só volta na resposta ao PDV: o desktop não guarda cópia.

Ao abrir, uma versão anterior é migrada sozinha: a `ACBR_E2E_KEY` dela vira a chave do cofre, e os emitentes já cadastrados continuam valendo. O antigo modo "remoto" deixa de
existir.

## O PDV

Chama `http://127.0.0.1:8030` (ou o IP deste PC, com "Aceitar PDVs da rede local") com o
token no cabeçalho `Authorization: Bearer` e o corpo em JSON comum, sem cifra. Com o
emitente cadastrado, basta enviar o documento:

```json
POST /v1/nfe/emitir   {"ini": "..."}
```

Se a SEFAZ estiver fora (`erro: sem_comunicacao`), o PDV pede de novo com `"tp_emis": "9"`:
a nota é assinada em contingência offline aqui. Quando a SEFAZ voltar, o PDV envia o XML
assinado em `/v1/nfe/transmitir`.

## Desenvolvimento

```bash
npm install
npm run dev          # Vite + Electron, com o servico.py do repositório (precisa do Python e do server/requirements.txt)
npm test             # cliente, .env e preferências (node --test)
```

## Gerar

No sistema de destino (o build de um não sai no outro):

```bash
npm run build:tudo   # comunicador (PyInstaller) + desktop em dist/ (.exe no Windows, AppImage no Linux)
npm run build        # só o desktop, reaproveitando o comunicador já gerado
```

`build:servidor` roda, no Windows, `server/windows/gerar.ps1 -SoExe` (→ `server/windows/saida`)
e, no Linux, `server/linux/gerar.sh` (→ `server/linux/saida`; gere no Ubuntu 22.04 para rodar
nas distribuições mais novas também). Cada um cria o seu `.venv` com as dependências travadas
e põe a ACBrLib do repositório ao lado do comunicador.
