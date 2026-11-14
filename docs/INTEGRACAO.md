# Integrando um sistema ao Comunicador Fiscal

Para quem escreve o cliente: um PDV, um ERP, um backend — qualquer sistema que precise
emitir NFC-e/NF-e. O comunicador assina e transmite pela ACBrLib; o cliente monta o
documento, guarda a nota e decide o que fazer com cada resposta.

```
cliente (PDV / ERP) ──► Comunicador Fiscal ──► ACBrLib ──► SEFAZ
         ▲                     │
         └──── resposta ───────┘
```

A API, a cifra de ponta a ponta e a configuração guardada estão em
[`server/README.md`](../server/README.md). Aqui fica o que o cliente precisa decidir.

## Quem guarda o quê

O comunicador **não tem fila nem banco de notas**. A nota pendente, o XML assinado em
contingência e o número da série moram no cliente. Se o comunicador reiniciar no meio,
nada se perde: o cliente tem tudo para consultar ou transmitir de novo.

O comunicador guarda só a configuração do emitente (certificado, CSC, UF, ambiente),
quando ela é gravada pelo desktop ou por `/v1/config/emitente`. Um cliente que prefira
mandar tudo em cada chamada pode — o que vem na chamada vale sobre o guardado.

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
| sem resposta, 401, 403 ou `erro: sigilo` | não se sabe o que houve | trata como `incerto`: depois de um envio, consulta |
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

A biblioteca é do Projeto ACBr, tem licença própria e não é versionada aqui. **O
comunicador a instala sozinho** ([`server/app/instalador.py`](../server/app/instalador.py)):

1. Sem lib, ele baixa o pacote de `ACBRLIB_PACOTE_URL` (`.tar.gz` ou `.zip`; link do
   MediaFire aceito — o direto é lido da página).
2. Confere a lib pelo **SHA-256** (`ACBRLIB_SO_SHA256`) e pelo cabeçalho (ELF no Linux, MZ
   no Windows). Uma página de erro, um download pela metade ou uma lib trocada viram
   aviso — nunca uma lib carregada.
3. Põe a lib, as que a acompanham e os `.xsd` de `Schemas/NFe` em `<dados>/lib`, inteira ou
   nada, e passa a emitir **sem reiniciar**. Já instalada e conferida, não baixa de novo;
   trocar o `ACBRLIB_SO_SHA256` (e o pacote) reinstala.
4. Nunca derruba o comunicador: falhou, o `/health` diz por quê.

Sem a variável, vale o **pacote de referência**: ACBrLibNFe 1.5.0.488, Linux x64 (MT),
SHA-256 `deec61a921b830516ad3d7f5833aee7cb69603391eb497e649296ecc5522b3f0`. **Para Windows
não há pacote de referência**: monte um `.zip` com `ACBrNFe64.dll`, as DLLs que a
acompanham e `Schemas/NFe`, hospede-o e informe URL e SHA-256 (no desktop, na tela Status).
`ACBRLIB_PACOTE_URL=` (vazia) desliga a instalação automática.

Onde a lib pode estar, na ordem em que vale:

| | Docker | Desktop / serviço Windows |
|---|---|---|
| montada / ao lado do programa | `./libs` → `/app/libs` | `windows\lib` no build (vai junto no `.exe`) |
| embutida na imagem | `embutida/`, `--build-arg ACBRLIB_PACOTE_URL`, ou a Action `imagem.yml` | — |
| instalada pelo comunicador | `/app/data/lib` (volume) | `%APPDATA%\Comunicador Fiscal\servidor\lib` / `%PROGRAMDATA%\AcbrFiscal\lib` |

Também à mão: `python -m app.instalador --url URL --sha256 HASH` (ou `--arquivo pacote.zip`),
`AcbrFiscal.exe instalar-lib ...`, a rota `POST /v1/config/lib {url, sha256}` ou os botões
da tela Status do desktop. Os Schemas valem os que estão ao lado da lib escolhida.

Detalhes que já custaram nota recusada:

- **Linux: `libxml2.so`.** A lib abre o nome sem versão, e o Debian só traz `libxml2.so.2`.
  A imagem cria o atalho; sem ele, o `/health` responde 200 e a primeira nota falha na
  assinatura.
- **glibc.** A `.so` compilada para `Linux-x86_64-MT` costuma exigir glibc 2.34+: a imagem
  é Debian 12 (2.36). Alpine não serve.
- **Fuso do `dhEmi` (rejeição 704).** O INI leva a data sem fuso e a ACBrLib acrescenta o
  do sistema — UTC num container. O comunicador grava `TimeZone.Modo=2` e
  `TimeZone.Str` a cada nota, com o `fuso` do contexto (ou do emitente guardado).
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

O ambiente vai no emitente (ou na chamada): `"2"` homologação, `"1"` produção. Ao passar
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
2. Emitente gravado com o A1 e o CSC de homologação; `POST /v1/status-servico`: `online: true`.
3. Venda → NFC-e autorizada (cStat 100), DANFE com protocolo.
4. Sem internet → `sem_comunicacao` → contingência → DANFE de contingência.
5. Reiniciar o comunicador com a nota pendente → nada se perde (está no cliente).
6. Internet de volta → `/v1/nfe/transmitir` → autorizada, com a mesma chave.
7. Tempo esgotado (bloquear a resposta) → `incerto` → consulta, nunca reenvio.
8. Dois caixas emitindo ao mesmo tempo → números diferentes.
9. Rejeição forçada (NCM inválido) → erro explicado; corrigir e emitir com o mesmo número.
10. Cancelar uma nota autorizada → evento registrado (NFC-e: em geral até 30 min).
