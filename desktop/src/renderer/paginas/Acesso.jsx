import { useEffect, useState } from 'react';
import { api, Aviso, Campo, Cartao, Copiavel, Segredo, mensagemDe } from '../comum';

export default function Acesso({ atualizar }) {
  const [acesso, setAcesso] = useState(null);
  const [form, setForm] = useState(null);
  const [salvando, setSalvando] = useState(false);
  const [retorno, setRetorno] = useState(null);
  const [trocando, setTrocando] = useState(false);
  const [retornoToken, setRetornoToken] = useState(null);

  const carregar = async () => {
    const lido = await api.lerAcesso();
    setAcesso(lido);
    setForm({ ...lido });
  };
  useEffect(() => {
    carregar();
  }, []);

  if (!form) return <p className="vazio">Carregando…</p>;

  const mudar = (campo, valor) => setForm({ ...form, [campo]: valor });

  const salvar = async (evento) => {
    evento.preventDefault();
    setSalvando(true);
    setRetorno(null);
    const resposta = await api.salvarAcesso(form);
    setSalvando(false);
    if (!resposta.ok) {
      setRetorno({ tipo: 'erro', texto: resposta.erros.join(' ') });
      return;
    }
    setAcesso(resposta.acesso);
    setForm({ ...resposta.acesso });
    setRetorno({ tipo: 'ok', texto: 'Gravado. O comunicador foi reiniciado.' });
    atualizar();
  };

  const trocarToken = async () => {
    const aviso =
      'Gerar um novo token? O atual para de funcionar na hora: cada PDV que usa este comunicador ' +
      'precisa receber o novo.';
    if (!window.confirm(aviso)) return;
    setTrocando(true);
    setRetornoToken(null);
    const resposta = await api.trocarToken('');
    setTrocando(false);
    if (resposta.ok) {
      setRetornoToken({ tipo: 'ok', texto: 'Novo token gerado. Atualize os PDVs.' });
      await carregar();
    } else {
      setRetornoToken({ tipo: 'erro', texto: mensagemDe(resposta) });
    }
  };

  const enderecos = [
    `http://127.0.0.1:${acesso.porta}`,
    ...(acesso.rede ? acesso.enderecos.map((ip) => `http://${ip}:${acesso.porta}`) : []),
  ];

  return (
    <>
      <h1>Acesso e conexão</h1>
      <p className="introducao">
        O que o PDV precisa para chamar o comunicador: o endereço e o token (cabeçalho{' '}
        <code>Authorization: Bearer</code>). O emitente e o certificado ficam guardados aqui: o PDV manda só o
        documento.
      </p>

      <Cartao titulo="Para configurar o PDV">
        <dl className="dados">
          <dt>Endereço</dt>
          <dd>{enderecos.map((url) => <Copiavel key={url} valor={url} />)}</dd>
          <dt>Token</dt>
          <dd><Segredo valor={acesso.token} /></dd>
        </dl>
        <div className="linha-acoes">
          <button type="button" className="botao" onClick={trocarToken} disabled={trocando}>
            {trocando ? 'Gerando…' : 'Gerar novo token'}
          </button>
        </div>
        <Aviso tipo={retornoToken?.tipo}>{retornoToken?.texto}</Aviso>
      </Cartao>

      <form onSubmit={salvar}>
        <Cartao titulo="Comunicador">
          <div className="grade">
            <Campo rotulo="Porta">
              <input type="number" min="1024" max="65535" value={form.porta} onChange={(e) => mudar('porta', e.target.value)} />
            </Campo>
            <Campo rotulo="Origens de navegador permitidas" ajuda="Só se o PDV for uma página web. Separe por vírgula, sem curinga." largo>
              <input value={form.origens} onChange={(e) => mudar('origens', e.target.value)} placeholder="https://pdv.minhaloja.com.br" />
            </Campo>
          </div>
          <label className="caixa">
            <input type="checkbox" checked={form.rede} onChange={(e) => mudar('rede', e.target.checked)} />
            Aceitar PDVs de outros computadores da rede local
          </label>
          {form.rede && (
            <Aviso tipo="info">
              O firewall (Windows, ufw) pode pedir para liberar o comunicador. Os PDVs da rede emitem com o token, mas o
              emitente, o certificado e o token só se alteram neste computador. Na rede, o token anda sem cifra: use só
              numa rede da loja, confiável.
            </Aviso>
          )}
          <label className="caixa">
            <input type="checkbox" checked={form.simulador} onChange={(e) => mudar('simulador', e.target.checked)} />
            SEFAZ simulada (só para testes: nada é emitido de verdade, e produção é recusada)
          </label>
        </Cartao>

        <Aviso tipo={retorno?.tipo}>{retorno?.texto}</Aviso>
        <div className="rodape-form">
          <button type="submit" className="botao botao-primario" disabled={salvando}>
            {salvando ? 'Gravando…' : 'Gravar'}
          </button>
        </div>
      </form>
    </>
  );
}
