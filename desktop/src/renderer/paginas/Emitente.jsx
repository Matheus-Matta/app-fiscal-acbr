import { useCallback, useEffect, useState } from 'react';
import { api, Aviso, Campo, Cartao, formatarCnpj, formatarData, mensagemDe } from '../comum';

// Só os segredos se configuram aqui. UF, ambiente, modelo, fuso, regime e CST vêm
// do PDV em cada emissão.
const VAZIO = { cnpj: '', senha: '', cscId: '', cscToken: '' };

function formDe(emitente) {
  if (!emitente) return { ...VAZIO };
  return {
    ...VAZIO,
    cnpj: formatarCnpj(emitente.cnpj),
    cscId: emitente.csc.id,
  };
}

function SituacaoDoCertificado({ certificado }) {
  if (!certificado?.presente) return <Aviso tipo="alerta">Nenhum certificado guardado.</Aviso>;
  if (certificado.erro) return <Aviso tipo="erro">Certificado guardado: {certificado.erro}</Aviso>;
  const dias = Math.ceil((new Date(`${certificado.vence_em}T23:59:59`) - new Date()) / 86_400_000);
  const tipo = certificado.vencido ? 'erro' : dias <= 30 ? 'alerta' : 'ok';
  return (
    <Aviso tipo={tipo}>
      <strong>{certificado.titular || 'Certificado A1'}</strong>
      <br />
      {certificado.vencido
        ? `Venceu em ${formatarData(certificado.vence_em)}.`
        : `Válido até ${formatarData(certificado.vence_em)} (${dias} dias).`}
    </Aviso>
  );
}

