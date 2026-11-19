# Licenças das bibliotecas de terceiros

Este repositório redistribui, sem modificações, bibliotecas compiladas de terceiros, para
que o comunicador funcione sem baixar nada:

- `server/embutida/` — Linux x64: vai para dentro da imagem Docker (`/opt/acbr`).
- `server/windows/lib/` — Windows x64: vai para dentro do `.exe` do serviço e do desktop.

Cada uma segue a sua própria licença, cujo texto está nesta pasta. Esta pasta vai junto
com as bibliotecas (`LICENCAS/` ao lado delas), na imagem e no `.exe`.

| Componente | Arquivos | Licença | Texto |
|---|---|---|---|
| ACBrLibNFe — Projeto ACBr, SVN trunk2 **r48608** | `libacbrnfe64.so`, `ACBrNFe64.dll` | LGPL 2.1 ou posterior | [ACBr-LGPL-2.1.txt](ACBr-LGPL-2.1.txt) |
| OpenSSL 1.1.1 (DLLs distribuídas pelo Projeto ACBr) | `libcrypto-1_1-x64.dll`, `libssl-1_1-x64.dll` | OpenSSL License + SSLeay License | [OpenSSL-1.1.1.txt](OpenSSL-1.1.1.txt) |
| libxml2 (idem) | `libxml2.dll` | MIT | [libxml2-MIT.txt](libxml2-MIT.txt) |
| libxslt e libexslt (idem) | `libxslt.dll`, `libexslt.dll` | MIT | [libxslt-libexslt-MIT.txt](libxslt-libexslt-MIT.txt) |
| GNU libiconv (idem) | `libiconv.dll` | LGPL 2.1 ou posterior | [ACBr-LGPL-2.1.txt](ACBr-LGPL-2.1.txt) |
| Schemas da NF-e (Portal da NF-e / ENCAT, distribuídos pelo Projeto ACBr) | `Schemas/*.xsd` | Publicação oficial | — |

Na imagem Linux, a OpenSSL e a libxml2 são as do próprio Debian, instaladas pelo `apt`
(`Dockerfile`), e não as daqui.

## Código-fonte (LGPL)

A ACBrLibNFe foi compilada **sem modificações** a partir do código público do Projeto
ACBr — https://projetoacbr.com.br:

    svn checkout -r 48608 https://svn.code.sf.net/p/acbr/code/trunk2

- **Windows**: [`server/windows/compilar-acbrlib.ps1 -Revisao 48608`](../windows/compilar-acbrlib.ps1)
  baixa exatamente esse código e refaz a `ACBrNFe64.dll`
  (`lazbuild --build-all --build-mode=win64-x86_64-MT --ws=nogui ACBrLibNFeConsoleMT.lpi`).
- **Linux**: o mesmo projeto, modo `Linux-x86_64-MT`, com `ACBR_HOME` apontando para o
  código (`docs/INTEGRACAO.md`, "A ACBrLib").

Para conferir que os binários daqui são os de sempre, compare o SHA-256:

| Arquivo | SHA-256 |
|---|---|
| `embutida/libacbrnfe64.so` | `deec61a921b830516ad3d7f5833aee7cb69603391eb497e649296ecc5522b3f0` |
| `windows/lib/ACBrNFe64.dll` | `eee3334e0579712e26e54f2643d2e84a31e94ffe229aa2fdd1b5dff529c32494` |

As bibliotecas são carregadas dinamicamente (ctypes) pelo comunicador, que é um programa
separado: quem quiser pode trocá-las por outra compilação, como a LGPL garante.
