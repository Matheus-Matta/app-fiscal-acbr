# Guia de uso do Comunicador Fiscal

Como instalar, configurar e operar o comunicador que emite NFC-e e NF-e pela ACBrLib. Para
programar o PDV/ERP que chama o comunicador, veja a [referência da API](API.md) e o guia
de [integração](INTEGRACAO.md).

- [1. Qual usar](#1-qual-usar)
- [2. Desktop no Windows](#2-desktop-no-windows)
- [3. Desktop no Linux](#3-desktop-no-linux)
- [4. Configurar o desktop](#4-configurar-o-desktop)
- [5. Docker na nuvem](#5-docker-na-nuvem)
- [6. Docker na loja (modo local)](#6-docker-na-loja-modo-local)
- [7. Serviço Windows (sem tela)](#7-serviço-windows-sem-tela)
- [8. De homologação para produção](#8-de-homologação-para-produção)
- [9. No dia a dia](#9-no-dia-a-dia)
- [10. Problemas comuns](#10-problemas-comuns)
- [11. Onde fica cada coisa](#11-onde-fica-cada-coisa)
- [12. Checklist de segurança](#12-checklist-de-segurança)

---

## 1. Qual usar

| Situação | Use | Modo |
|---|---|---|
| Um PDV/ERP na nuvem emite para várias empresas; o certificado fica com o ERP | [Docker na nuvem](#5-docker-na-nuvem) | nuvem |
| O PC do caixa emite, e precisa funcionar **sem internet** (contingência offline) | [Desktop](#2-desktop-no-windows) (Windows ou Linux) | local |
| Um servidor da loja atende vários caixas, sem tela | [Docker na loja](#6-docker-na-loja-modo-local) ou [serviço Windows](#7-serviço-windows-sem-tela) | local |

A diferença, em uma frase: **na nuvem**, o PDV/ERP guarda o certificado e manda tudo em
cada chamada, cifrado; **no local**, o certificado fica configurado no comunicador e o PDV
manda só a nota, com o token. Em nenhum dos dois o comunicador guarda o XML das notas: ele
volta na resposta, e guardá-lo é do PDV/ERP.

A ACBrLib (Projeto ACBr, LGPL) já vem dentro de tudo: nada é baixado para emitir.

## 2. Desktop no Windows

**Requisitos:** Windows 10 ou 11, 64 bits.

1. Baixe `ComunicadorFiscal-<versão>.exe` na página **Releases** do repositório (confira o
   `SHA256SUMS.txt`, se quiser).
2. Abra. É portátil: não instala nada. Na primeira vez, o Windows pode mostrar "O Windows
   protegeu o computador" (o arquivo não é assinado): **Mais informações → Executar assim
   mesmo**.
3. Siga a [configuração](#4-configurar-o-desktop).

Fechar a janela **não encerra**: o comunicador continua no ícone da bandeja, perto do
relógio, emitindo para o PDV. Para encerrar: botão direito no ícone → **Sair**. Abrir o
`.exe` de novo só mostra a janela que já está aberta.

**Atualizar:** feche pelo **Sair**, troque o `.exe` pelo novo e abra. A configuração fica
em `%APPDATA%\Comunicador Fiscal` e continua valendo.

## 3. Desktop no Linux

**Requisitos:** Linux x64 com glibc 2.34 ou mais nova (Ubuntu 22.04+, Debian 12+, Mint 21+,
Fedora 36+), com `libxml2` e `libssl3` (já vêm na maioria) e, para abrir um AppImage, a FUSE 2:

```bash
sudo apt install libfuse2        # Ubuntu 22.04 / Debian
sudo apt install libfuse2t64     # Ubuntu 24.04 ou mais novo
```

1. Baixe `ComunicadorFiscal-<versão>-x86_64.AppImage` na página **Releases**.
2. Dê permissão de execução e abra:

   ```bash
   chmod +x ComunicadorFiscal-*.AppImage
   ./ComunicadorFiscal-*.AppImage
   ```

3. Siga a [configuração](#4-configurar-o-desktop).

O ícone fica na bandeja do sistema. No **GNOME** (Ubuntu), ela só aparece com a extensão
*AppIndicator* (no Ubuntu já vem ativa). **Iniciar com o sistema** cria
`~/.config/autostart/comunicador-fiscal.desktop`: mantenha o AppImage no mesmo lugar depois
de ligar a opção.

**Se a janela não abrir** no Ubuntu 24.04+ (erro sobre o *sandbox*), abra com
`./ComunicadorFiscal-*.AppImage --no-sandbox`. É uma restrição do AppArmor a AppImages com
Electron.

## 4. Configurar o desktop

São três telas, no menu à esquerda.

### Emitente — a primeira vez

Substitui o login: é aqui que o comunicador aprende quem emite.

| Campo | |
|---|---|
| CNPJ, UF | da empresa |
| Ambiente | **Homologação** para testar; **Produção** só depois do [roteiro](#8-de-homologação-para-produção) |
| Modelo | NFC-e (65) ou NF-e (55) |
| Fuso | o da loja: `-03:00` (Brasília); `-04:00` no AM, MT, MS, RO e RR; `-05:00` no AC |
| Certificado A1 | o arquivo `.pfx` e a senha. É conferido na hora: senha, validade e CNPJ (o da matriz vale para as filiais) |
| CSC | o ID e o código do CSC, gerados no portal da SEFAZ da UF (NFC-e). Homologação e produção têm CSCs diferentes |

Tudo fica guardado cifrado no próprio computador. Mais de uma empresa? Cadastre cada CNPJ;
o PDV informa o `cnpj` em cada chamada.

### Acesso e conexão — o que vai para o PDV

- **Endereço**: `http://127.0.0.1:8030` (o PDV no mesmo computador) ou, com **Aceitar PDVs
  da rede local** ligado, `http://<IP deste PC>:8030`.
- **Token**: copie e configure no PDV (cabeçalho `Authorization: Bearer`).
- **Gerar novo token**: o antigo para de funcionar na hora; atualize todos os PDVs.
- **Origens de navegador**: só se o PDV for uma página web (ex.: `https://pdv.minhaloja.com.br`).
- **SEFAZ simulada**: para desenvolver/testar sem SEFAZ. **Desligue antes de usar na loja.**

Com a rede local ligada, o Windows (ou o `ufw`, no Linux) pode pedir para liberar a porta.
Os PDVs da rede **emitem**, mas não conseguem trocar certificado nem token: isso só se faz
neste computador.

### Status

- **Comunicador**: se está ativo e se a ACBrLib está carregada ("Pronto para emitir").
- **SEFAZ → Testar comunicação**: consulta o serviço da SEFAZ com o emitente e o certificado
  configurados. É o teste final da configuração.
- **Iniciar com o Windows / com o sistema**: abre direto na bandeja ao ligar o PC.
- **Registro do comunicador**: o log, para diagnóstico.

## 5. Docker na nuvem

**Requisitos:** um servidor Linux x64 com Docker e um domínio com HTTPS.

### 5.1 O `.env`

```bash
git clone <este repositório> && cd fiscal_acbr/server
cp .env.example .env
openssl rand -base64 48 | tr -d '\n/+='; echo     # → ACBRLIB_TOKEN
openssl rand -base64 32                           # → ACBR_E2E_KEY
```

```ini
ACBR_MODO=nuvem
ACBRLIB_TOKEN=<o primeiro valor: 32+ caracteres>
ACBR_E2E_KEY=<o segundo valor>
ACBR_SIMULADOR=0
```

Sem token forte ou sem a chave, o comunicador **não sobe** (e diz o porquê no log).

### 5.2 Subir

Com o código: `docker compose up -d --build`. Ou com a imagem publicada pelo GitHub Actions
(`ghcr.io/<dono>/comunicador-fiscal`, a ACBrLib já dentro):

```yaml
services:
  acbr:
    image: ghcr.io/<dono>/comunicador-fiscal:latest
    env_file: .env
    environment:
      FORWARDED_ALLOW_IPS: "*"   # seguro só porque a porta 8030 NÃO é publicada (ver abaixo)
    restart: unless-stopped
    # sem "ports": só o proxy alcança o comunicador

  proxy:
    image: caddy:2
    ports: ["80:80", "443:443"]
    command: caddy reverse-proxy --from fiscal.suaempresa.com.br --to acbr:8030
    volumes: ["caddy:/data"]   # o certificado HTTPS; sem isto, um novo a cada reinício
    restart: unless-stopped

volumes:
  caddy:
```

O Caddy tira e renova o certificado HTTPS sozinho. Com outro proxy (nginx, Traefik), o
princípio é o mesmo:

- **Não publique a porta 8030** para a internet: só o proxy deve alcançá-la.
- `FORWARDED_ALLOW_IPS` diz de quem o comunicador aceita o `X-Forwarded-For` (o IP real do
  cliente, que o bloqueio por tentativas usa). Com a porta fechada, `*` é seguro; com ela
  aberta, use o IP do proxy — senão qualquer um forja o próprio IP e escapa do bloqueio.

### 5.3 Conferir e entregar

```bash
curl https://fiscal.suaempresa.com.br/health
# {"ok": true, "modo": "nuvem", "motor": "acbrlib", "lib": true, "simulador": false}
```

Entregue ao time do PDV/ERP, por um canal seguro: a **URL**, o **token** e a **chave**. Eles
mandam o certificado A1 e o CSC de cada empresa em toda chamada
([API, seção 4](API.md#4-o-contexto-do-emitente)); nada disso fica no servidor.

**Trocar o token ou a chave:** edite o `.env` e `docker compose up -d`. Atualize os clientes
ao mesmo tempo. Se a chave vazar, troque-a **e** a senha dos certificados.

**Atualizar:** `docker compose pull && docker compose up -d` (imagem) ou
`git pull && docker compose up -d --build` (código). Não há dado a migrar: na nuvem, o volume
`data/` só tem o log.

## 6. Docker na loja (modo local)

Um servidor na loja, sem tela, atendendo os caixas da rede.

```ini
ACBR_MODO=local
ACBRLIB_TOKEN=<openssl rand -base64 32>
ACBR_CHAVE_COFRE=<openssl rand -base64 32>
# As chamadas do próprio host chegam ao container pela rede do Docker:
ACBR_CONFIG_REDES=127.0.0.1/32,::1/128,172.16.0.0/12
```

No `docker-compose.yml`, publique a porta só para a máquina se só ela chama
(`"127.0.0.1:8030:8030"`), ou em todas as interfaces se os caixas da rede chamam — nesse
caso, deixe a configuração (`/v1/config/*`) só para o host, como acima.

O emitente se grava pela API, **do próprio servidor**:

```bash
curl -s http://127.0.0.1:8030/v1/config/emitente -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d @- <<EOF
{"cnpj": "11222333000181", "uf": "SP", "ambiente": "2", "modelo": "65", "fuso": "-03:00",
 "certificado": {"pfx_base64": "$(base64 -w0 a1.pfx)", "senha": "..."},
 "csc": {"id": "1", "token": "..."}}
EOF
```

**Guarde o `.env` e a pasta `data/`**: a `ACBR_CHAVE_COFRE` abre `data/configuracao.bin`;
sem ela, o emitente precisa ser cadastrado de novo.

## 7. Serviço Windows (sem tela)

Para um servidor Windows sem o desktop. O instalador não sai pelo GitHub Actions: gere-o
com `server\windows\gerar.ps1` (Python 3.12 e Inno Setup 6), que já leva a ACBrLib.

`AcbrFiscal-Setup.exe` pede administrador e, ao final, pergunta o token (Enter gera um):
anote-o para os PDVs. O serviço sobe com o Windows em `http://127.0.0.1:8030`, no modo local.
Configure o emitente pela API, como no [Docker na loja](#6-docker-na-loja-modo-local).

```bat
AcbrFiscal.exe configurar --forcar    :: troca o token (a chave do cofre e os emitentes ficam)
```

## 8. De homologação para produção

Teste tudo em **homologação** (ambiente 2), com o A1 e o CSC de homologação:

1. `GET /health` com `lib: true` (ou "Pronto para emitir" no desktop).
2. **Testar comunicação** com a SEFAZ: `online`.
3. Venda → NFC-e autorizada (cStat 100), DANFE com protocolo.
4. Sem internet → contingência → DANFE de contingência.
5. Internet de volta → a contingência é transmitida e autorizada, com a mesma chave.
6. Cancelar uma nota autorizada.
7. Dois caixas emitindo ao mesmo tempo → números diferentes.

Em homologação, o primeiro item da NFC-e precisa ser "NOTA FISCAL EMITIDA EM AMBIENTE DE
HOMOLOGACAO - SEM VALOR FISCAL" (rejeição 373).

Para produção: troque o **ambiente** para 1, o **CSC** pelo de produção, desligue a **SEFAZ
simulada** e confira o **próximo número** da série (notas de homologação não ocupam números
de produção).

## 9. No dia a dia

| Situação | O que acontece |
|---|---|
| A SEFAZ cai | o PDV recebe `sem_comunicacao` e emite em **contingência**: a nota é assinada no comunicador local e o DANFE sai na hora. **Só no modo local** — na nuvem, sem internet, o PDV nem alcança o comunicador |
| A SEFAZ volta | o PDV transmite as contingências pendentes (prazo: **24 h**). O comunicador não retransmite sozinho |
| A resposta se perde | `incerto`: o PDV **consulta** a chave antes de reenviar — nunca emite de novo às cegas |
| O PC reinicia no meio de uma venda | nada se perde: a nota pendente mora no PDV |
| O certificado vai vencer | a tela Emitente (e `/v1/config/ler`) mostra a validade; troque o `.pfx` antes. Vencido, nenhuma nota sai |

## 10. Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Docker reinicia sem parar; o log diz "o comunicador não sobe" | token fraco, chave ausente/inválida ou `ACBR_MODO` errado | corrigir o `.env` como o log indica |
| `401 token inválido` | token diferente do comunicador | copiar de novo (local: tela Acesso; nuvem: `.env`) |
| `429` na nuvem | o IP errou o token várias vezes | esperar o `Retry-After`; corrigir o token do cliente |
| `403` ao configurar | `/v1/config/*` chamada de outro computador | configurar no próprio computador do comunicador (ou `ACBR_CONFIG_REDES`) |
| `403` no navegador | origem fora de `ACBR_ALLOWED_ORIGINS` | incluir a origem exata do PDV web |
| `sigilo` / `nao_decifrou` | chave do cliente diferente da do servidor | conferir a `ACBR_E2E_KEY` dos dois lados |
| `sigilo` / `fora_da_janela` | relógio errado no cliente ou no servidor | acertar a hora (NTP) |
| `sigilo` / `cifra_no_modo_local` | o PDV ainda cifra, mas o comunicador é local | no local, mandar JSON comum, só com o token |
| `configuracao` / `senha_invalida`, `certificado_vencido`, `cnpj_diferente` | o A1 | trocar o `.pfx` ou a senha |
| `configuracao` / `acbrlib_ausente`, ou `/health` 503 | a ACBrLib não carregou | ver o `mensagem` do `/health`; no Linux, conferir `libxml2` e `libssl3` |
| Rejeição 704 (data de emissão) | fuso errado | ajustar o **fuso** do emitente |
| Rejeição 539/613 (número repetido) | dois emissores na mesma série | uma série por caixa |
| A porta 8030 está em uso | outro comunicador (ou o serviço Windows) aberto | fechar o outro, ou trocar a porta em Acesso |

## 11. Onde fica cada coisa

| | Desktop Windows | Desktop Linux | Serviço Windows | Docker |
|---|---|---|---|---|
| Configuração (`.env`, emitentes, token) | `%APPDATA%\Comunicador Fiscal\servidor` | `~/.config/Comunicador Fiscal/servidor` | `%PROGRAMDATA%\AcbrFiscal` | `.env` + `./data` |
| Log | `…\servidor\log` (e a tela Status) | `…/servidor/log` | `%PROGRAMDATA%\AcbrFiscal\log` | `docker compose logs` + `./data/log` |
| ACBrLib | dentro do `.exe` | dentro do AppImage | `C:\Program Files\AcbrFiscal\lib` | dentro da imagem (`/opt/acbr`) |

Nenhum deles guarda XML de nota.

## 12. Checklist de segurança

- [ ] **Nuvem:** HTTPS na frente; a porta 8030 fechada para a internet; token de 32+ caracteres e chave só com o ERP.
- [ ] **Nuvem:** `FORWARDED_ALLOW_IPS` coerente com o proxy ([5.2](#52-subir)).
- [ ] **Local:** só `127.0.0.1`, a não ser que os caixas da rede precisem; rede da loja confiável (no local, o token anda sem cifra).
- [ ] `ACBR_SIMULADOR=0` (ou SEFAZ simulada desligada) em produção.
- [ ] `ACBR_ALLOWED_ORIGINS` só com as origens do PDV web, se houver.
- [ ] Backup do `.env` (e, no local, da pasta de dados), fora do servidor.
- [ ] Trocou de funcionário ou de PDV? Gere um token novo.
