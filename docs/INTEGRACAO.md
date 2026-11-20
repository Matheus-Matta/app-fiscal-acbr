# Integrando um sistema ao Comunicador Fiscal

Para quem escreve o cliente: um PDV, um ERP, um backend — qualquer sistema que precise
emitir NFC-e/NF-e. O comunicador assina e transmite pela ACBrLib; o cliente monta o
documento, guarda a nota e decide o que fazer com cada resposta.

```
cliente (PDV / ERP) ──► Comunicador Fiscal ──► ACBrLib ──► SEFAZ
         ▲                     │
         └──── resposta ───────┘
```

Cada rota, campo, resposta e erro está na [referência da API](API.md); instalar e operar, no
[guia de uso](USO.md). Aqui fica o que o cliente precisa decidir.

## Qual comunicador o cliente chama

| | Comunicador na **nuvem** (Docker, `ACBR_MODO=nuvem`) | Comunicador **local** (desktop, serviço Windows) |
|---|---|---|
| O cliente guarda | o token, a `ACBR_E2E_KEY`, e o certificado A1 + senha + CSC de cada emitente | só o token |
| Cada chamada leva | `Authorization: Bearer`, corpo cifrado, o contexto inteiro (`cnpj`, `uf`, `ambiente`, `modelo`, `certificado`, `csc`) e o documento | `Authorization: Bearer`, os dados da emissão (`uf`, `ambiente`, `modelo`, `fuso`; `cnpj` se houver mais de um emitente) e o documento, em JSON comum |
| Os segredos (A1, senha, CSC) | ficam com o cliente, que os manda em toda chamada | ficam no comunicador, gravados na tela **Emitente** do desktop, nesta máquina |
| Endereço | `https://` atrás de um proxy | `http://127.0.0.1:8030` (ou o IP do PC, na rede da loja) |

**Nuvem, exemplo** (o JSON abaixo é o texto claro que vai cifrado no envelope):

```json
POST /v1/nfe/emitir
{"cnpj": "11222333000181", "uf": "SP", "ambiente": "1", "modelo": "65", "fuso": "-03:00",
 "certificado": {"pfx_base64": "MIIK…", "senha": "…"}, "csc": {"id": "1", "token": "…"},
 "ini": "[Identificacao]…"}
```

O cliente guarda o certificado e o CSC como guarda qualquer segredo (cofre, variável
cifrada) e só os manda para o comunicador dentro do envelope. A resposta traz o XML
assinado/autorizado: o comunicador não fica com cópia (nem na nuvem nem no local), então **guardar o XML é
obrigação do cliente**.

**Local, exemplo:**

```bash
curl -X POST http://127.0.0.1:8030/v1/nfe/emitir \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"uf": "SP", "ambiente": "1", "modelo": "65", "fuso": "-03:00", "ini": "[Identificacao]…"}'
```

## Quem guarda o quê

O comunicador **não tem fila nem banco de notas**. A nota pendente, o XML assinado em
contingência e o número da série moram no cliente. Se o comunicador reiniciar no meio,
nada se perde: o cliente tem tudo para consultar ou transmitir de novo.

Na nuvem, o comunicador não guarda nada do emitente nem das notas. No local, guarda só
os segredos do emitente (certificado A1, senha e CSC), gravados pelo desktop, e nenhum
XML. Os dados da emissão (UF, ambiente, modelo, fuso; regime, CST e IBS/CBS no INI) vêm
sempre na chamada; certificado e CSC vindos na chamada valem sobre os guardados.

## O resultado

Toda operação fiscal que deu certo devolve a mesma forma:

```json
{"situacao": "autorizada | rejeitada | denegada | contingencia | processando | nao_encontrada | cancelada",
 "cstat": "100", "motivo": "Autorizado o uso da NF-e", "chave": "3526…", "protocolo": "135…",
 "recebido_em": "2026-10-09T14:03:11-03:00", "xml": "<nfeProc …>", "qrcode": "https://…?p=…",
 "digest_value": "…"}
```

A ACBrLib devolver "ok" é a chamada que deu certo, não a autorização: quem diz o destino
da nota é o `cstat`, já traduzido em `situacao`.

## O que fazer com cada erro

| Resposta | Significa | O cliente faz |
|---|---|---|
| `situacao: autorizada` | nota válida | grava chave, protocolo e XML; imprime o DANFE |
| `situacao: rejeitada` / `denegada` | a SEFAZ recusou | mostra o `motivo`; corrige e emite de novo **com o mesmo número** |
| `erro: sem_comunicacao` (503) | a nota **não saiu** | contingência (`tp_emis: "9"`), ou tenta de novo depois |
| `erro: incerto` (500) | a nota **pode ter saído** | **consulta antes de qualquer reenvio** |
| `erro: documento_invalido` (422) | schema, assinatura, INI ou campo fora do contrato | corrige o documento; repetir dá o mesmo erro |
| `erro: configuracao` (500) | certificado, CSC, lib ou emitente | nada sai até corrigir; **nunca** vira contingência |
| sem resposta, 401, 403, 429 ou `erro: sigilo` | não se sabe o que houve | trata como `incerto`: depois de um envio, consulta |
| `situacao: nao_encontrada` (na consulta) | a SEFAZ não tem a nota | pode transmitir de novo |

