import { useCallback, useEffect, useRef, useState } from 'react';
import { api, Indicador } from './comum';
import Acesso from './paginas/Acesso';
import Emitente from './paginas/Emitente';
import Status from './paginas/Status';

const PAGINAS = [
  { id: 'status', titulo: 'Status', Componente: Status },
  { id: 'emitente', titulo: 'Emitente', Componente: Emitente },
  { id: 'acesso', titulo: 'Acesso e conexão', Componente: Acesso },
];

/** ok | alerta | erro, e a frase curta do estado geral. */
export function resumoDoEstado(estado) {
  if (!estado) return ['alerta', 'Carregando…'];
  const { saude, servidorLocal } = estado;
  if (servidorLocal?.situacao === 'erro') return ['erro', 'Comunicador com erro'];
  if (servidorLocal?.situacao === 'iniciando') return ['alerta', 'Iniciando…'];
  if (!saude?.alcancado) return ['erro', 'Comunicador parado'];
  if (saude.simulador) return ['alerta', 'Simulador (sem valor fiscal)'];
  if (!saude.ok) return ['alerta', 'Falta a ACBrLib'];
  return ['ok', 'Pronto para emitir'];
}

export default function App() {
  const [pagina, setPagina] = useState('status');
  const [estado, setEstado] = useState(null);
  const conferiuPrimeiroUso = useRef(false);

  const atualizar = useCallback(async () => {
    try {
      setEstado(await api.estado());
    } catch {
      /* a janela pode estar fechando */
    }
  }, []);

  useEffect(() => {
    atualizar();
    const intervalo = setInterval(atualizar, 5000);
    const parar = api.aoMudarServidor(atualizar);
    return () => {
      clearInterval(intervalo);
      parar();
    };
  }, [atualizar]);

  // Primeiro uso: sem emitente cadastrado, a tela de configuração vem primeiro.
  useEffect(() => {
    if (conferiuPrimeiroUso.current || !estado?.saude?.alcancado) return;
    conferiuPrimeiroUso.current = true;
    api.lerConfig().then((resposta) => {
      if (resposta.ok && resposta.corpo.emitentes.length === 0) setPagina('emitente');
    });
  }, [estado]);

  const [tipo, frase] = resumoDoEstado(estado);
  const { Componente } = PAGINAS.find((p) => p.id === pagina);

  return (
    <div className="app">
      <nav className="lateral">
        <div className="marca">
          <strong>Comunicador Fiscal</strong>
          <span>NFC-e / NF-e · ACBr</span>
        </div>
        <Indicador tipo={tipo}>{frase}</Indicador>
        <ul>
          {PAGINAS.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                className={p.id === pagina ? 'ativo' : ''}
                aria-current={p.id === pagina ? 'page' : undefined}
                onClick={() => setPagina(p.id)}
              >
                {p.titulo}
              </button>
            </li>
          ))}
        </ul>
        <p className="rodape">
          v{estado?.versao || '—'} · fechar a janela mantém o comunicador ativo na bandeja
        </p>
      </nav>
      <main className="conteudo">
        <Componente estado={estado} atualizar={atualizar} irPara={setPagina} />
      </main>
    </div>
  );
}
