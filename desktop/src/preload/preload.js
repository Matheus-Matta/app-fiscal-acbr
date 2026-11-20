// A ponte da página para o processo principal. A página não tem Node nem rede:
// tudo passa por aqui, por canais fixos.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('comunicador', {
  estado: () => ipcRenderer.invoke('estado'),
  log: () => ipcRenderer.invoke('log'),
  lerConfig: () => ipcRenderer.invoke('config:ler'),
  salvarEmitente: (dados) => ipcRenderer.invoke('config:emitente', dados),
  removerEmitente: (cnpj) => ipcRenderer.invoke('config:remover', cnpj),
  trocarToken: (token) => ipcRenderer.invoke('config:token', token),
  statusSefaz: (dados) => ipcRenderer.invoke('sefaz:status', dados),
  escolherCertificado: () => ipcRenderer.invoke('certificado:escolher'),
  instalarLib: (dados) => ipcRenderer.invoke('lib:instalar', dados),
  instalarLibDeArquivo: () => ipcRenderer.invoke('lib:escolher-pacote'),
  lerAcesso: () => ipcRenderer.invoke('acesso:ler'),
  salvarAcesso: (dados) => ipcRenderer.invoke('acesso:salvar', dados),
  reiniciarServidor: () => ipcRenderer.invoke('servidor:reiniciar'),
  abrirPasta: (qual) => ipcRenderer.invoke('pasta:abrir', qual),
  copiar: (texto) => ipcRenderer.invoke('copiar', texto),
  iniciarComSistema: (ativo) => ipcRenderer.invoke('sistema:iniciar', ativo),
  aoMudarServidor: (funcao) => {
    const ouvinte = (_evento, estado) => funcao(estado);
    ipcRenderer.on('servidor:estado', ouvinte);
    return () => ipcRenderer.removeListener('servidor:estado', ouvinte);
  },
});
