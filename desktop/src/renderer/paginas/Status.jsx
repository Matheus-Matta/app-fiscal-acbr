import { useEffect, useState } from 'react';
import { api, Aviso, Campo, Cartao, Indicador, mensagemDe } from '../comum';

const MOTOR = { acbrlib: 'ACBrLib', simulador: 'SEFAZ simulada', ausente: 'ACBrLib não instalada' };
const SITUACAO = { parado: 'Parado', iniciando: 'Iniciando', rodando: 'Rodando', erro: 'Com erro' };
const UFS = ['AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA', 'PB', 'PE', 'PI',
  'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO'];

/** A ACBrLib: o comunicador a baixa, confere o SHA-256 e instala sozinho (server/app/instalador.py). */
function Biblioteca({ estado, atualizar, lib }) {
  const alcancado = Boolean(estado.saude?.alcancado);
  const carregada = Boolean(estado.saude?.lib);
  const [info, setInfo] = useState(null);
  const [url, setUrl] = useState('');
  const [sha, setSha] = useState('');
  const [trabalhando, setTrabalhando] = useState('');
  const [retorno, setRetorno] = useState(null);

  useEffect(() => {
    if (!alcancado) return;
    api.lerConfig().then((resposta) => {
      if (!resposta.ok) return;
      setInfo(resposta.corpo.lib);
      setUrl((atual) => atual || resposta.corpo.lib.pacote_url || '');
      setSha((atual) => atual || resposta.corpo.lib.sha256 || '');
    });
  }, [alcancado, carregada]);

  const instalar = async () => {
    setTrabalhando('baixando');
    setRetorno(null);
    const resposta = await api.instalarLib({ url: url.trim(), sha256: sha.trim() });
    setTrabalhando('');
    setRetorno(resposta.ok
      ? { tipo: 'ok', texto: `${resposta.corpo.mensagem} Conferida pelo SHA-256.` }
      : { tipo: 'erro', texto: mensagemDe(resposta) });
    atualizar();
  };

  const escolher = async () => {
    setTrabalhando('arquivo');
    setRetorno(null);
    const resultado = await api.instalarLibDeArquivo();
    setTrabalhando('');
    if (!resultado) return;
    setRetorno(resultado.ok
      ? { tipo: 'ok', texto: `${resultado.mensagem} SHA-256 da lib: ${resultado.sha256}` }
      : { tipo: 'erro', texto: resultado.mensagem });
    atualizar();
  };

  return (
    <Cartao
      titulo="Biblioteca ACBr"
      acoes={<button type="button" className="botao" onClick={() => api.abrirPasta('lib')}>Abrir pasta</button>}
    >
      {carregada ? (
        <Aviso tipo="ok">ACBrLib carregada: o comunicador assina e transmite de verdade.</Aviso>
      ) : (
        <>
          {info?.situacao === 'instalando' && <Aviso tipo="info">Baixando e instalando a ACBrLib…</Aviso>}
          {info?.situacao === 'falhou' && <Aviso tipo="erro">A instalação automática falhou: {info.mensagem}</Aviso>}
          <p className="nota">
            A ACBrLib (Projeto ACBr) é baixada, conferida pelo SHA-256 e instalada pelo próprio comunicador. Informe o
            endereço do pacote (.zip ou .tar.gz, link do MediaFire aceito) e o SHA-256 da lib, ou escolha um pacote já
            baixado neste computador.
          </p>
          <div className="grade">
            <Campo rotulo="Endereço do pacote" largo>
              <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…/acbrlib-windows-x64.zip" />
            </Campo>
            <Campo rotulo="SHA-256 da lib" ajuda="Sem ele o download não é aceito: é o que garante que a lib é a certa." largo>
              <input value={sha} onChange={(e) => setSha(e.target.value)} placeholder="64 caracteres hexadecimais" />
            </Campo>
          </div>
          <div className="linha-acoes acoes-lib">
            <button type="button" className="botao botao-primario" onClick={instalar}
              disabled={Boolean(trabalhando) || !alcancado || !url.trim() || !sha.trim()}>
              {trabalhando === 'baixando' ? 'Baixando e conferindo…' : 'Baixar e instalar'}
            </button>
            <button type="button" className="botao" onClick={escolher} disabled={Boolean(trabalhando)}>
              {trabalhando === 'arquivo' ? 'Instalando…' : 'Escolher pacote no computador…'}
            </button>
          </div>
        </>
      )}
      <Aviso tipo={retorno?.tipo}>{retorno?.texto}</Aviso>
      {/* Só quando falta: carregada, ela pode ser a que vem dentro do .exe, e não a desta pasta. */}
      {!carregada && (
        <>
          <ul className="lista-conferencia">
            <li className={lib.dll ? 'ok' : 'falta'}>
              {lib.nome}{estado.windows ? ' e as DLLs que a acompanham' : ' (e a libxml2 e a OpenSSL do sistema)'}
            </li>
            <li className={lib.schemas ? 'ok' : 'falta'}>Pasta Schemas (Schemas/NFe da distribuição da ACBr)</li>
          </ul>
          <p className="nota">Pasta: <code>{estado.pastas.lib}</code></p>
        </>
      )}
    </Cartao>
  );
}

