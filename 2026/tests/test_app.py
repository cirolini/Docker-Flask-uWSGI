"""Testes do app 2026.

Existem para que o estágio "test" do pipeline signifique alguma coisa. Em 2019
o Jenkinsfile tinha um estágio chamado "Unit Test" cujo corpo inteiro era
`teste = "fullstack"` — ele passava sempre, inclusive com o app quebrado.
"""

from __future__ import annotations

import json

import pytest

from app.main import HOSTNAME, create_app


@pytest.fixture
def client():
    flask_app = create_app()
    flask_app.config.update(TESTING=True)
    with flask_app.test_client() as test_client:
        yield test_client


def test_raiz_responde_200(client):
    assert client.get("/").status_code == 200


def test_raiz_mantem_o_comportamento_de_2019(client):
    """O contrato do app não mudou: saúda e mostra o hostname."""
    corpo = client.get("/").get_data(as_text=True)
    assert "Hello Fullstack!" in corpo
    assert "<b>Hostname:</b>" in corpo
    assert HOSTNAME in corpo


def test_healthz_responde_json(client):
    resposta = client.get("/healthz")
    assert resposta.status_code == 200
    assert resposta.mimetype == "application/json"

    corpo = json.loads(resposta.get_data(as_text=True))
    assert corpo["status"] == "ok"
    assert corpo["hostname"] == HOSTNAME


def test_healthz_nao_devolve_html(client):
    """A sonda não deve pagar o custo de renderizar a página."""
    assert "<h3>" not in client.get("/healthz").get_data(as_text=True)


def test_rota_inexistente_da_404(client):
    assert client.get("/nao-existe").status_code == 404
