import base64
import importlib
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import sigilo  # noqa: E402

#: A nuvem não sobe com token de menos de 32 caracteres.
TOKEN = "token-de-teste-com-32-caracteres-ou-mais"
CHAVE_E2E = base64.b64encode(b"e" * 32).decode()
CHAVE_COFRE = base64.b64encode(b"k" * 32).decode()
#: O IP de quem chama no modo local: o próprio computador.
DESTA_MAQUINA = ("127.0.0.1", 50000)


class ClienteSelado(TestClient):
    """Fala com a API como o PDV: `json=` sai cifrado e a resposta volta aberta."""

    chave = CHAVE_E2E

    def post(self, url, *, json=None, **kwargs):  # noqa: A002
        if json is None:
            return super().post(url, **kwargs)
        envelope, nonce = sigilo.selar_pedido(_texto(json), "POST", urlsplit(url).path, self.chave)
        resposta = super().post(url, json=envelope, **kwargs)
        corpo = resposta.json()
        if isinstance(corpo, dict) and set(corpo) == {"v", "nonce", "dados"}:
            resposta._content = sigilo.abrir_resposta(corpo, resposta.status_code, nonce, self.chave)
        else:
            assert resposta.status_code >= 400, "resposta de sucesso sem cifra"
        return resposta


def _texto(corpo):
    return json.dumps(corpo).encode()


@pytest.fixture(autouse=True)
def _sem_download(monkeypatch, tmp_path):
    """Nenhum teste baixa a ACBrLib de verdade: o pacote padrão fica desligado."""
    monkeypatch.setenv("ACBRLIB_PACOTE_URL", "")
    monkeypatch.setenv("ACBR_LIB_INSTALADA", str(tmp_path / "lib-instalada"))


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    """O modo nuvem: token forte e chave de ponta a ponta."""
    # A configuração guardada (emitentes, token) de cada teste fica no seu tmp_path.
    monkeypatch.setenv("ACBR_DATA_DIR", str(tmp_path / "dados"))
    monkeypatch.setenv("ACBR_MODO", "nuvem")
    monkeypatch.setenv("ACBRLIB_TOKEN", TOKEN)
    monkeypatch.setenv("ACBR_E2E_KEY", CHAVE_E2E)
    monkeypatch.delenv("ACBR_CHAVE_COFRE", raising=False)
    monkeypatch.delenv("ACBR_CONFIG_REDES", raising=False)
    monkeypatch.setenv("ACBR_ALLOWED_ORIGINS", "https://caixa.exemplo.com.br")


@pytest.fixture
def api(ambiente, monkeypatch):
    """O comunicador na nuvem, com a SEFAZ simulada, como sobe com ACBR_SIMULADOR=1."""
    monkeypatch.setenv("ACBR_SIMULADOR", "1")
    import app.main

    modulo = importlib.reload(app.main)
    cliente = ClienteSelado(modulo.app)
    cliente.headers["Authorization"] = f"Bearer {TOKEN}"
    return cliente


@pytest.fixture
def ambiente_local(ambiente, monkeypatch):
    """O modo local: só o token, e a chave do cofre dos emitentes."""
    monkeypatch.setenv("ACBR_MODO", "local")
    monkeypatch.delenv("ACBR_E2E_KEY", raising=False)
    monkeypatch.setenv("ACBR_CHAVE_COFRE", CHAVE_COFRE)


def cliente_local(client=DESTA_MAQUINA):
    """Fala com o comunicador local como o PDV: JSON comum e o token."""
    import app.main

    cliente = TestClient(app.main.app, client=client)
    cliente.headers["Authorization"] = f"Bearer {TOKEN}"
    return cliente


@pytest.fixture
def api_local(ambiente_local, monkeypatch):
    """O comunicador local, chamado do próprio computador, com a SEFAZ simulada."""
    monkeypatch.setenv("ACBR_SIMULADOR", "1")
    import app.main

    importlib.reload(app.main)
    return cliente_local()
