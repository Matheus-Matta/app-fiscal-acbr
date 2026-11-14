import { useState } from 'react';

export const api = window.comunicador;

/** A frase para o operador a partir da resposta do comunicador. */
export function mensagemDe(resposta, padrao = 'Não foi possível concluir.') {
  const corpo = resposta?.corpo || {};
  return corpo.mensagem || corpo.erro || padrao;
}

export function Campo({ rotulo, ajuda, children, largo }) {
  return (
    <label className={`campo${largo ? ' campo-largo' : ''}`}>
      <span className="campo-rotulo">{rotulo}</span>
      {children}
      {ajuda && <span className="campo-ajuda">{ajuda}</span>}
    </label>
  );
}

export function Aviso({ tipo = 'info', children }) {
  if (!children) return null;
  return (
    <div className={`aviso aviso-${tipo}`} role={tipo === 'erro' ? 'alert' : 'status'}>
      {children}
    </div>
  );
}

export function Cartao({ titulo, acoes, children }) {
  return (
    <section className="cartao">
      {(titulo || acoes) && (
        <header className="cartao-topo">
          {titulo && <h2>{titulo}</h2>}
          {acoes && <div className="cartao-acoes">{acoes}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Indicador({ tipo, children }) {
  return (
    <span className={`indicador indicador-${tipo}`}>
      <span className="indicador-ponto" aria-hidden="true" />
      {children}
    </span>
  );
}

/** Um valor secreto: escondido até pedir, com botão de copiar. */
export function Segredo({ valor }) {
  const [visivel, setVisivel] = useState(false);
  const [copiado, setCopiado] = useState(false);
  const copiar = async () => {
    await api.copiar(valor);
    setCopiado(true);
    setTimeout(() => setCopiado(false), 1500);
  };
  return (
    <div className="segredo">
      <code>{valor ? (visivel ? valor : '•'.repeat(24)) : '—'}</code>
      <button type="button" className="botao-texto" onClick={() => setVisivel(!visivel)} disabled={!valor}>
        {visivel ? 'Ocultar' : 'Mostrar'}
      </button>
      <button type="button" className="botao-texto" onClick={copiar} disabled={!valor}>
        {copiado ? 'Copiado' : 'Copiar'}
      </button>
    </div>
  );
}

export function Copiavel({ valor }) {
  const [copiado, setCopiado] = useState(false);
  return (
    <div className="segredo">
      <code>{valor}</code>
      <button
        type="button"
        className="botao-texto"
        onClick={async () => {
          await api.copiar(valor);
          setCopiado(true);
          setTimeout(() => setCopiado(false), 1500);
        }}
      >
        {copiado ? 'Copiado' : 'Copiar'}
      </button>
    </div>
  );
}

export function formatarCnpj(cnpj) {
  const c = String(cnpj || '').toUpperCase().replace(/[^0-9A-Z]/g, '');
  if (c.length !== 14) return cnpj;
  return `${c.slice(0, 2)}.${c.slice(2, 5)}.${c.slice(5, 8)}/${c.slice(8, 12)}-${c.slice(12)}`;
}

export function formatarData(iso) {
  if (!iso) return '';
  const [ano, mes, dia] = iso.split('-');
  return `${dia}/${mes}/${ano}`;
}
