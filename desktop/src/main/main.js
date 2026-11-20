// Comunicador Fiscal — desktop. Um arquivo só, sem instalador (Windows: .exe portátil;
// Linux: AppImage): abre a janela de configuração e sobe o comunicador local
// (AcbrFiscal[.exe]) por baixo. Fechar a janela não encerra: ele fica na bandeja,
// emitindo para o PDV. "Sair" está no menu da bandeja.
// O comunicador roda no modo local (server/app/modo.py): o PDV usa só o token, e o
// emitente fica guardado nele. O Docker na nuvem não se configura por aqui.
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {
  app, BrowserWindow, Menu, Tray, clipboard, dialog, ipcMain, nativeImage, shell,
} = require('electron');
const { chamar, saude } = require('./cliente');
const { Preferencias } = require('./preferencias');
const { ServidorLocal } = require('./servidor');

app.setName('Comunicador Fiscal'); // antes de qualquer getPath: a pasta do usuário leva este nome

const EMPACOTADO = app.isPackaged;
const URL_DEV = process.env.ACBR_DEV_URL || '';
const RAIZ = path.join(__dirname, '..', '..');
const OCULTO = process.argv.includes('--oculto'); // aberto com o sistema: direto para a bandeja
const TAMANHO_MAXIMO_PFX = 256 * 1024;
const WINDOWS = process.platform === 'win32';
const LINUX = process.platform === 'linux';
const COMUNICADOR = WINDOWS ? 'AcbrFiscal.exe' : 'AcbrFiscal';
const NOME_LIB = WINDOWS ? 'ACBrNFe64.dll' : 'libacbrnfe64.so';
// Linux: o "iniciar com o sistema" é um atalho em ~/.config/autostart (padrão XDG).
const AUTOSTART = path.join(process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config'), 'autostart',
  'comunicador-fiscal.desktop');

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
  const nome = WINDOWS ? 'python' : 'python3';
  try {
    return execFileSync(WINDOWS ? 'where' : 'which', [nome], { encoding: 'utf8' }).split(/\r?\n/)[0].trim();
  } catch {
    return nome;
  }
}

function criarServidor() {
  const pastaDados = path.join(app.getPath('userData'), 'servidor');
  if (EMPACOTADO) {
    return new ServidorLocal({ pastaDados, comando: path.join(process.resourcesPath, 'servidor', COMUNICADOR) });
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
  return servidor.conexao();
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
  return `comunicador ${DESCRICAO[servidor.estado.situacao] || servidor.estado.situacao}`;
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
        label: WINDOWS ? 'Iniciar com o Windows' : 'Iniciar com o sistema',
        type: 'checkbox',
        enabled: PODE_INICIAR_COM_SISTEMA,
        checked: iniciaComSistema(),
        click: (item) => {
          definirInicioComSistema(item.checked);
          atualizarBandeja();
        },
      },
      { label: 'Reiniciar comunicador', click: () => servidor.reiniciar(prefs.ler().local) },
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

// ── iniciar com o sistema ────────────────────────────────────────────────────
// Windows: o item de login do Electron. Linux: um .desktop em ~/.config/autostart, que o
// GNOME, o KDE, o XFCE e o Cinnamon abrem ao entrar (o Electron não faz isso no Linux).
const PODE_INICIAR_COM_SISTEMA = EMPACOTADO && (WINDOWS || LINUX);

function itemDeInicio() {
  // O portátil/AppImage roda de uma pasta temporária: o que fica é o arquivo que o usuário abriu.
  return {
    path: process.env.PORTABLE_EXECUTABLE_FILE || process.env.APPIMAGE || process.execPath,
    args: ['--oculto'],
  };
}

/** Um argumento do Exec= de um .desktop: entre aspas, com ", `, $ e \ escapados (especificação XDG). */
function argumentoDesktop(valor) {
  return `"${String(valor).replace(/(["`$\\])/g, '\\$1')}"`;
}

function iniciaComSistema() {
  if (!PODE_INICIAR_COM_SISTEMA) return false;
  if (LINUX) return fs.existsSync(AUTOSTART);
  return app.getLoginItemSettings(itemDeInicio()).openAtLogin;
}

