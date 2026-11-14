// node --test src/main/  (sem Electron: só os módulos puros)
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');

const { chamar } = require('./cliente');
const { Preferencias } = require('./preferencias');
const { ServidorLocal, lerEnv, gravarEnv } = require('./servidor');
const { abrirResposta, selarPedido } = require('./sigilo');

const CHAVE = Buffer.alloc(32, 'e').toString('base64');

function pastaTemporaria() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'comunicador-'));
}

// ── a cifra ──────────────────────────────────────────────────────────────────
test('abre a resposta que o sigilo.py selou (vetor gerado pelo Python)', () => {
  const envelope = {
    v: 1,
    nonce: 'Xz/iZerrlg5Gr1jC',
    dados: 'JKm5WzedOWz2JWATIxYZIUcNtKja0irIIiGh3lvAAt2vPsQOMLhlJd49wP0p5MCUK9SK2mCSdbvPag==',
  };
  const corpo = JSON.parse(abrirResposta(envelope, 200, 'bm9uY2UtcGVkaWRv', CHAVE));
  assert.deepEqual(corpo, { situacao: 'autorizada', cstat: '100' });
});

test('resposta com o status trocado não abre', () => {
  const envelope = {
    v: 1,
    nonce: 'Xz/iZerrlg5Gr1jC',
    dados: 'JKm5WzedOWz2JWATIxYZIUcNtKja0irIIiGh3lvAAt2vPsQOMLhlJd49wP0p5MCUK9SK2mCSdbvPag==',
  };
  assert.throws(() => abrirResposta(envelope, 503, 'bm9uY2UtcGVkaWRv', CHAVE));
});

test('o pedido não leva nada em claro e cada um tem nonce novo', () => {
  const a = selarPedido('{"senha":"segredo-do-a1"}', 'POST', '/v1/nfe/emitir', CHAVE);
  const b = selarPedido('{"senha":"segredo-do-a1"}', 'POST', '/v1/nfe/emitir', CHAVE);
  assert.ok(!JSON.stringify(a.envelope).includes('segredo'));
  assert.notEqual(a.nonce, b.nonce);
  assert.equal(Buffer.from(a.nonce, 'base64').length, 12);
});

test('chave com tamanho errado é recusada antes de chamar', async () => {
  const r = await chamar({ url: 'http://127.0.0.1:1', token: 't', chave: 'curta' }, '/v1/config/ler');
  assert.equal(r.ok, false);
  assert.equal(r.corpo.erro, 'conexao');
});

test('resposta sem envelope não é tratada como decisão', async () => {
  const servidor = http.createServer((_req, res) => {
    res.writeHead(401, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ detail: 'token inválido' }));
  });
  await new Promise((r) => servidor.listen(0, '127.0.0.1', r));
  const { port } = servidor.address();
  const r = await chamar({ url: `http://127.0.0.1:${port}`, token: 't', chave: CHAVE }, '/v1/config/ler');
  servidor.close();
  assert.equal(r.ok, false);
  assert.equal(r.status, 401);
  assert.equal(r.corpo.mensagem, 'token inválido');
});

// ── o .env ───────────────────────────────────────────────────────────────────
test('o .env é lido como o servico.py lê, sem cortar o "=" do base64', () => {
  const arquivo = path.join(pastaTemporaria(), '.env');
  gravarEnv(arquivo, { ACBRLIB_TOKEN: 'abc', ACBR_E2E_KEY: CHAVE });
  assert.deepEqual(lerEnv(arquivo), { ACBRLIB_TOKEN: 'abc', ACBR_E2E_KEY: CHAVE });
});

test('na primeira vez gera token e chave, e depois os mantém', () => {
  const servidor = new ServidorLocal({ pastaDados: pastaTemporaria(), comando: 'x' });
  const primeiro = servidor.garantirEnv({ porta: 8123 });
  assert.ok(primeiro.ACBRLIB_TOKEN.length >= 32);
  assert.equal(Buffer.from(primeiro.ACBR_E2E_KEY, 'base64').length, 32);
  assert.equal(primeiro.ACBR_HOST, '127.0.0.1');
  const segundo = servidor.garantirEnv({ rede: true });
  assert.equal(segundo.ACBRLIB_TOKEN, primeiro.ACBRLIB_TOKEN);
  assert.equal(segundo.ACBR_E2E_KEY, primeiro.ACBR_E2E_KEY);
  assert.equal(segundo.ACBR_PORT, '8123');
  assert.equal(segundo.ACBR_HOST, '0.0.0.0');
  assert.deepEqual(servidor.conexao(), { url: 'http://127.0.0.1:8123', token: primeiro.ACBRLIB_TOKEN, chave: primeiro.ACBR_E2E_KEY });
});

test('com a porta ocupada não abre e explica', async () => {
  const ocupante = http.createServer();
  await new Promise((r) => ocupante.listen(0, '127.0.0.1', r));
  const servidor = new ServidorLocal({ pastaDados: pastaTemporaria(), comando: process.execPath });
  await servidor.iniciar({ porta: ocupante.address().port });
  ocupante.close();
  assert.equal(servidor.estado.situacao, 'erro');
  assert.match(servidor.estado.mensagem, /em uso/);
  assert.equal(servidor.processo, null);
});

// ── preferências ─────────────────────────────────────────────────────────────
test('token e chave do remoto vão cifrados quando o Windows oferece o cofre', () => {
  const cofre = {
    isEncryptionAvailable: () => true,
    encryptString: (s) => Buffer.from(`X${s}`),
    decryptString: (b) => b.toString().slice(1),
  };
  const arquivo = path.join(pastaTemporaria(), 'desktop.json');
  const prefs = new Preferencias(arquivo, cofre);
  prefs.salvar({ modo: 'remoto', remoto: { url: 'https://f', token: 'tok-secreto', chave: CHAVE } });
  assert.ok(!fs.readFileSync(arquivo, 'utf8').includes('tok-secreto'));
  const lido = prefs.ler();
  assert.equal(lido.modo, 'remoto');
  assert.equal(lido.remoto.token, 'tok-secreto');
  assert.equal(lido.local.porta, 8030);
});