O `motivo` de cada erro diz a providência para o operador (`senha_invalida`,
`certificado_vencido`, `acbrlib_ausente`, `comunicador_ocupado`...). A lista está no
[`server/README.md`](../server/README.md#erros-do-comunicador).

**Duplicidade (cStat 204/539) não chega como recusa**: o comunicador consulta a chave e
devolve a situação real. **Serviço paralisado (108/109) chega como `sem_comunicacao`**:
é indisponibilidade, e justifica contingência.

## Contingência offline (NFC-e)

Contingência é para **indisponibilidade**, nunca para recusa.

```
                 emitir (tp_emis "1")
       ┌──────────────┼──────────────────┬─────────────────────┐
   autorizada     rejeitada        sem_comunicacao           incerto
       │              │                  │                      │
    pronto     corrige e emite    emitir com tp_emis "9"     CONSULTA (nunca reenvia)
               (mesmo número)     mesmo nNF, tpEmis=9 no INI   autorizada → pronto
                                  → situacao "contingencia"    nao_encontrada → emite de novo
                                  grava o XML, imprime o DANFE
                                  de contingência
                                         │
                      quando a SEFAZ voltar: /v1/nfe/transmitir com O MESMO XML
                         ┌───────────────┼────────────────┐
                    autorizada       rejeitada        sem_comunicacao
                       pronto     erro + alerta       tenta de novo depois
```

Os pontos que evitam nota em dobro:

1. **`incerto` nunca vira contingência às cegas.** A SEFAZ pode ter autorizado a normal:
   consulte primeiro. Se o cliente decidir imprimir em contingência mesmo assim, guarde a
   chave da normal e consulte-a antes de transmitir a contingência — autorizada, a nota é
   ela e a contingência é descartada.
2. **O XML de contingência é transmitido como foi assinado.** Não refaça `dhEmi` nem a
   chave: o cupom impresso tem aquela chave, e é ela que a SEFAZ tem de receber.
3. **Mesmo número, chave nova.** A contingência reaproveita o `nNF` que não foi
   autorizado; a chave muda porque o `tpEmis` faz parte dela. Mantenha o mesmo `cNF` em
   todas as tentativas da mesma nota: é como se reconhece uma tentativa anterior.
4. **Uma série por ponto de emissão.** Dois emissores na mesma série (dois PCs, ou um
   ambiente de teste com o mesmo CNPJ) acabam com número repetido — rejeição 539/613.

Prazo: a NFC-e em contingência tem de ser transmitida em até 24 h. O comunicador não
retransmite sozinho — o cliente agenda a transmissão das pendentes.

## A ACBrLib

A biblioteca é do Projeto ACBr (LGPL 2.1) e **vem neste repositório**, compilada do código
público na revisão r48608 do SVN, sem modificações. Nada é baixado para emitir:

| | Onde está | Vai para |
|---|---|---|
| Linux x64 | [`server/embutida/`](../server/embutida/LEIAME.md): `libacbrnfe64.so` + `Schemas` | a imagem Docker (`/opt/acbr`) |
| Windows x64 | `server/windows/lib/`: `ACBrNFe64.dll` + OpenSSL + libxml2 + `Schemas` | o `.exe` do serviço e o desktop |

Licenças, origem do código e SHA-256 de cada binário:
[`server/licencas/LEIA-ME.md`](../server/licencas/LEIA-ME.md). A DLL do Windows se refaz com
[`server/windows/compilar-acbrlib.ps1 -Revisao 48608`](../server/windows/compilar-acbrlib.ps1),
e um teste confere que os binários do repositório têm o SHA-256 publicado.

Onde a lib pode estar, na ordem em que vale:

| | Docker | Desktop / serviço Windows |
|---|---|---|
| montada | `./libs` → `/app/libs` | — |
| embutida (a do repositório) | `/opt/acbr` | instalada pelo comunicador, se houver (`<dados>\lib`); senão a que vai junto no `.exe` |
| instalada pelo comunicador | `/app/data/lib` (volume) | `%APPDATA%\Comunicador Fiscal\servidor\lib` / `%PROGRAMDATA%\AcbrFiscal\lib` |

**Trocar de versão:**

- **Docker**: ponha a nova lib e os `Schemas` em `server/embutida/` e refaça a imagem, ou
  monte-os em `./libs` (vale antes da embutida, sem refazer nada).
- **Desktop / serviço**: rode `compilar-acbrlib.ps1` com outra `-Revisao` e gere o `.exe` de
  novo, ou instale um pacote pela tela Status ou por `AcbrFiscal.exe instalar-lib` — a lib
  instalada na pasta de dados vale antes da que vem no `.exe`.

O instalador ([`server/app/instalador.py`](../server/app/instalador.py)) continua para quem
quiser um pacote próprio: `ACBRLIB_PACOTE_URL` + `ACBRLIB_SO_SHA256`,
`POST /v1/config/lib {url, sha256}` ou `python -m app.instalador --url URL --sha256 HASH`
(ou `--arquivo pacote.zip`). Confere a lib pelo SHA-256 e pelo cabeçalho (ELF/MZ) antes de
pô-la no lugar, inteira ou nada. Ele só age quando **não há lib nenhuma carregada** (com a
embutida, a rota responde `lib_ja_carregada`). Sem `ACBRLIB_PACOTE_URL`, nada é baixado.
Os Schemas valem os que estão ao lado da lib escolhida.

Detalhes que já custaram nota recusada:

- **Linux: `libxml2.so`.** A lib abre o nome sem versão, e o Debian só traz `libxml2.so.2`.
  A imagem cria o atalho; sem ele, o `/health` responde 200 e a primeira nota falha na
  assinatura.
- **glibc.** A `.so` compilada para `Linux-x86_64-MT` costuma exigir glibc 2.34+: a imagem
  é Debian 12 (2.36). Alpine não serve.
- **Fuso do `dhEmi` (rejeição 704).** O INI leva a data sem fuso e a ACBrLib acrescenta o
  do sistema — UTC num container. O comunicador grava `TimeZone.Modo=2` e
  `TimeZone.Str` a cada nota, com o `fuso` da chamada.
- **Compilar a lib.** `export ACBR_HOME=<fontes>` antes do `lazbuild --build-all
  --build-mode=Linux-x86_64-MT --ws=nogui Projetos/ACBrLib/Fontes/NFe/ACBrLibNFeConsoleMT.lpi`
  — sem o `ACBR_HOME` o projeto não acha `ACBr.inc`.

A configuração base da lib está em [`server/config/ACBrLib.ini`](../server/config/ACBrLib.ini).
O que muda por emitente (UF, ambiente, modelo, certificado, CSC, forma de emissão) é
gravado pelo comunicador a cada chamada. Os endereços da SEFAZ de cada UF vêm na lib.

## Recusas do INI que o cliente evita

O INI segue o leiaute da ACBrLib NFe. Algumas recusas comuns:

- **866 — ausência de troco.** `vTroco = soma(vPag) − vNF`, nunca negativo, e vai
  **dentro da última seção `[pagNNN]`** — é só ali que o leitor da lib o procura. Numa
  seção `[pag]` à parte ele é ignorado.
- **899 / 865 — pagamento.** A NFC-e não aceita `tPag=90` (sem pagamento) nem pagamento
  abaixo do total. `tPag=99` (outros) exige `xPag` (441).
- **386 — CFOP × CSOSN (Simples).** CSOSN 500 só aceita CFOP 5405, 5656 ou 5667; os CSOSN
  101, 102, 103, 300, 400 e 900, só 5101–5104 e 5115.
- **373 / 598 — homologação.** Em homologação, o primeiro item da NFC-e precisa ser
  "NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL" e o destinatário
  "NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL".
- **539 / 613 — chave difere da existente.** O número já foi usado na SEFAZ. Mesmo `cNF`:
  é uma tentativa anterior desta nota — consulte e adote. `cNF` diferente: outro emissor
  usou o número; avance para o próximo livre.

## Homologação e produção

O ambiente vai na chamada, nos dois modos: `"2"` homologação, `"1"` produção. Ao passar
para produção, troque também o **CSC** pelo de produção e confira o **próximo número** da
série: notas de teste não ocupam números de produção, mas um buraco na série exige
inutilização na SEFAZ.

## Simulador

`ACBR_SIMULADOR=1` responde sem ir à SEFAZ, para desenvolver o cliente sem lib nem
certificado. Ele nunca se passa pela SEFAZ: o motivo diz **"SIMULADO — sem valor
fiscal"**, e produção é recusada. `POST /_simulador/modo` com `{"modo": "online" | "fora"
| "lenta" | "recusa"}` troca o comportamento, para testar cada caminho acima.

## Roteiro de homologação

1. Comunicador com a lib: `GET /health` com `lib: true`.
2. A1 e CSC de homologação (na chamada, na nuvem; gravados no desktop, no local); `POST /v1/status-servico`: `online: true`.
3. Venda → NFC-e autorizada (cStat 100), DANFE com protocolo.
4. Sem internet → `sem_comunicacao` → contingência → DANFE de contingência.
5. Reiniciar o comunicador com a nota pendente → nada se perde (está no cliente).
6. Internet de volta → `/v1/nfe/transmitir` → autorizada, com a mesma chave.
7. Tempo esgotado (bloquear a resposta) → `incerto` → consulta, nunca reenvio.
8. Dois caixas emitindo ao mesmo tempo → números diferentes.
9. Rejeição forçada (NCM inválido) → erro explicado; corrigir e emitir com o mesmo número.
10. Cancelar uma nota autorizada → evento registrado (NFC-e: em geral até 30 min).