function definirInicioComSistema(ativo) {
  if (!PODE_INICIAR_COM_SISTEMA) return;
  if (WINDOWS) {
    app.setLoginItemSettings({ ...itemDeInicio(), openAtLogin: Boolean(ativo) });
    return;
  }
  if (!ativo) {
    fs.rmSync(AUTOSTART, { force: true });
    return;
  }
  const { path: executavel, args } = itemDeInicio();
  fs.mkdirSync(path.dirname(AUTOSTART), { recursive: true });
  fs.writeFileSync(
    AUTOSTART,
    [
      '[Desktop Entry]',
      'Type=Application',
      'Name=Comunicador Fiscal',
      `Exec=${[executavel, ...args].map(argumentoDesktop).join(' ')}`,
      'X-GNOME-Autostart-enabled=true',
      'Terminal=false',
      '',
    ].join('\n'),
  );
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
  return { ...prefs.ler().local, ...servidor.conexao(), enderecos: enderecosDaRede() };
}

function validarAcesso(dados) {
  const porta = Number(dados?.porta);
  return Number.isInteger(porta) && porta >= 1024 && porta <= 65535
    ? []
    : ['A porta precisa ser um número entre 1024 e 65535.'];
}

function registrarIpc() {
  tratar('estado', async () => {
    const conexao = conexaoAtiva();
    return {
      versao: app.getVersion(),
      url: conexao.url,
      servidorLocal: servidor.estado,
      saude: conexao.url ? await saude(conexao.url) : null,
      pastas: { dados: servidor.pastaDados, lib: servidor.pastaLib },
      lib: {
        dll: fs.existsSync(path.join(servidor.pastaLib, NOME_LIB)),
        nome: NOME_LIB,
        schemas: fs.existsSync(path.join(servidor.pastaLib, 'Schemas')),
      },
      iniciarComSistema: iniciaComSistema(),
      podeIniciarComSistema: PODE_INICIAR_COM_SISTEMA,
      windows: WINDOWS,
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
      servidor.trocarTokenNoEnv(resposta.corpo.token);
    }
    return resposta;
  });
  // UF, ambiente e modelo não ficam guardados: o teste os informa, como o PDV na emissão.
  tratar('sefaz:status', ({ cnpj, uf, ambiente, modelo } = {}) =>
    chamar(conexaoAtiva(), '/v1/status-servico', { ...(cnpj ? { cnpj } : {}), uf, ambiente, modelo }));
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
  // A ACBrLib: baixada e conferida pelo comunicador (app/instalador.py).
  tratar('lib:instalar', async ({ url, sha256 } = {}) => {
    const resposta = await chamar(conexaoAtiva(), '/v1/config/lib', { url: url || '', sha256: sha256 || '' },
      { tempoLimiteMs: 10 * 60_000 });
    // O pacote fica no .env, e o comunicador o reinstala sozinho se a lib sumir.
    if (resposta.ok && url) {
      servidor.gravarNoEnv({ ACBRLIB_PACOTE_URL: url, ACBRLIB_SO_SHA256: sha256 || '' });
    }
    return resposta;
  });
  tratar('lib:escolher-pacote', async () => {
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
      local: {
        porta: Number(dados.porta),
        rede: Boolean(dados.rede),
        origens: String(dados.origens || '').trim(),
        simulador: Boolean(dados.simulador),
      },
    });
    await servidor.reiniciar(p.local);
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
  tratar('sistema:iniciar', (ativo) => {
    definirInicioComSistema(ativo);
    atualizarBandeja();
    return iniciaComSistema();
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
    prefs = new Preferencias(path.join(app.getPath('userData'), 'desktop.json'));
    servidor = criarServidor();
    servidor.on('estado', (estado) => {
      atualizarBandeja();
      janela?.webContents.send('servidor:estado', estado);
    });
    registrarIpc();
    criarBandeja();
    criarJanela();
    servidor.iniciar(prefs.ler().local);
  });
}

iniciar();
