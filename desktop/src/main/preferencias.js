// As preferências do desktop (desktop.json na pasta do usuário): o modo (comunicador
// local ou Docker remoto) e as opções de cada um. Token e chave do remoto vão cifrados
// pelo Windows (safeStorage/DPAPI), quando disponível.
const fs = require('node:fs');
const path = require('node:path');

const PADRAO = {
  modo: 'local',
  local: { porta: 8030, rede: false, origens: '', simulador: false },
  remoto: { url: '', token: '', chave: '' },
  avisouBandeja: false,
};

const SEGREDOS = ['token', 'chave'];

class Preferencias {
  /** @param {string} arquivo  @param {{isEncryptionAvailable(): boolean, encryptString(s: string): Buffer, decryptString(b: Buffer): string}} [cofre] */
  constructor(arquivo, cofre) {
    this.arquivo = arquivo;
    this.cofre = cofre;
  }

  _abrir(valor) {
    if (valor && typeof valor === 'object' && valor.cifrado && this.cofre) {
      try {
        return this.cofre.decryptString(Buffer.from(valor.cifrado, 'base64'));
      } catch {
        return '';
      }
    }
    return typeof valor === 'string' ? valor : '';
  }

  _fechar(valor) {
    if (valor && this.cofre?.isEncryptionAvailable()) {
      return { cifrado: this.cofre.encryptString(valor).toString('base64') };
    }
    return valor;
  }

  ler() {
    let gravado = {};
    try {
      gravado = JSON.parse(fs.readFileSync(this.arquivo, 'utf8'));
    } catch {
      gravado = {};
    }
    const remoto = { ...PADRAO.remoto, ...gravado.remoto };
    for (const campo of SEGREDOS) remoto[campo] = this._abrir(remoto[campo]);
    return {
      ...PADRAO,
      ...gravado,
      modo: gravado.modo === 'remoto' ? 'remoto' : 'local',
      local: { ...PADRAO.local, ...gravado.local },
      remoto,
    };
  }

  salvar(mudancas) {
    const atual = this.ler();
    const novo = {
      ...atual,
      ...mudancas,
      local: { ...atual.local, ...mudancas.local },
      remoto: { ...atual.remoto, ...mudancas.remoto },
    };
    const gravar = { ...novo, remoto: { ...novo.remoto } };
    for (const campo of SEGREDOS) gravar.remoto[campo] = this._fechar(novo.remoto[campo]);
    fs.mkdirSync(path.dirname(this.arquivo), { recursive: true });
    fs.writeFileSync(this.arquivo, JSON.stringify(gravar, null, 2), { encoding: 'utf8', mode: 0o600 });
    return novo;
  }
}

module.exports = { Preferencias, PADRAO };
