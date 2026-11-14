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

TOKEN = "token-de-teste"
CHAVE_E2E = base64.b64encode(b"e" * 32).decode()


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


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    # A configuração guardada (emitentes, token) de cada teste fica no seu tmp_path.
    monkeypatch.setenv("ACBR_DATA_DIR", str(tmp_path / "dados"))
    monkeypatch.setenv("ACBRLIB_TOKEN", TOKEN)
    monkeypatch.setenv("ACBR_E2E_KEY", CHAVE_E2E)
    monkeypatch.setenv("ACBR_ALLOWED_ORIGINS", "https://caixa.exemplo.com.br")


@pytest.fixture
def api(ambiente, monkeypatch):
    """O comunicador com a SEFAZ simulada, como sobe com ACBR_SIMULADOR=1."""
    monkeypatch.setenv("ACBR_SIMULADOR", "1")
    import app.main

    modulo = importlib.reload(app.main)
    cliente = ClienteSelado(modulo.app)
    cliente.headers["Authorization"] = f"Bearer {TOKEN}"
    return cliente
