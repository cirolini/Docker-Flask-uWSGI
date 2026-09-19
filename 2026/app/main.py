"""O mesmo app de 2019: diz olá e mostra o hostname do container.

O comportamento é idêntico de propósito — o estudo de caso é sobre como se
entrega um container, não sobre o que o app faz. O que mudou aqui é só o que
a operação precisa para funcionar em produção: um endpoint de health separado
da rota de negócio e logs que alguém consegue ler.
"""

from __future__ import annotations

import logging
import os
import socket
from html import escape

from flask import Flask, Response, jsonify

from app.logging_config import configure_logging

log = logging.getLogger(__name__)

# Resolvido uma vez: o hostname de um container não muda enquanto ele vive, e
# em 2019 isso era uma syscall por request.
HOSTNAME = socket.gethostname()


def create_app() -> Flask:
    """Cria a aplicação Flask.

    App factory em vez de um `app` global porque é isso que deixa os testes
    criarem instâncias isoladas — em 2019 não havia teste nenhum para isolar.
    """
    configure_logging()
    flask_app = Flask(__name__)

    @flask_app.route("/")
    def hello() -> str:
        log.info("request", extra={"path": "/", "hostname": HOSTNAME})
        return (
            "<h3>Hello Fullstack!</h3>"
            f"<b>Hostname:</b> {escape(HOSTNAME)}<br/>"
        )

    @flask_app.route("/healthz")
    def healthz() -> Response:
        """Liveness/readiness.

        Separado de `/` porque sonda e usuário fazem perguntas diferentes:
        a sonda quer saber se o processo responde, não quer renderizar HTML
        nem aparecer no log de acesso a cada segundo.
        """
        return jsonify(status="ok", hostname=HOSTNAME)

    # Aparece uma vez no master (que importa o módulo para resolver o app) e
    # mais uma por worker. O pid no log distingue os dois.
    log.info(
        "aplicação carregada",
        extra={"hostname": HOSTNAME, "pid": os.getpid()},
    )
    return flask_app


app = create_app()
