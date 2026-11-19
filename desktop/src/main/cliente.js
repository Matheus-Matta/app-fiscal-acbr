// Fala com o comunicador local como o PDV fala no modo local: token no cabeçalho e
// corpo em JSON comum (server/README.md, "Modo local").
const TEMPO_LIMITE_MS = 60_000;

function base(url) {
  return String(url || '').replace(/\/+$/, '');
}

/**
 * { ok, status, corpo }. `corpo` é o JSON da resposta; em falha de rede, `{ erro: 'sem_resposta' }`.
 * 401 e 403 voltam com a `mensagem` do comunicador.
 */
async function chamar(conexao, caminho, corpo = {}, { tempoLimiteMs = TEMPO_LIMITE_MS } = {}) {
  if (!conexao.url || !conexao.token) {
    return { ok: false, status: 0, corpo: { erro: 'conexao', mensagem: 'Conexão sem URL ou token.' } };
  }
  let resposta;
  try {
    resposta = await fetch(base(conexao.url) + caminho, {
      method: 'POST',
      headers: { Authorization: `Bearer ${conexao.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(corpo),
      signal: AbortSignal.timeout(tempoLimiteMs),
    });
  } catch (erro) {
    return { ok: false, status: 0, corpo: { erro: 'sem_resposta', mensagem: `O comunicador não respondeu (${erro.message}).` } };
  }
  const json = await resposta.json().catch(() => null);
  if (!json || typeof json !== 'object') {
    return { ok: false, status: resposta.status, corpo: { erro: 'recusado', mensagem: `Resposta ${resposta.status} inesperada.` } };
  }
  if (!resposta.ok) {
    const mensagem = json.mensagem || json.detail || `Resposta ${resposta.status}.`;
    return { ok: false, status: resposta.status, corpo: { erro: json.erro || 'recusado', ...json, mensagem } };
  }
  return { ok: true, status: resposta.status, corpo: json };
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
