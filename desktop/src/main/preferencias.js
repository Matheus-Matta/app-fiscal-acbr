// As preferências do desktop (desktop.json na pasta do usuário): as opções do comunicador
// local. Nada secreto mora aqui: o token fica no .env do comunicador.
const fs = require('node:fs');
const path = require('node:path');

const PADRAO = {
  local: { porta: 8030, rede: false, origens: '', simulador: false },
  avisouBandeja: false,
};

class Preferencias {
  /** @param {string} arquivo */
  constructor(arquivo) {
    this.arquivo = arquivo;
  }

  ler() {
    let gravado = {};
    try {
      gravado = JSON.parse(fs.readFileSync(this.arquivo, 'utf8'));
    } catch {
      gravado = {};
    }
    // Versões anteriores tinham um modo "remoto" (token e chave de um Docker): fica de fora.
    return {
      local: { ...PADRAO.local, ...gravado.local },
      avisouBandeja: Boolean(gravado.avisouBandeja),
    };
  }

  salvar(mudancas) {
    const atual = this.ler();
    const novo = { ...atual, ...mudancas, local: { ...atual.local, ...mudancas.local } };
    fs.mkdirSync(path.dirname(this.arquivo), { recursive: true });
    fs.writeFileSync(this.arquivo, JSON.stringify(novo, null, 2), { encoding: 'utf8', mode: 0o600 });
    return novo;
  }
}

module.exports = { Preferencias, PADRAO };
