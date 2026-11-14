// Comunicador Fiscal — desktop. Um .exe só (portátil, sem instalador): abre a janela de
// configuração e sobe o comunicador local (AcbrFiscal.exe) por baixo. Fechar a janela
// não encerra: ele fica na bandeja, emitindo para o PDV. "Sair" está no menu da bandeja.
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {
  app, BrowserWindow, Menu, Tray, clipboard, dialog, ipcMain, nativeImage, safeStorage, shell,
} = require('electron');
const { chamar, saude } = require('./cliente');
const { Preferencias } = require('./preferencias');
const { ServidorLocal } = require('./servidor');

app.setName('Comunicador Fiscal'); // antes de qualquer getPath: a pasta do usuário leva este nome

const EMPACOTADO = app.isPackaged;
const URL_DEV = process.env.ACBR_DEV_URL || '';
const RAIZ = path.join(__dirname, '..', '..');
const OCULTO = process.argv.includes('--oculto'); // aberto com o Windows: direto para a bandeja
const TAMANHO_MAXIMO_PFX = 256 * 1024;

let janela = null;
let bandeja = null;
let saindo = false;
let encerrado = false;
let prefs;
let servidor;

function recurso(nome) {
  return EMPACOTADO ? path.join(process.resourcesPath, nome) : path.join(RAIZ, 'resources', nome);
}

function acharPython() {
  try {
    return execFileSync('where', ['python'], { encoding: 'utf8' }).split(/\r?\n/)[0].trim();
  } catch {
    return 'python';
  }
}

function criarServidor() {
  const pastaDados = path.join(app.getPath('userData'), 'servidor');
  if (EMPACOTADO) {
    return new ServidorLocal({ pastaDados, comando: path.join(process.resourcesPath, 'servidor', 'AcbrFiscal.exe') });
  }
  // Desenvolvimento: o servico.py direto do repositório.
  const pastaServer = path.join(RAIZ, '..', 'server');
  return new ServidorLocal({
    pastaDados,
    comando: process.env.ACBR_DESKTOP_PYTHON || acharPython(),
    argumentos: [path.join(pastaServer, 'windows', 'servico.py')],
    ambienteExtra: { PYTHONPATH: pastaServer },
  });
}

function conexaoAtiva() {
  const p = prefs.ler();
  return p.modo === 'remoto' ? p.remoto : servidor.conexao();
}

// ── janela e bandeja ─────────────────────────────────────────────────────────
function mostrar() {
  if (!janela) criarJanela(true);
  if (janela.isMinimized()) janela.restore();
  janela.show();
  janela.focus();
}

