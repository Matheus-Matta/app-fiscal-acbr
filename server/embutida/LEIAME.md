# Lib embutida na imagem (Linux x64)

`libacbrnfe64.so` (ACBrLibNFe, Projeto ACBr, SVN trunk2 r48608, `Linux-x86_64-MT`) e a
pasta `Schemas`. Vêm no repositório: o `docker build` as copia para `/opt/acbr`, dentro da
imagem, e o comunicador não baixa nada. Uma lib montada em `/app/libs` continua valendo
primeiro.

Licença (LGPL 2.1), origem do código e SHA-256: [`../licencas/LEIA-ME.md`](../licencas/LEIA-ME.md).

Para trocar de versão, ponha a nova `.so` e os `Schemas` aqui (ou
`python -m app.instalador --url URL --sha256 HASH --destino embutida`) e atualize o
SHA-256 em `licencas/LEIA-ME.md`.
