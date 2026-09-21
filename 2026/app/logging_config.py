"""Logs estruturados em JSON, sem dependência externa.

Em 2019 o uWSGI cuspia linhas de texto que nenhum backend de log conseguia
parsear. Aqui cada evento sai como um objeto JSON numa linha, que é o formato
que Loki, CloudWatch, Datadog e afins consomem direto, sem regex no meio.

Fica na stdlib de propósito: toda dependência a mais é superfície de ataque a
mais na cadeia de suprimentos, e um formatter JSON são vinte linhas.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

# Atributos que o logging já põe em todo LogRecord. Tudo que não estiver aqui
# foi passado via `extra=` pela aplicação e merece ir para o JSON.
_RESERVED = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Formata cada LogRecord como um objeto JSON de uma linha."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        # Campos passados com logger.info("...", extra={"chave": valor})
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value

        return json.dumps(payload, ensure_ascii=False, default=str)


class SkipHealthz(logging.Filter):
    """Descarta a linha de acesso das sondas.

    A sonda bate em /healthz a cada poucos segundos, em cada réplica. Sem este
    filtro o log de acesso vira quase só isso, e a requisição real de usuário
    se perde no meio.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            return "/healthz" not in record.getMessage()
        except (TypeError, ValueError):
            return True


def configure_logging(level: str | None = None) -> None:
    """Manda o logging da aplicação para stdout em JSON.

    Stdout, e não arquivo, porque num container o runtime é quem coleta —
    escrever em arquivo dentro do container significa perder o log no restart
    e ainda impedir o root filesystem read-only.

    Sob gunicorn quem configura o logging é o `logconfig_dict` do
    gunicorn.conf.py, que roda também no processo master. Esta função então não
    faz nada: se ela sobrescrevesse a raiz aqui, os logs do master voltariam ao
    formato texto e a saída ficaria metade JSON, metade não. Ela existe para o
    caso de rodar fora do gunicorn — testes e desenvolvimento local.
    """
    root = logging.getLogger()
    if root.handlers:
        return

    resolved = (level or os.getenv("LOG_LEVEL", "INFO")).upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root.addHandler(handler)
    root.setLevel(resolved)
