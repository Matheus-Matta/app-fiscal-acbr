const { app, BrowserWindow, ipcMain, Menu } = require('electron');
const path = require('path');
const isDev = require('electron-is-dev');
const { spawn } = require('child_process');

let mainWindow;
let apiProcess;

const createWindow = () => {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, '../preload/preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  const startUrl = isDev
    ? 'http://localhost:3000'
    : `file://${path.join(__dirname, '../../build/index.html')}`;

  mainWindow.loadURL(startUrl);

  if (isDev) {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
    if (apiProcess) apiProcess.kill();
  });
};

// Iniciar API local (fiscal_acbr)
const startAPI = () => {
  // TODO: Implementar lógica de iniciar FastAPI
  // Por enquanto, a API é iniciada externamente
};

app.on('ready', () => {
  startAPI();
  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  }
});

// IPC: Login
ipcMain.handle('login', async (event, { email, password }) => {
  try {
    // TODO: Chamar API de autenticação
    return { success: true, token: 'token-here' };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

// IPC: Listar Restaurantes
ipcMain.handle('get-restaurants', async (event, token) => {
  try {
    // TODO: Chamar API para pegar restaurantes
    return { success: true, restaurants: [] };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

// IPC: Sincronizar Dados
ipcMain.handle('sync-data', async (event, { token, restaurantId }) => {
  try {
    // TODO: Sincronizar certificado, CSC, etc
    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
});
