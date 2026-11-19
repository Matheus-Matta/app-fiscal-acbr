// Gera o comunicador que o desktop embute, no sistema em que roda:
//   Windows: server/windows/gerar.ps1 -SoExe  → server/windows/saida/AcbrFiscal (com windows/lib)
//   Linux:   server/linux/gerar.sh            → server/linux/saida/AcbrFiscal   (com embutida/)
const { spawnSync } = require('node:child_process');
const path = require('node:path');

const server = path.join(__dirname, '..', '..', 'server');
const [comando, argumentos] = process.platform === 'win32'
  ? ['powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', path.join(server, 'windows', 'gerar.ps1'), '-SoExe']]
  : ['bash', [path.join(server, 'linux', 'gerar.sh')]];

const resultado = spawnSync(comando, argumentos, { stdio: 'inherit' });
process.exit(resultado.status ?? 1);