export default function Status({ estado, atualizar }) {
  const [teste, setTeste] = useState(null);
  const [testando, setTestando] = useState(false);
  // Não ficam guardados no comunicador: no PDV, vêm em cada emissão.
  const [dadosTeste, setDadosTeste] = useState({ uf: 'SP', ambiente: '2', modelo: '65' });
  const mudarTeste = (campo) => (e) => setDadosTeste({ ...dadosTeste, [campo]: e.target.value });
  const [linhas, setLinhas] = useState([]);
  const [reiniciando, setReiniciando] = useState(false);

  const lerLog = async () => setLinhas(await api.log());
  useEffect(() => {
    lerLog();
  }, [estado?.servidorLocal?.situacao]);

  const testarSefaz = async () => {
    setTestando(true);
    setTeste(await api.statusSefaz(dadosTeste));
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
          <button type="button" className="botao" onClick={reiniciar} disabled={reiniciando}>
            {reiniciando ? 'Reiniciando…' : 'Reiniciar'}
          </button>
        }
      >
        <dl className="dados">
          <dt>Modo</dt>
          <dd>Local, neste computador (o PDV usa só o token)</dd>
          <dt>Endereço</dt>
          <dd><code>{estado.url || '—'}</code></dd>
          <dt>Processo</dt>
          <dd>
            <Indicador tipo={servidorLocal.situacao === 'rodando' ? 'ok' : servidorLocal.situacao === 'erro' ? 'erro' : 'alerta'}>
              {SITUACAO[servidorLocal.situacao] || servidorLocal.situacao}
            </Indicador>
          </dd>
          <dt>Emissão</dt>
          <dd>
            {saude?.alcancado ? (
              <Indicador tipo={saude.ok && !saude.simulador ? 'ok' : 'alerta'}>{MOTOR[saude.motor] || saude.motor}</Indicador>
            ) : (
              <Indicador tipo="erro">Sem resposta</Indicador>
            )}
          </dd>
        </dl>
        <Aviso tipo="erro">{servidorLocal.situacao === 'erro' && servidorLocal.mensagem}</Aviso>
        <Aviso tipo="alerta">{saude?.alcancado && saude.mensagem}</Aviso>
        <Aviso tipo="alerta">
          {saude?.simulador && 'SEFAZ simulada: nada é emitido de verdade. Desligue em "Acesso e conexão" antes de usar na loja.'}
        </Aviso>
      </Cartao>

      <Biblioteca estado={estado} atualizar={atualizar} lib={lib} />

      <Cartao
        titulo="SEFAZ"
        acoes={
          <button type="button" className="botao" onClick={testarSefaz} disabled={testando || !saude?.alcancado}>
            {testando ? 'Consultando…' : 'Testar comunicação'}
          </button>
        }
      >
        <p className="nota">
          Consulta o status do serviço da SEFAZ com o certificado guardado. UF, ambiente e modelo não ficam guardados:
          informe-os aqui, como o PDV faz em cada emissão.
        </p>
        <div className="grade">
          <Campo rotulo="UF">
            <select value={dadosTeste.uf} onChange={mudarTeste('uf')}>
              {UFS.map((uf) => <option key={uf}>{uf}</option>)}
            </select>
          </Campo>
          <Campo rotulo="Ambiente">
            <select value={dadosTeste.ambiente} onChange={mudarTeste('ambiente')}>
              <option value="2">Homologação (testes)</option>
              <option value="1">Produção</option>
            </select>
          </Campo>
          <Campo rotulo="Documento">
            <select value={dadosTeste.modelo} onChange={mudarTeste('modelo')}>
              <option value="65">NFC-e (modelo 65)</option>
              <option value="55">NF-e (modelo 55)</option>
            </select>
          </Campo>
        </div>
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
            checked={estado.iniciarComSistema}
            disabled={!estado.podeIniciarComSistema}
            onChange={async (e) => {
              await api.iniciarComSistema(e.target.checked);
              atualizar();
            }}
          />
          {estado.windows ? 'Iniciar com o Windows' : 'Iniciar com o sistema'} (direto na bandeja, sem abrir a janela)
        </label>
        <p className="nota">
          Fechar a janela não encerra o comunicador: ele continua no ícone da bandeja
          {estado.windows ? ', perto do relógio' : ' (no GNOME, precisa da extensão AppIndicator)'}. Para encerrar,
          clique com o botão direito no ícone e escolha Sair.
        </p>
      </Cartao>

      <Cartao
        titulo="Registro do comunicador"
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
    </>
  );
}
