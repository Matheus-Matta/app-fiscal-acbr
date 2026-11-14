import { useEffect, useState } from 'react';
import { api, Aviso, Cartao, Indicador, mensagemDe } from '../comum';

const MOTOR = { acbrlib: 'ACBrLib', simulador: 'SEFAZ simulada', ausente: 'ACBrLib não instalada' };
const SITUACAO = { parado: 'Parado', iniciando: 'Iniciando', rodando: 'Rodando', erro: 'Com erro' };

export default function Status({ estado, atualizar }) {
  const [teste, setTeste] = useState(null);
  const [testando, setTestando] = useState(false);
  const [linhas, setLinhas] = useState([]);
  const [reiniciando, setReiniciando] = useState(false);
  const local = estado?.modo === 'local';

  const lerLog = async () => setLinhas(await api.log());
  useEffect(() => {
    if (local) lerLog();
  }, [local, estado?.servidorLocal?.situacao]);

  const testarSefaz = async () => {
    setTestando(true);
    setTeste(await api.statusSefaz());
    setTestando(false);
  };

  const reiniciar = async () => {
    setReiniciando(true);
    await api.reiniciarServidor();
    setReiniciando(false);
    atualizar();
    lerLog();
  };

  if (!estado) return <p className="vazio">Carregando…</p>;
  const { saude, servidorLocal, lib } = estado;

  return (
    <>
      <h1>Status</h1>

      <Cartao
        titulo="Comunicador"
        acoes={
          local && (
            <button type="button" className="botao" onClick={reiniciar} disabled={reiniciando}>
              {reiniciando ? 'Reiniciando…' : 'Reiniciar'}
            </button>
          )
        }
      >
        <dl className="dados">
          <dt>Modo</dt>
          <dd>{local ? 'Local, neste computador' : 'Remoto (Docker)'}</dd>
          <dt>Endereço</dt>
          <dd><code>{estado.url || '—'}</code></dd>
          {local && (
            <>
              <dt>Processo</dt>
              <dd>
                <Indicador tipo={servidorLocal.situacao === 'rodando' ? 'ok' : servidorLocal.situacao === 'erro' ? 'erro' : 'alerta'}>
                  {SITUACAO[servidorLocal.situacao] || servidorLocal.situacao}
                </Indicador>
              </dd>
            </>
          )}
          <dt>Emissão</dt>
          <dd>
            {saude?.alcancado ? (
              <Indicador tipo={saude.ok && !saude.simulador ? 'ok' : 'alerta'}>{MOTOR[saude.motor] || saude.motor}</Indicador>
            ) : (
              <Indicador tipo="erro">Sem resposta</Indicador>
            )}
          </dd>
        </dl>
        <Aviso tipo="erro">{local && servidorLocal.situacao === 'erro' && servidorLocal.mensagem}</Aviso>
        <Aviso tipo="erro">{!local && saude && !saude.alcancado && `O comunicador remoto não respondeu: ${saude.mensagem}`}</Aviso>
        <Aviso tipo="alerta">{saude?.alcancado && saude.mensagem}</Aviso>
        <Aviso tipo="alerta">
          {saude?.simulador && 'SEFAZ simulada: nada é emitido de verdade. Desligue em "Acesso e conexão" antes de usar na loja.'}
        </Aviso>
      </Cartao>

      {local && (
        <Cartao
          titulo="Biblioteca ACBr"
          acoes={
            <button type="button" className="botao" onClick={() => api.abrirPasta('lib')}>
              Abrir pasta
            </button>
          }
        >
          <ul className="lista-conferencia">
            <li className={lib.dll ? 'ok' : 'falta'}>ACBrNFe64.dll e as DLLs que a acompanham</li>
            <li className={lib.schemas ? 'ok' : 'falta'}>Pasta Schemas (Schemas/NFe da distribuição da ACBr)</li>
          </ul>
          <p className="nota">
            Pasta: <code>{estado.pastas.lib}</code>
            <br />
            A biblioteca é distribuída pelo Projeto ACBr e não vem junto. Copie os arquivos para essa pasta e clique em
            Reiniciar.
          </p>
        </Cartao>
      )}

      <Cartao
        titulo="SEFAZ"
        acoes={
          <button type="button" className="botao" onClick={testarSefaz} disabled={testando || !saude?.alcancado}>
            {testando ? 'Consultando…' : 'Testar comunicação'}
          </button>
        }
      >
        <p className="nota">Consulta o status do serviço da SEFAZ com o emitente e o certificado configurados.</p>
        {teste && teste.ok && (
          <Aviso tipo={teste.corpo.online ? 'ok' : 'alerta'}>
            {teste.corpo.online ? 'SEFAZ em operação' : 'SEFAZ indisponível: as notas sairão em contingência'}
            {teste.corpo.cstat && ` (cStat ${teste.corpo.cstat}${teste.corpo.motivo ? ` — ${teste.corpo.motivo}` : ''})`}
          </Aviso>
        )}
        {teste && !teste.ok && <Aviso tipo="erro">{mensagemDe(teste)}</Aviso>}
      </Cartao>

      <Cartao titulo="Segundo plano">
        <label className="caixa">
          <input
            type="checkbox"
            checked={estado.iniciarComWindows}
            disabled={!estado.podeIniciarComWindows}
            onChange={async (e) => {
              await api.iniciarComWindows(e.target.checked);
              atualizar();
            }}
          />
          Iniciar com o Windows (direto na bandeja, sem abrir a janela)
        </label>
        <p className="nota">
          Fechar a janela não encerra o comunicador: ele continua no ícone da bandeja, perto do relógio. Para encerrar,
          clique com o botão direito no ícone e escolha Sair.
        </p>
      </Cartao>

      {local && (
        <Cartao
          titulo="Registro do comunicador local"
          acoes={
            <>
              <button type="button" className="botao-texto" onClick={lerLog}>
                Atualizar
              </button>
              <button type="button" className="botao-texto" onClick={() => api.abrirPasta('dados')}>
                Abrir pasta de dados
              </button>
            </>
          }
        >
          <pre className="registro">{linhas.length ? linhas.join('\n') : 'Nada registrado ainda.'}</pre>
        </Cartao>
      )}
    </>
  );
}
