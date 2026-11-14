// Fala com o comunicador (o local, embutido, ou um Docker remoto) como o PDV fala:
// token no cabeçalho e corpo cifrado de ponta a ponta.
const { selarPedido, abrirResposta, envelopeDeResposta } = require('./sigilo');

const TEMPO_LIMITE_MS = 60_000;

function base(url) {
  return String(url || '').replace(/\/+$/, '');
}

/**
 * { ok, status, corpo }. `corpo` é o JSON aberto; em falha de rede, `{ erro: 'sem_resposta' }`.
 * Resposta sem envelope (401, 403, erro de sigilo) volta como veio: não traz decisão fiscal.
 */
async function chamar(conexao, caminho, corpo = {}, { tempoLimiteMs = TEMPO_LIMITE_MS } = {}) {
  if (!conexao.url || !conexao.token || !conexao.chave) {
    return { ok: false, status: 0, corpo: { erro: 'conexao', mensagem: 'Conexão sem URL, token ou chave.' } };
  }
  let selado;
  try {
    selado = selarPedido(JSON.stringify(corpo), 'POST', caminho, conexao.chave);
  } catch (erro) {
    return { ok: false, status: 0, corpo: { erro: 'conexao', mensagem: erro.message } };
  }
  let resposta;
  try {
    resposta = await fetch(base(conexao.url) + caminho, {
      method: 'POST',
      headers: { Authorization: `Bearer ${conexao.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(selado.envelope),
      signal: AbortSignal.timeout(tempoLimiteMs),
    });
  } catch (erro) {
    return { ok: false, status: 0, corpo: { erro: 'sem_resposta', mensagem: `O comunicador não respondeu (${erro.message}).` } };
  }
  const json = await resposta.json().catch(() => null);
  if (!envelopeDeResposta(json)) {
    const mensagem = json?.mensagem || json?.detail || `Resposta ${resposta.status} sem cifra.`;
    return { ok: false, status: resposta.status, corpo: { erro: json?.erro || 'recusado', ...json, mensagem } };
  }
  try {
    const aberto = JSON.parse(abrirResposta(json, resposta.status, selado.nonce, conexao.chave));
    return { ok: resposta.ok, status: resposta.status, corpo: aberto };
  } catch {
    return {
      ok: false,
      status: resposta.status,
      corpo: { erro: 'sigilo', mensagem: 'A resposta não abriu com a chave: ela não veio deste comunicador.' },
    };
  }
}

/** O /health, aberto e sem segredo. */
async function saude(url) {
  try {
    const resposta = await fetch(`${base(url)}/health`, { signal: AbortSignal.timeout(3000) });
    return { alcancado: true, status: resposta.status, ...(await resposta.json().catch(() => ({}))) };
  } catch (erro) {
    return { alcancado: false, mensagem: erro.message };
  }
}

module.exports = { chamar, saude };
