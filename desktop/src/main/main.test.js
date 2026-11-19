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

const CHAVE = Buffer.alloc(32, 'e').toString('base64');

function pastaTemporaria() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'comunicador-'));
}

/** Um comunicador de mentira: anota o pedido e responde `status` com `corpo`. */
async function comunicadorFalso(status, corpo) {
  const recebido = {};
  const servidor = http.createServer((req, res) => {
    let texto = '';
    req.on('data', (d) => { texto += d; });
    req.on('end', () => {
      Object.assign(recebido, { url: req.url, autorizacao: req.headers.authorization, corpo: texto });
      res.writeHead(status, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(corpo));
    });
  });
  await new Promise((r) => servidor.listen(0, '127.0.0.1', r));
  return { servidor, recebido, url: `http://127.0.0.1:${servidor.address().port}` };
}

// ── o cliente: modo local, JSON comum com o token ────────────────────────────
test('chama com o token no cabeçalho e o corpo em JSON comum', async () => {
  const { servidor, recebido, url } = await comunicadorFalso(200, { situacao: 'autorizada' });
  const r = await chamar({ url, token: 'tok' }, '/v1/nfe/emitir', { ini: 'x' });
  servidor.close();
  assert.equal(r.ok, true);
  assert.deepEqual(r.corpo, { situacao: 'autorizada' });
  assert.equal(recebido.url, '/v1/nfe/emitir');
  assert.equal(recebido.autorizacao, 'Bearer tok');
  assert.deepEqual(JSON.parse(recebido.corpo), { ini: 'x' });
});

test('sem token não chama', async () => {
  const r = await chamar({ url: 'http://127.0.0.1:1', token: '' }, '/v1/config/ler');
  assert.equal(r.ok, false);
  assert.equal(r.corpo.erro, 'conexao');
});

test('recusa volta com a mensagem do comunicador', async () => {
  const { servidor, url } = await comunicadorFalso(403, { detail: 'A configuração só pode ser alterada no computador do comunicador.' });
  const r = await chamar({ url, token: 't' }, '/v1/config/emitente');
  servidor.close();
  assert.equal(r.ok, false);
  assert.equal(r.status, 403);
  assert.match(r.corpo.mensagem, /computador do comunicador/);
});

test('erro fiscal mantém erro e motivo', async () => {
  const { servidor, url } = await comunicadorFalso(500, { erro: 'configuracao', motivo: 'senha_invalida', mensagem: 'Senha.' });
  const r = await chamar({ url, token: 't' }, '/v1/status-servico');
  servidor.close();
  assert.equal(r.ok, false);
  assert.equal(r.corpo.erro, 'configuracao');
  assert.equal(r.corpo.motivo, 'senha_invalida');
});

test('comunicador fora vira sem_resposta', async () => {
  const r = await chamar({ url: 'http://127.0.0.1:1', token: 't' }, '/v1/status-servico', {}, { tempoLimiteMs: 2000 });
  assert.equal(r.ok, false);
  assert.equal(r.corpo.erro, 'sem_resposta');
});

// ── o .env ───────────────────────────────────────────────────────────────────
test('o .env é lido como o servico.py lê, sem cortar o "=" do base64', () => {
  const arquivo = path.join(pastaTemporaria(), '.env');
  gravarEnv(arquivo, { ACBRLIB_TOKEN: 'abc', ACBR_CHAVE_COFRE: CHAVE });
  assert.deepEqual(lerEnv(arquivo), { ACBRLIB_TOKEN: 'abc', ACBR_CHAVE_COFRE: CHAVE });
});

test('.env salvo com BOM (Bloco de Notas) não perde a primeira variável', () => {
  const arquivo = path.join(pastaTemporaria(), '.env');
  fs.writeFileSync(arquivo, '﻿ACBRLIB_TOKEN=abc\nACBR_PORT=9000\n', 'utf8');
  assert.deepEqual(lerEnv(arquivo), { ACBRLIB_TOKEN: 'abc', ACBR_PORT: '9000' });
});

test('na primeira vez gera token e chave do cofre no modo local, e depois os mantém', () => {
  const servidor = new ServidorLocal({ pastaDados: pastaTemporaria(), comando: 'x' });
  const primeiro = servidor.garantirEnv({ porta: 8123 });
  assert.equal(primeiro.ACBR_MODO, 'local');
  assert.ok(primeiro.ACBRLIB_TOKEN.length >= 32);
  assert.equal(Buffer.from(primeiro.ACBR_CHAVE_COFRE, 'base64').length, 32);
  assert.equal(primeiro.ACBR_E2E_KEY, undefined);
  assert.equal(primeiro.ACBR_HOST, '127.0.0.1');
  const segundo = servidor.garantirEnv({ rede: true });
  assert.equal(segundo.ACBRLIB_TOKEN, primeiro.ACBRLIB_TOKEN);
  assert.equal(segundo.ACBR_CHAVE_COFRE, primeiro.ACBR_CHAVE_COFRE);
  assert.equal(segundo.ACBR_PORT, '8123');
  assert.equal(segundo.ACBR_HOST, '0.0.0.0');
  assert.deepEqual(servidor.conexao(), { url: 'http://127.0.0.1:8123', token: primeiro.ACBRLIB_TOKEN });
});

test('a chave E2E de uma versão anterior vira a chave do cofre', () => {
  const pasta = pastaTemporaria();
  gravarEnv(path.join(pasta, '.env'), { ACBRLIB_TOKEN: 'antigo', ACBR_E2E_KEY: CHAVE, ACBRLIB_PACOTE_URL: 'https://x' });
  const valores = new ServidorLocal({ pastaDados: pasta, comando: 'x' }).garantirEnv();
  assert.equal(valores.ACBR_CHAVE_COFRE, CHAVE);
  assert.equal(valores.ACBRLIB_TOKEN, 'antigo');
  assert.equal(valores.ACBRLIB_PACOTE_URL, 'https://x');
  assert.equal(lerEnv(path.join(pasta, '.env')).ACBR_E2E_KEY, undefined);
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
test('preferências antigas com modo remoto ficam só com o local, sem segredo', () => {
  const arquivo = path.join(pastaTemporaria(), 'desktop.json');
  fs.writeFileSync(arquivo, JSON.stringify({ modo: 'remoto', remoto: { token: 'tok-secreto' }, local: { porta: 9000 } }));
  const prefs = new Preferencias(arquivo);
  assert.deepEqual(prefs.ler(), { local: { porta: 9000, rede: false, origens: '', simulador: false }, avisouBandeja: false });
  prefs.salvar({ local: { rede: true } });
  const gravado = fs.readFileSync(arquivo, 'utf8');
  assert.ok(!gravado.includes('tok-secreto') && !gravado.includes('remoto'));
  assert.equal(prefs.ler().local.rede, true);
});
