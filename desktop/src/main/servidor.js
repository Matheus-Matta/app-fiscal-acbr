// O comunicador local: o mesmo AcbrFiscal.exe do serviço Windows (server/windows/servico.py),
// aberto como processo filho, com a pasta de dados do usuário e o .env que o desktop grava.
const { execFileSync, spawn } = require('node:child_process');
const crypto = require('node:crypto');
const { EventEmitter } = require('node:events');
const fs = require('node:fs');
const net = require('node:net');
const path = require('node:path');
const { saude } = require('./cliente');

const MAX_LINHAS = 300;
const REINICIOS_POR_MINUTO = 5;

/** Mesmas regras do `ler_env` do servico.py: o valor vai inteiro, até o "=" do base64. */
function lerEnv(arquivo) {
  if (!fs.existsSync(arquivo)) return {};
  const valores = {};
  for (const bruta of fs.readFileSync(arquivo, 'utf8').split(/\r?\n/)) {
    const linha = bruta.trim();
    if (!linha || linha.startsWith('#') || !linha.includes('=')) continue;
    const i = linha.indexOf('=');
    valores[linha.slice(0, i).trim()] = linha.slice(i + 1).trim();
  }
  return valores;
}

function gravarEnv(arquivo, valores) {
  fs.mkdirSync(path.dirname(arquivo), { recursive: true });
  const corpo =
    '# Gravado pelo Comunicador Fiscal (desktop). O mesmo formato do .env do Docker.\n' +
    Object.entries(valores)
      .map(([chave, valor]) => `${chave}=${String(valor ?? '').replace(/[\r\n]/g, '')}`)
      .join('\n') +
    '\n';
  const temporario = `${arquivo}.novo`;
  fs.writeFileSync(temporario, corpo, { encoding: 'utf8', mode: 0o600 });
  fs.renameSync(temporario, arquivo);
}