function criarJanela(mostrarAoAbrir = !OCULTO) {
  janela = new BrowserWindow({
    width: 1100,
    height: 760,
    minWidth: 860,
    minHeight: 580,
    show: false,
    title: 'Comunicador Fiscal',
    icon: recurso('icone.png'),
    autoHideMenuBar: true,
    backgroundColor: '#f4f5f7',
    webPreferences: {
      preload: path.join(__dirname, '..', 'preload', 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });
  janela.removeMenu();
  janela.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  janela.webContents.on('will-navigate', (evento) => evento.preventDefault());
  janela.once('ready-to-show', () => mostrarAoAbrir && janela.show());
  janela.on('close', (evento) => {
    if (saindo) return;
    evento.preventDefault();
    janela.hide();
    avisarQueFicouNaBandeja();
  });
  janela.on('closed', () => {
    janela = null;
  });
  if (URL_DEV) janela.loadURL(URL_DEV);
  else janela.loadFile(path.join(RAIZ, 'build', 'index.html'));
}

function avisarQueFicouNaBandeja() {
  if (prefs.ler().avisouBandeja) return;
  prefs.salvar({ avisouBandeja: true });
  bandeja?.displayBalloon({
    title: 'Comunicador Fiscal continua ativo',
    content: 'Ele segue emitindo em segundo plano. Para encerrar, use "Sair" no ícone da bandeja.',
    iconType: 'info',
  });
}

const DESCRICAO = { parado: 'parado', iniciando: 'iniciando…', rodando: 'ativo', erro: 'com erro' };

function descricaoDoEstado() {
  if (prefs.ler().modo === 'remoto') return 'usando comunicador remoto';
  return `comunicador local ${DESCRICAO[servidor.estado.situacao] || servidor.estado.situacao}`;
}

function atualizarBandeja() {
  if (!bandeja) return;
  bandeja.setToolTip(`Comunicador Fiscal — ${descricaoDoEstado()}`);
  bandeja.setContextMenu(
    Menu.buildFromTemplate([
      { label: 'Abrir', click: mostrar },
      { label: descricaoDoEstado(), enabled: false },
      { type: 'separator' },
      {
        label: 'Iniciar com o Windows',
        type: 'checkbox',
        enabled: EMPACOTADO,
        checked: iniciaComWindows(),
        click: (item) => {
          definirInicioComWindows(item.checked);
          atualizarBandeja();
        },
      },
      { label: 'Reiniciar comunicador local', enabled: prefs.ler().modo === 'local', click: () => servidor.reiniciar(prefs.ler().local) },
      { label: 'Abrir pasta de dados', click: () => shell.openPath(servidor.pastaDados) },
      { type: 'separator' },
      { label: 'Sair', click: () => app.quit() },
    ]),
  );
}

function criarBandeja() {
  const icone = nativeImage.createFromPath(recurso('icone.png')).resize({ width: 16, height: 16 });
  bandeja = new Tray(icone);
  bandeja.on('click', mostrar);
  atualizarBandeja();
}

// ── iniciar com o Windows ────────────────────────────────────────────────────
function itemDeInicio() {
  // O portátil se extrai numa pasta temporária: o que fica é o .exe que o usuário abriu.
  return { path: process.env.PORTABLE_EXECUTABLE_FILE || process.execPath, args: ['--oculto'] };
}

function iniciaComWindows() {
  return EMPACOTADO && app.getLoginItemSettings(itemDeInicio()).openAtLogin;
}

function definirInicioComWindows(ativo) {
  if (EMPACOTADO) app.setLoginItemSettings({ ...itemDeInicio(), openAtLogin: Boolean(ativo) });
}

// ── IPC ──────────────────────────────────────────────────────────────────────
function origemConfiavel(evento) {
  const url = evento.senderFrame?.url || '';
  return URL_DEV ? url.startsWith(URL_DEV) : url.startsWith('file://');
}

function tratar(canal, funcao) {
  ipcMain.handle(canal, async (evento, ...argumentos) => {
    if (!origemConfiavel(evento)) throw new Error('Chamada de origem desconhecida.');
    return funcao(...argumentos);
  });
}

function enderecosDaRede() {
  return Object.values(os.networkInterfaces())
    .flat()
    .filter((i) => i && i.family === 'IPv4' && !i.internal)
    .map((i) => i.address);
}

function lerAcesso() {
  const p = prefs.ler();
  return {
    modo: p.modo,
    local: { ...p.local, ...servidor.conexao(), enderecos: enderecosDaRede() },
    remoto: p.remoto,
  };
}

function validarAcesso(dados) {
  const erros = [];
  const porta = Number(dados?.local?.porta);
  if (dados?.local && !(Number.isInteger(porta) && porta >= 1024 && porta <= 65535)) {
    erros.push('A porta precisa ser um número entre 1024 e 65535.');
  }
  if (dados?.modo === 'remoto') {
    const r = dados.remoto || {};
    if (!/^https?:\/\/[^\s]+$/i.test(r.url || '')) erros.push('Informe a URL do comunicador remoto (http:// ou https://).');
    if (!r.token) erros.push('Informe o token do comunicador remoto.');
    if (Buffer.from(r.chave || '', 'base64').length !== 32) erros.push('A chave precisa ter 32 bytes em base64.');
  }
  return erros;
}

function registrarIpc() {
  tratar('estado', async () => {
    const p = prefs.ler();
    const conexao = conexaoAtiva();
    return {
      versao: app.getVersion(),
      modo: p.modo,
      url: conexao.url,
      servidorLocal: servidor.estado,
      saude: conexao.url ? await saude(conexao.url) : null,
      pastas: { dados: servidor.pastaDados, lib: servidor.pastaLib },
      lib: {
        dll: fs.existsSync(path.join(servidor.pastaLib, 'ACBrNFe64.dll')),
        schemas: fs.existsSync(path.join(servidor.pastaLib, 'Schemas')),
      },
      iniciarComWindows: iniciaComWindows(),
      podeIniciarComWindows: EMPACOTADO,
    };
  });
  tratar('log', () => servidor.linhas.slice(-200));
  tratar('config:ler', () => chamar(conexaoAtiva(), '/v1/config/ler'));
  tratar('config:emitente', (dados) => chamar(conexaoAtiva(), '/v1/config/emitente', dados));
  tratar('config:remover', (cnpj) => chamar(conexaoAtiva(), '/v1/config/emitente/remover', { cnpj }));
  tratar('config:token', async (token) => {
    const resposta = await chamar(conexaoAtiva(), '/v1/config/token', { token: token || '' });
    if (resposta.ok && resposta.corpo.token) {
      // O comunicador já só aceita o novo: o desktop passa a usá-lo também.
      if (prefs.ler().modo === 'local') servidor.trocarTokenNoEnv(resposta.corpo.token);
      else prefs.salvar({ remoto: { token: resposta.corpo.token } });
    }
    return resposta;
  });
  tratar('sefaz:status', (cnpj) => chamar(conexaoAtiva(), '/v1/status-servico', cnpj ? { cnpj } : {}));
  tratar('certificado:escolher', async () => {
    const escolha = await dialog.showOpenDialog(janela, {
      title: 'Certificado A1',
      properties: ['openFile'],
      filters: [{ name: 'Certificado A1 (.pfx, .p12)', extensions: ['pfx', 'p12'] }],
    });
    if (escolha.canceled || !escolha.filePaths[0]) return null;
    const arquivo = escolha.filePaths[0];
    if (fs.statSync(arquivo).size > TAMANHO_MAXIMO_PFX) {
      return { erro: 'O arquivo é grande demais para ser um certificado A1.' };
    }
    return { nome: path.basename(arquivo), pfx_base64: fs.readFileSync(arquivo).toString('base64') };
  });
  // A ACBrLib: baixada e conferida pelo comunicador (app/instalador.py), local ou remoto.
  tratar('lib:instalar', async ({ url, sha256 } = {}) => {
    const resposta = await chamar(conexaoAtiva(), '/v1/config/lib', { url: url || '', sha256: sha256 || '' },
      { tempoLimiteMs: 10 * 60_000 });
    // Local: o pacote fica no .env, e o comunicador o reinstala sozinho se a lib sumir.
    if (resposta.ok && url && prefs.ler().modo === 'local') {
      servidor.gravarNoEnv({ ACBRLIB_PACOTE_URL: url, ACBRLIB_SO_SHA256: sha256 || '' });
    }
    return resposta;
  });
  tratar('lib:escolher-pacote', async () => {
    if (prefs.ler().modo !== 'local') {
      return { ok: false, mensagem: 'No modo remoto, instale pela URL do pacote.' };
    }
    const escolha = await dialog.showOpenDialog(janela, {
      title: 'Pacote da ACBrLib',
      properties: ['openFile'],
      filters: [{ name: 'Pacote da ACBrLib (.zip, .tar.gz)', extensions: ['zip', 'gz', 'tgz'] }],
    });
    if (escolha.canceled || !escolha.filePaths[0]) return null;
    return servidor.instalarLibDeArquivo(escolha.filePaths[0], prefs.ler().local);
  });
  tratar('acesso:ler', lerAcesso);
  tratar('acesso:salvar', async (dados) => {
    const erros = validarAcesso(dados);
    if (erros.length) return { ok: false, erros };
    const p = prefs.salvar({
      modo: dados.modo === 'remoto' ? 'remoto' : 'local',
      local: {
        porta: Number(dados.local.porta),
        rede: Boolean(dados.local.rede),
        origens: String(dados.local.origens || '').trim(),
        simulador: Boolean(dados.local.simulador),
      },
      ...(dados.modo === 'remoto'
        ? { remoto: { url: dados.remoto.url.trim(), token: dados.remoto.token.trim(), chave: dados.remoto.chave.trim() } }
        : {}),
    });
    if (p.modo === 'local') await servidor.reiniciar(p.local);
    else await servidor.parar();
    atualizarBandeja();
    return { ok: true, acesso: lerAcesso() };
  });
  tratar('servidor:reiniciar', async () => {
    await servidor.reiniciar(prefs.ler().local);
    return servidor.estado;
  });
  tratar('pasta:abrir', (qual) => {
    const pasta = qual === 'lib' ? servidor.pastaLib : servidor.pastaDados;
    fs.mkdirSync(pasta, { recursive: true });
    return shell.openPath(pasta);
  });
  tratar('copiar', (texto) => clipboard.writeText(String(texto ?? '')));
  tratar('windows:iniciar', (ativo) => {
    definirInicioComWindows(ativo);
    atualizarBandeja();
    return iniciaComWindows();
  });
}

// ── ciclo de vida ────────────────────────────────────────────────────────────
function iniciar() {
  if (!app.requestSingleInstanceLock()) {
    app.quit(); // já aberto: a outra instância mostra a janela (second-instance)
    return;
  }
  app.on('second-instance', mostrar);
  app.on('window-all-closed', () => {}); // a janela só se esconde; quem encerra é "Sair"
  app.on('before-quit', (evento) => {
    saindo = true;
    if (encerrado || !servidor) return;
    evento.preventDefault();
    servidor.parar().finally(() => {
      encerrado = true;
      app.quit();
    });
  });

  app.whenReady().then(() => {
    prefs = new Preferencias(path.join(app.getPath('userData'), 'desktop.json'), safeStorage);
    servidor = criarServidor();
    servidor.on('estado', (estado) => {
      atualizarBandeja();
      janela?.webContents.send('servidor:estado', estado);
    });
    registrarIpc();
    criarBandeja();
    criarJanela();
    const p = prefs.ler();
    if (p.modo === 'local') servidor.iniciar(p.local);
  });
}

iniciar();
