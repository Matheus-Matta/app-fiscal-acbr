// Abre o Electron sem o ELECTRON_RUN_AS_NODE que o terminal do VS Code define:
// com ele, o electron.exe roda como Node puro e a janela nunca abre.
const { spawn } = require('node:child_process');
const electron = require('electron');

const ambiente = { ...process.env };
delete ambiente.ELECTRON_RUN_AS_NODE;
const processo = spawn(electron, ['.', ...process.argv.slice(2)], { stdio: 'inherit', env: ambiente });
processo.on('exit', (codigo) => process.exit(codigo ?? 0));
