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
    setForm({ modo: lido.modo, local: { ...lido.local }, remoto: { ...lido.remoto } });
  };
  useEffect(() => {
    carregar();
  }, []);

  if (!form) return <p className="vazio">Carregando…</p>;

  const mudarLocal = (campo, valor) => setForm({ ...form, local: { ...form.local, [campo]: valor } });
  const mudarRemoto = (campo, valor) => setForm({ ...form, remoto: { ...form.remoto, [campo]: valor } });

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
    setForm({ modo: resposta.acesso.modo, local: { ...resposta.acesso.local }, remoto: { ...resposta.acesso.remoto } });
    setRetorno({ tipo: 'ok', texto: form.modo === 'local' ? 'Gravado. O comunicador local foi reiniciado.' : 'Gravado.' });
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

  const local = acesso.local;
  const remotoSalvo = acesso.modo === 'remoto';
  const enderecos = [`http://127.0.0.1:${local.porta}`, ...(local.rede ? local.enderecos.map((ip) => `http://${ip}:${local.porta}`) : [])];

  return (
    <>
      <h1>Acesso e conexão</h1>
      <p className="introducao">
        O que o PDV precisa para chamar o comunicador: o endereço, o token (cabeçalho Authorization) e a chave de
        criptografia das chamadas.
      </p>

      <Cartao titulo={acesso.modo === 'local' ? 'Para configurar o PDV' : 'Comunicador remoto em uso'}>
        <dl className="dados">
          <dt>Endereço</dt>
          <dd>
            {acesso.modo === 'local'
              ? enderecos.map((url) => <Copiavel key={url} valor={url} />)
              : <Copiavel valor={acesso.remoto.url} />}
          </dd>
          <dt>Token</dt>
          <dd><Segredo valor={acesso.modo === 'local' ? local.token : acesso.remoto.token} /></dd>
          <dt>Chave (ACBR_E2E_KEY)</dt>
          <dd><Segredo valor={acesso.modo === 'local' ? local.chave : acesso.remoto.chave} /></dd>
        </dl>
        <div className="linha-acoes">
          <button type="button" className="botao" onClick={trocarToken} disabled={trocando}>
            {trocando ? 'Gerando…' : 'Gerar novo token'}
          </button>
        </div>
        <Aviso tipo={retornoToken?.tipo}>{retornoToken?.texto}</Aviso>
      </Cartao>

      <form onSubmit={salvar}>
        <Cartao titulo="Qual comunicador este desktop usa">
          <div className="opcoes">
            <label className="opcao">
              <input type="radio" name="modo" checked={form.modo === 'local'} onChange={() => setForm({ ...form, modo: 'local' })} />
              <span>
                <strong>Local, neste computador</strong>
                <small>Funciona sem internet: sem SEFAZ, a nota é assinada em contingência offline aqui mesmo.</small>
              </span>
            </label>
            <label className="opcao">
              <input type="radio" name="modo" checked={form.modo === 'remoto'} onChange={() => setForm({ ...form, modo: 'remoto' })} />
              <span>
                <strong>Remoto (Docker)</strong>
                <small>Só configura um comunicador que já roda em outro lugar, com o token e a chave do .env dele.</small>
              </span>
            </label>
          </div>
        </Cartao>

        {form.modo === 'local' ? (
          <Cartao titulo="Comunicador local">
            <div className="grade">
              <Campo rotulo="Porta">
                <input type="number" min="1024" max="65535" value={form.local.porta} onChange={(e) => mudarLocal('porta', e.target.value)} />
              </Campo>
              <Campo rotulo="Origens de navegador permitidas" ajuda="Só se o PDV for uma página web. Separe por vírgula, sem curinga." largo>
                <input value={form.local.origens} onChange={(e) => mudarLocal('origens', e.target.value)} placeholder="https://pdv.minhaloja.com.br" />
              </Campo>
            </div>
            <label className="caixa">
              <input type="checkbox" checked={form.local.rede} onChange={(e) => mudarLocal('rede', e.target.checked)} />
              Aceitar PDVs de outros computadores da rede local
            </label>
            {form.local.rede && (
              <Aviso tipo="info">O Windows pode pedir para liberar o comunicador no firewall. As chamadas continuam exigindo o token e a chave.</Aviso>
            )}
            <label className="caixa">
              <input type="checkbox" checked={form.local.simulador} onChange={(e) => mudarLocal('simulador', e.target.checked)} />
              SEFAZ simulada (só para testes: nada é emitido de verdade, e produção é recusada)
            </label>
          </Cartao>
        ) : (
          <Cartao titulo="Comunicador remoto">
            <div className="grade">
              <Campo rotulo="URL" largo>
                <input value={form.remoto.url} onChange={(e) => mudarRemoto('url', e.target.value)} placeholder="https://fiscal.minhaloja.com.br" />
              </Campo>
              <Campo rotulo="Token (ACBRLIB_TOKEN)">
                <input type="password" value={form.remoto.token} onChange={(e) => mudarRemoto('token', e.target.value)} autoComplete="off" />
              </Campo>
              <Campo rotulo="Chave (ACBR_E2E_KEY)">
                <input type="password" value={form.remoto.chave} onChange={(e) => mudarRemoto('chave', e.target.value)} autoComplete="off" />
              </Campo>
            </div>
            <p className="nota">
              O token e a chave ficam guardados neste computador, cifrados pelo Windows. Com o modo remoto, o comunicador
              local fica desligado.
            </p>
          </Cartao>
        )}

        <Aviso tipo={retorno?.tipo}>{retorno?.texto}</Aviso>
        <div className="rodape-form">
          <button type="submit" className="botao botao-primario" disabled={salvando}>
            {salvando ? 'Gravando…' : remotoSalvo === (form.modo === 'remoto') ? 'Gravar' : 'Gravar e trocar de modo'}
          </button>
        </div>
      </form>
    </>
  );
}
