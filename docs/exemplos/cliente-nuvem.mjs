// Cliente de exemplo do Comunicador Fiscal no modo NUVEM (docs/API.md), em Node 18+.
// Só usa o que vem no Node (fetch e crypto).
//
//   ACBR_URL=https://fiscal.suaempresa.com.br ACBRLIB_TOKEN=... ACBR_E2E_KEY=... node cliente-nuvem.mjs
import crypto from 'node:crypto';

const ROTULO = 'acbr-e2e-v1';

/** Uma chave por sentido ("pedido" ou "resposta"), derivada da ACBR_E2E_KEY. */
function chave(chaveBase64, sentido) {
  // HKDF sem salt: igual a 32 bytes zero, como no servidor.
  return Buffer.from(crypto.hkdfSync('sha256', Buffer.from(chaveBase64, 'base64'), Buffer.alloc(0),
    Buffer.from(`${ROTULO} ${sentido}`), 32));
}

/** Nada confiável voltou (rede, 401, 403, 429, erro de cifra): trate como `incerto`. */
export class SemResposta extends Error {}

export async function chamar({ url, token, chaveE2e }, rota, corpo, tempoLimiteMs = 60_000) {
  const ts = Math.floor(Date.now() / 1000);
  const iv = crypto.randomBytes(12); // novo a cada tentativa: repetir um envelope dá 409
  const nonce = iv.toString('base64');
  const cifra = crypto.createCipheriv('aes-256-gcm', chave(chaveE2e, 'pedido'), iv);
  cifra.setAAD(Buffer.from(`${ROTULO}\nPOST\n${rota}\n${ts}\n${nonce}`));
  const dados = Buffer.concat([cifra.update(JSON.stringify(corpo), 'utf8'), cifra.final(), cifra.getAuthTag()]);

  let resposta;
  try {
    resposta = await fetch(url.replace(/\/+$/, '') + rota, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ v: 1, ts, nonce, dados: dados.toString('base64') }),
      signal: AbortSignal.timeout(tempoLimiteMs),
    });
  } catch (erro) {
    throw new SemResposta(`sem resposta: ${erro.message}`);
  }
  const texto = await resposta.text();
  try {
    const selado = JSON.parse(texto);
    const bruto = Buffer.from(selado.dados, 'base64');
    const decifra = crypto.createDecipheriv('aes-256-gcm', chave(chaveE2e, 'resposta'), Buffer.from(selado.nonce, 'base64'));
    decifra.setAAD(Buffer.from(`${ROTULO}\n${resposta.status}\n${nonce}`));
    decifra.setAuthTag(bruto.subarray(bruto.length - 16));
    const claro = Buffer.concat([decifra.update(bruto.subarray(0, bruto.length - 16)), decifra.final()]);
    return { status: resposta.status, corpo: JSON.parse(claro.toString('utf8')) };
  } catch {
    // Sem envelope (401, 403, 429, erro: sigilo) ou envelope que não abre: não é decisão fiscal.
    throw new SemResposta(`HTTP ${resposta.status} sem resposta cifrada: ${texto.slice(0, 200)}`);
  }
}

if (import.meta.url === `file://${process.argv[1]}` || process.argv[1]?.endsWith('cliente-nuvem.mjs')) {
  const conexao = { url: process.env.ACBR_URL, token: process.env.ACBRLIB_TOKEN, chaveE2e: process.env.ACBR_E2E_KEY };
  const contexto = { cnpj: '11222333000181', uf: 'SP', ambiente: '2', modelo: '65', fuso: '-03:00' };
  console.log(await chamar(conexao, '/v1/status-servico', contexto));
}
