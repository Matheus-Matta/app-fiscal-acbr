# Lib embutida na imagem

Coloque aqui a `libacbrnfe64.so` (e a pasta `Schemas`) antes do `docker build` e o
Dockerfile a copia para `/opt/acbr`, dentro da imagem: quem instala não precisa
montar nada. Uma lib montada em `/app/libs` continua valendo primeiro.

A `.so` nunca é versionada (`.gitignore`): tem licença própria do Projeto ACBr.
Confira a licença antes de publicar uma imagem com a lib num registro público.
Ver `docs/INTEGRACAO.md`, "A ACBrLib".