export default function Emitente({ estado }) {
  const [config, setConfig] = useState(null);
  const [erroAoLer, setErroAoLer] = useState('');
  const [selecionado, setSelecionado] = useState(null); // cnpj do emitente em edição; null = novo
  const [form, setForm] = useState({ ...VAZIO });
  const [arquivo, setArquivo] = useState(null);
  const [salvando, setSalvando] = useState(false);
  const [retorno, setRetorno] = useState(null);

  const aplicar = useCallback((resumo, cnpj) => {
    setConfig(resumo);
    const emitente = resumo.emitentes.find((e) => e.cnpj === cnpj) || resumo.emitentes[0] || null;
    setSelecionado(emitente?.cnpj || null);
    setForm(formDe(emitente));
    setArquivo(null);
  }, []);

  const carregar = useCallback(async () => {
    const resposta = await api.lerConfig();
    if (!resposta.ok) {
      setErroAoLer(mensagemDe(resposta, 'O comunicador não respondeu.'));
      return;
    }
    setErroAoLer('');
    aplicar(resposta.corpo, selecionado);
  }, [aplicar, selecionado]);

  const alcancado = Boolean(estado?.saude?.alcancado);
  useEffect(() => {
    if (alcancado && !config) carregar();
  }, [alcancado, config, carregar]);

  const atual = config?.emitentes.find((e) => e.cnpj === selecionado) || null;
  const mudar = (campo) => (e) => setForm({ ...form, [campo]: e.target.value });

  const escolherArquivo = async () => {
    const escolhido = await api.escolherCertificado();
    if (escolhido?.erro) setRetorno({ tipo: 'erro', texto: escolhido.erro });
    else if (escolhido) setArquivo(escolhido);
  };

  const salvar = async (evento) => {
    evento.preventDefault();
    setRetorno(null);
    if (arquivo && !form.senha) {
      setRetorno({ tipo: 'erro', texto: 'Informe a senha do certificado.' });
      return;
    }
    const cscMudou = form.cscId !== (atual?.csc.id || '');
    if (!form.cscToken && cscMudou && form.cscId) {
      setRetorno({ tipo: 'erro', texto: 'Ao trocar o ID do CSC, informe também o código (token) do CSC.' });
      return;
    }
    const dados = {
      cnpj: form.cnpj,
      // null = mantém o que já está guardado
      certificado: arquivo ? { pfx_base64: arquivo.pfx_base64, senha: form.senha } : null,
      csc: form.cscToken ? { id: form.cscId, token: form.cscToken } : null,
    };
    setSalvando(true);
    const resposta = await api.salvarEmitente(dados);
    setSalvando(false);
    if (!resposta.ok) {
      setRetorno({ tipo: 'erro', texto: mensagemDe(resposta) });
      return;
    }
    const cnpj = form.cnpj.toUpperCase().replace(/[^0-9A-Z]/g, '');
    aplicar(resposta.corpo, cnpj);
    setRetorno({ tipo: 'ok', texto: 'Emitente gravado. O PDV emite enviando o documento e os dados da emissão (UF, ambiente, modelo).' });
  };

  const remover = async () => {
    if (!atual || !window.confirm(`Remover o emitente ${formatarCnpj(atual.cnpj)} e o certificado guardado?`)) return;
    const resposta = await api.removerEmitente(atual.cnpj);
    if (resposta.ok) {
      aplicar(resposta.corpo, null);
      setRetorno({ tipo: 'ok', texto: 'Emitente removido.' });
    } else {
      setRetorno({ tipo: 'erro', texto: mensagemDe(resposta) });
    }
  };

  const novo = () => {
    setSelecionado(null);
    setForm({ ...VAZIO });
    setArquivo(null);
    setRetorno(null);
  };

  if (!alcancado) {
    return (
      <>
        <h1>Emitente</h1>
        <Aviso tipo="alerta">O comunicador ainda não respondeu. Veja a página Status.</Aviso>
      </>
    );
  }
  if (erroAoLer) {
    return (
      <>
        <h1>Emitente</h1>
        <Aviso tipo="erro">{erroAoLer}</Aviso>
        <button type="button" className="botao" onClick={carregar}>Tentar de novo</button>
      </>
    );
  }
  if (!config) return <p className="vazio">Carregando…</p>;

  const editando = Boolean(atual);
  return (
    <>
      <h1>Emitente</h1>
      <p className="introducao">
        Aqui ficam só os segredos do emitente — certificado A1, senha e CSC —, guardados e cifrados no comunicador.
        UF, ambiente, modelo, fuso, regime e CST vêm do PDV em cada emissão. Sem internet, a nota sai em contingência
        offline aqui mesmo.
      </p>

      {config.emitentes.length > 0 && (
        <div className="abas">
          {config.emitentes.map((e) => (
            <button
              key={e.cnpj}
              type="button"
              className={e.cnpj === selecionado ? 'ativo' : ''}
              onClick={() => {
                setSelecionado(e.cnpj);
                setForm(formDe(e));
                setArquivo(null);
                setRetorno(null);
              }}
            >
              {formatarCnpj(e.cnpj)}
            </button>
          ))}
          <button type="button" className={selecionado ? '' : 'ativo'} onClick={novo}>+ Novo emitente</button>
        </div>
      )}

      <form onSubmit={salvar}>
        <Cartao titulo="Empresa">
          <div className="grade">
            <Campo rotulo="CNPJ" ajuda="Identifica de quem são o certificado e o CSC.">
              <input value={form.cnpj} onChange={mudar('cnpj')} required disabled={editando} placeholder="00.000.000/0000-00" />
            </Campo>
          </div>
        </Cartao>

        <Cartao titulo="Certificado digital A1">
          {editando && <SituacaoDoCertificado certificado={atual.certificado} />}
          <div className="grade">
            <Campo rotulo={editando ? 'Trocar o arquivo (.pfx)' : 'Arquivo (.pfx)'} ajuda={editando && !arquivo ? 'Sem arquivo novo, o guardado continua.' : ''}>
              <div className="arquivo">
                <button type="button" className="botao" onClick={escolherArquivo}>Escolher…</button>
                <span>{arquivo?.nome || 'Nenhum arquivo escolhido'}</span>
              </div>
            </Campo>
            <Campo rotulo="Senha do certificado">
              <input type="password" value={form.senha} onChange={mudar('senha')} autoComplete="off" disabled={!arquivo} />
            </Campo>
          </div>
        </Cartao>

        <Cartao titulo="CSC (código de segurança do contribuinte)">
          <p className="nota">Obrigatório na NFC-e: gerado no portal da SEFAZ da sua UF. Vai no QR Code do cupom.</p>
          {editando && (
            <Aviso tipo={atual.csc.configurado ? 'ok' : 'alerta'}>
              {atual.csc.configurado ? `CSC guardado (ID ${atual.csc.id}).` : 'Nenhum CSC guardado.'}
            </Aviso>
          )}
          <div className="grade">
            <Campo rotulo="ID do CSC">
              <input value={form.cscId} onChange={mudar('cscId')} placeholder="ex.: 000001" />
            </Campo>
            <Campo rotulo="Código do CSC" ajuda={atual?.csc.configurado ? 'Em branco: mantém o guardado.' : ''}>
              <input type="password" value={form.cscToken} onChange={mudar('cscToken')} autoComplete="off" />
            </Campo>
          </div>
        </Cartao>

        <Aviso tipo={retorno?.tipo}>{retorno?.texto}</Aviso>
        <div className="rodape-form">
          {editando && (
            <button type="button" className="botao botao-perigo" onClick={remover}>Remover emitente</button>
          )}
          <button type="submit" className="botao botao-primario" disabled={salvando}>
            {salvando ? 'Conferindo e gravando…' : 'Gravar'}
          </button>
        </div>
      </form>
    </>
  );
}
