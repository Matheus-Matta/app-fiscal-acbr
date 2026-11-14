// A cifra de ponta a ponta do comunicador, do lado do cliente (server/app/sigilo.py e
// server/README.md, "Cifra de ponta a ponta"). AES-256-GCM, uma chave por sentido
// derivada por HKDF-SHA256 da ACBR_E2E_KEY.
const crypto = require('node:crypto');

const ROTULO = 'acbr-e2e-v1';

function derivar(chaveBase64, sentido) {
  // HKDF sem salt: o Python usa salt=None, que é o mesmo que 32 bytes zero — e uma
  // chave HMAC vazia é preenchida com zeros, então o resultado é idêntico.
  const chave = Buffer.from(chaveBase64, 'base64');
  if (chave.length !== 32) throw new Error('A chave de criptografia precisa ter 32 bytes em base64.');
  return Buffer.from(crypto.hkdfSync('sha256', chave, Buffer.alloc(0), Buffer.from(`${ROTULO} ${sentido}`), 32));
}

function selarPedido(corpo, metodo, caminho, chaveBase64, ts = Math.floor(Date.now() / 1000)) {
  const iv = crypto.randomBytes(12);
  const nonce = iv.toString('base64');
  const cifra = crypto.createCipheriv('aes-256-gcm', derivar(chaveBase64, 'pedido'), iv);
  cifra.setAAD(Buffer.from(`${ROTULO}\n${metodo}\n${caminho}\n${ts}\n${nonce}`));
  const dados = Buffer.concat([cifra.update(Buffer.from(corpo, 'utf8')), cifra.final(), cifra.getAuthTag()]);
  return { envelope: { v: 1, ts, nonce, dados: dados.toString('base64') }, nonce };
}

/** O corpo em claro. Lança erro se a resposta não veio do serviço, para este pedido e status. */
function abrirResposta(envelope, status, noncePedido, chaveBase64) {
  const bruto = Buffer.from(envelope.dados, 'base64');
  const decifra = crypto.createDecipheriv(
    'aes-256-gcm',
    derivar(chaveBase64, 'resposta'),
    Buffer.from(envelope.nonce, 'base64'),
  );
  decifra.setAAD(Buffer.from(`${ROTULO}\n${status}\n${noncePedido}`));
  decifra.setAuthTag(bruto.subarray(bruto.length - 16));
  return Buffer.concat([decifra.update(bruto.subarray(0, bruto.length - 16)), decifra.final()]).toString('utf8');
}

function envelopeDeResposta(corpo) {
  return Boolean(corpo && corpo.v === 1 && typeof corpo.nonce === 'string' && typeof corpo.dados === 'string');
}

module.exports = { selarPedido, abrirResposta, envelopeDeResposta, derivar };
