"""Configuração do gunicorn.

Cada opção aqui responde a um achado concreto do wsgi.ini de 2019 — a auditoria
está em docs/then-vs-now.md.
"""

from __future__ import annotations

import multiprocessing
import os

bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"

# 2019: `processes = 5` fixo no wsgi.ini, sem relação nenhuma com o limite de
# CPU do pod. Aqui o default vem da CPU realmente disponível e WEB_CONCURRENCY
# deixa o manifesto do Kubernetes mandar — quem sabe o limite é ele.
workers = int(os.getenv("WEB_CONCURRENCY", multiprocessing.cpu_count() * 2 + 1))
worker_class = "sync"

# 2019: sem harakiri. Um request travado prendia um worker para sempre, e cinco
# deles derrubavam o app com o pod ainda marcado como saudável.
timeout = 30
graceful_timeout = 30

# Recicla worker periodicamente: segura vazamento lento sem ninguém perceber.
# O jitter evita que todos os workers reiniciem no mesmo instante.
max_requests = 1000
max_requests_jitter = 100

keepalive = 5

# Com o root filesystem read-only, o heartbeat do gunicorn precisa de um lugar
# gravável em memória. Sem isto os workers entram em loop de restart.
worker_tmp_dir = "/dev/shm"  # noqa: S108

# O gunicorn 26 abre um socket de controle em ~/.gunicorn/gunicorn.ctl. O
# usuário do container não tem home e o filesystem é read-only, então isso
# falhava a cada boot com "Permission denied: '/home/app'". O app não usa a
# interface de controle — desligar é melhor que abrir um diretório gravável.
control_socket_disable = True

# Logging estruturado, configurado aqui e não na aplicação porque isto também
# roda no processo master. Quando ficava só no create_app(), as linhas do
# master ("Starting gunicorn", "Booting worker") saíam em texto puro e a saída
# ficava metade JSON, metade não — impossível de parsear de um jeito só.
loglevel = os.getenv("LOG_LEVEL", "info").lower()
accesslog = "-"
errorlog = "-"

logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "app.logging_config.JsonFormatter"},
    },
    "filters": {
        "sem_healthz": {"()": "app.logging_config.SkipHealthz"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "json",
        },
        "console_acesso": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "json",
            "filters": ["sem_healthz"],
        },
    },
    "root": {
        "level": loglevel.upper(),
        "handlers": ["console"],
    },
    "loggers": {
        "gunicorn.error": {
            "level": loglevel.upper(),
            "handlers": ["console"],
            "propagate": False,
        },
        "gunicorn.access": {
            "level": "INFO",
            "handlers": ["console_acesso"],
            "propagate": False,
        },
    },
}
