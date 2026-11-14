# Comunicador Fiscal — desktop

Um `.exe` só, sem instalador, para o computador da loja. Ele abre a tela de configuração e
sobe por baixo o comunicador ([`../server`](../server/README.md)), que emite as notas pela
ACBrLib. Sem internet, a nota sai em contingência offline ali mesmo.

- **Fechar a janela não encerra**: o comunicador continua no ícone da bandeja. Para encerrar,
  use "Sair" no menu da bandeja.
- **Iniciar com o Windows** (página Status ou bandeja): abre direto na bandeja, sem janela.
- Abrir o `.exe` de novo só mostra a janela que já está aberta.

## Telas

| Tela | O que faz |
|---|---|
| **Status** | Se o comunicador está no ar, se a ACBrLib está instalada, teste da SEFAZ e o registro do comunicador. |
| **Emitente** | Substitui o login: CNPJ, UF, ambiente, modelo, fuso, certificado A1 (.pfx + senha) e CSC. Ficam guardados e cifrados no comunicador; o A1 é conferido ao gravar. |
| **Acesso e conexão** | O endereço, o token e a chave que o PDV usa. Gera um token novo. Escolhe entre o comunicador **local** e um **remoto (Docker)**. |

No modo **remoto**, o desktop só configura um comunicador em Docker: informe a URL e o token
e a chave do `.env` dele. O comunicador local fica desligado.

## A biblioteca ACBr

Ela não vem junto (é distribuída pelo Projeto ACBr). Copie `ACBrNFe64.dll`, as DLLs que a
acompanham e a pasta `Schemas` para:

```
%APPDATA%\Comunicador Fiscal\servidor\lib
```

O botão "Abrir pasta", na tela Status, abre essa pasta. Depois clique em **Reiniciar**.

Na mesma pasta `servidor` ficam o `.env` (token e chave gerados na primeira vez), a
configuração guardada (`configuracao.bin`, cifrada), o log e os XML.

## O PDV

Chama `http://127.0.0.1:8030` (ou o IP deste PC, com "Aceitar PDVs da rede local") com o
token no cabeçalho `Authorization: Bearer` e o corpo cifrado com a chave, como está em
[`server/README.md`](../server/README.md#cifra-de-ponta-a-ponta). Com o emitente cadastrado,
basta enviar o documento:

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
npm test             # cifra, .env e preferências (node --test)
```

## Gerar o .exe

```bash
npm run build:tudo   # AcbrFiscal.exe (PyInstaller) + ComunicadorFiscal-<versão>.exe em dist/
npm run build        # só o desktop, reaproveitando o AcbrFiscal.exe já gerado
```

`build:servidor` roda `server/windows/gerar.ps1 -SoExe`, que cria `server/windows/.venv`
com as dependências travadas.