/** Se o PID ainda é um processo com este nome de executável (o PID pode ter sido reaproveitado). */
function imagemDoProcesso(pid, nome) {
  try {
    if (process.platform === 'win32') {
      const saida = execFileSync('tasklist', ['/FI', `PID eq ${pid}`, '/FO', 'CSV', '/NH'], {
        encoding: 'utf8',
        windowsHide: true,
      });
      return saida.toLowerCase().includes(`"${nome.toLowerCase()}"`);
    }
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

const gerarToken = () => crypto.randomBytes(32).toString('base64url');
const gerarChave = () => crypto.randomBytes(32).toString('base64');

function portaLivre(porta, host) {
  return new Promise((resolve) => {
    const teste = net.createServer();
    teste.once('error', () => resolve(false));
    teste.once('listening', () => teste.close(() => resolve(true)));
    teste.listen(porta, host);
  });
}

class ServidorLocal extends EventEmitter {
  /**
   * @param {object} o
   * @param {string} o.pastaDados  ACBR_DATA_DIR: .env, configuração guardada, log, lib
   * @param {string} o.comando     o AcbrFiscal.exe (ou o python, no desenvolvimento)
   * @param {string[]} [o.argumentos]
   * @param {object} [o.ambienteExtra]
   */
  constructor({ pastaDados, comando, argumentos = [], ambienteExtra = {} }) {
    super();
    Object.assign(this, { pastaDados, comando, argumentos, ambienteExtra });
    this.processo = null;
    this.parando = false;
    this.reinicios = [];
    this.linhas = [];
    this.estado = { situacao: 'parado', mensagem: '' };
  }

  get arquivoEnv() {
    return path.join(this.pastaDados, '.env');
  }

  get pastaLib() {
    return path.join(this.pastaDados, 'lib');
  }

  /** Lê o .env, gera token e chave na primeira vez e grava as opções da tela. */
  garantirEnv(opcoes = {}) {
    const atual = lerEnv(this.arquivoEnv);
    const valores = {
      ...atual, // o que não é da tela (ACBRLIB_PACOTE_URL, ACBRLIB_SO_SHA256...) fica
      ACBRLIB_TOKEN: atual.ACBRLIB_TOKEN || gerarToken(),
      ACBR_E2E_KEY: atual.ACBR_E2E_KEY || gerarChave(),
      ACBR_ALLOWED_ORIGINS: opcoes.origens ?? atual.ACBR_ALLOWED_ORIGINS ?? '',
      ACBR_SIMULADOR: (opcoes.simulador ?? atual.ACBR_SIMULADOR === '1') ? '1' : '0',
      ACBR_PORT: String(opcoes.porta ?? atual.ACBR_PORT ?? 8030),
      // 0.0.0.0: o PDV em outro PC da rede local alcança este. Padrão: só este PC.
      ACBR_HOST: (opcoes.rede ?? atual.ACBR_HOST === '0.0.0.0') ? '0.0.0.0' : '127.0.0.1',
    };
    gravarEnv(this.arquivoEnv, valores);
    return valores;
  }

  trocarTokenNoEnv(token) {
    gravarEnv(this.arquivoEnv, { ...lerEnv(this.arquivoEnv), ACBRLIB_TOKEN: token });
  }

  gravarNoEnv(mudancas) {
    gravarEnv(this.arquivoEnv, { ...lerEnv(this.arquivoEnv), ...mudancas });
  }

  /**
   * Instala a ACBrLib de um pacote (.zip/.tar.gz) deste computador, com o próprio
   * comunicador (`instalar-lib`): confere o cabeçalho, acha a lib e os Schemas e
   * troca a pasta lib inteira. Para o comunicador antes — a DLL carregada prende a
   * pasta — e o reabre depois.
   */
  async instalarLibDeArquivo(arquivo, opcoes = {}) {
    await this.parar();
    const ambiente = Object.fromEntries(Object.entries(process.env).filter(([k]) => !/^ACBR/i.test(k)));
    const saida = await new Promise((resolve) => {
      let texto = '';
      const processo = spawn(this.comando, [...this.argumentos, 'instalar-lib', '--arquivo', arquivo], {
        env: { ...ambiente, ...this.ambienteExtra, ACBR_DATA_DIR: this.pastaDados, PYTHONIOENCODING: 'utf-8' },
        cwd: path.dirname(this.comando),
        windowsHide: true,
      });
      processo.stdout.on('data', (d) => { texto += d; });
      processo.stderr.on('data', (d) => this._registrar(d));
      processo.on('error', (erro) => resolve(JSON.stringify({ ok: false, mensagem: erro.message })));
      processo.on('exit', () => resolve(texto));
    });
    let resultado;
    try {
      resultado = JSON.parse(saida.trim().split(/\r?\n/).pop());
    } catch {
      resultado = { ok: false, mensagem: `O instalador não respondeu (${saida.slice(0, 200)}).` };
    }
    this._registrar(`--- instalar-lib: ${resultado.mensagem} ---`);
    this.reinicios = [];
    await this.iniciar(opcoes);
    return resultado;
  }

  conexao() {
    const env = lerEnv(this.arquivoEnv);
    return {
      url: `http://127.0.0.1:${env.ACBR_PORT || 8030}`,
      token: env.ACBRLIB_TOKEN || '',
      chave: env.ACBR_E2E_KEY || '',
    };
  }

  _mudar(situacao, mensagem = '') {
    this.estado = { situacao, mensagem, pid: this.processo?.pid };
    this.emit('estado', this.estado);
  }

  _registrar(texto) {
    for (const linha of String(texto).split(/\r?\n/)) {
      if (!linha.trim()) continue;
      this.linhas.push(linha);
      if (this.linhas.length > MAX_LINHAS) this.linhas.shift();
    }
  }

  get arquivoPid() {
    return path.join(this.pastaDados, 'comunicador.pid');
  }

  /** Um comunicador órfão (o desktop foi encerrado à força) ainda segurando a porta. */
  async _encerrarOrfao() {
    let pid;
    try {
      pid = Number(fs.readFileSync(this.arquivoPid, 'utf8'));
    } catch {
      return;
    }
    fs.rmSync(this.arquivoPid, { force: true });
    if (!Number.isInteger(pid) || pid <= 0 || !imagemDoProcesso(pid, path.basename(this.comando))) return;
    this._registrar(`--- encerrando o comunicador anterior que ficou aberto (PID ${pid}) ---`);
    try {
      process.kill(pid);
    } catch {
      return;
    }
    for (let i = 0; i < 20 && imagemDoProcesso(pid, path.basename(this.comando)); i += 1) {
      await new Promise((r) => setTimeout(r, 250));
    }
  }

  async iniciar(opcoes = {}) {
    if (this.processo) return;
    const env = this.garantirEnv(opcoes);
    const porta = Number(env.ACBR_PORT);
    await this._encerrarOrfao();
    if (!(await portaLivre(porta, env.ACBR_HOST))) {
      this._mudar(
        'erro',
        `A porta ${porta} já está em uso — outro Comunicador ou o serviço Windows AcbrFiscal? ` +
          'Feche-o ou troque a porta em Acesso.',
      );
      return;
    }
    if (!fs.existsSync(this.comando)) {
      this._mudar('erro', `O comunicador não foi encontrado em ${this.comando}.`);
      return;
    }

    // Nada de ACBR_* herdado do Windows: vale só o .env desta pasta.
    const ambiente = Object.fromEntries(Object.entries(process.env).filter(([k]) => !/^ACBR/i.test(k)));
    this.parando = false;
    this._mudar('iniciando');
    this._registrar(`--- iniciando ${this.comando} ---`);
    const processo = spawn(this.comando, this.argumentos, {
      env: { ...ambiente, ...this.ambienteExtra, ACBR_DATA_DIR: this.pastaDados, PYTHONIOENCODING: 'utf-8' },
      cwd: path.dirname(this.comando),
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    this.processo = processo;
    if (processo.pid) fs.writeFileSync(this.arquivoPid, String(processo.pid));
    processo.stdout.on('data', (d) => this._registrar(d));
    processo.stderr.on('data', (d) => this._registrar(d));
    processo.on('error', (erro) => this._registrar(`erro ao abrir: ${erro.message}`));
    processo.on('exit', (codigo) => this._saiu(processo, codigo));
    this._aguardarPronto(processo, `http://127.0.0.1:${porta}`);
  }

  async _aguardarPronto(processo, url) {
    for (let i = 0; i < 60 && this.processo === processo; i += 1) {
      const resposta = await saude(url);
      if (resposta.alcancado) {
        if (this.processo === processo) this._mudar('rodando');
        return;
      }
      await new Promise((r) => setTimeout(r, 500));
    }
    if (this.processo === processo) this._mudar('erro', 'O comunicador abriu, mas não respondeu em 30 s.');
  }

  _saiu(processo, codigo) {
    if (this.processo !== processo) return;
    this.processo = null;
    fs.rmSync(this.arquivoPid, { force: true });
    this._registrar(`--- comunicador encerrou (código ${codigo}) ---`);
    if (this.parando) {
      this._mudar('parado');
      return;
    }
    const agora = Date.now();
    this.reinicios = this.reinicios.filter((t) => agora - t < 60_000);
    if (this.reinicios.length >= REINICIOS_POR_MINUTO) {
      const ultima = this.linhas.slice(-3).join(' | ');
      this._mudar('erro', `O comunicador caiu ${REINICIOS_POR_MINUTO} vezes em 1 minuto. Último registro: ${ultima}`);
      return;
    }
    this.reinicios.push(agora);
    this._mudar('iniciando', 'O comunicador caiu; reabrindo…');
    setTimeout(() => {
      if (!this.processo && !this.parando) this.iniciar();
    }, 2000);
  }

  parar() {
    this.parando = true;
    const processo = this.processo;
    if (!processo) {
      this._mudar('parado');
      return Promise.resolve();
    }
    return new Promise((resolve) => {
      const tempo = setTimeout(resolve, 5000);
      processo.once('exit', () => {
        clearTimeout(tempo);
        resolve();
      });
      processo.kill();
    });
  }

  async reiniciar(opcoes = {}) {
    await this.parar();
    this.reinicios = [];
    await this.iniciar(opcoes);
  }
}

module.exports = { ServidorLocal, lerEnv, gravarEnv, gerarToken, gerarChave, portaLivre };
