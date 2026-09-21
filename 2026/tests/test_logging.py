"""Testes do logging estruturado.

Formatter próprio é código, e código sem teste quebra calado — o pior jeito de
descobrir que o log parou de ser parseável é precisar dele durante um incidente.
"""

from __future__ import annotations

import json
import logging

from app.logging_config import JsonFormatter, SkipHealthz


def _registro(msg: str = "oi", **extra) -> logging.LogRecord:
    registro = logging.LogRecord(
        name="teste", level=logging.INFO, pathname=__file__,
        lineno=1, msg=msg, args=None, exc_info=None,
    )
    for chave, valor in extra.items():
        setattr(registro, chave, valor)
    return registro


def test_saida_e_json_valido_de_uma_linha():
    saida = JsonFormatter().format(_registro())
    assert "\n" not in saida
    assert json.loads(saida)["msg"] == "oi"


def test_campos_obrigatorios_presentes():
    corpo = json.loads(JsonFormatter().format(_registro()))
    assert set(corpo) >= {"ts", "level", "logger", "msg"}
    assert corpo["level"] == "INFO"
    assert corpo["logger"] == "teste"


def test_campos_do_extra_viram_chaves():
    corpo = json.loads(JsonFormatter().format(_registro(hostname="abc", pid=7)))
    assert corpo["hostname"] == "abc"
    assert corpo["pid"] == 7


def test_excecao_vai_para_o_json():
    try:
        raise ValueError("falhou")
    except ValueError:
        import sys

        registro = _registro("erro")
        registro.exc_info = sys.exc_info()
        corpo = json.loads(JsonFormatter().format(registro))

    assert "ValueError: falhou" in corpo["exc"]


def test_objeto_nao_serializavel_nao_derruba_o_log():
    """Um log que levanta exceção ao formatar é pior que um log impreciso."""
    corpo = json.loads(JsonFormatter().format(_registro(obj=object())))
    assert "obj" in corpo


def test_filtro_descarta_healthz_e_mantem_o_resto():
    filtro = SkipHealthz()
    assert filtro.filter(_registro('GET /healthz HTTP/1.1" 200')) is False
    assert filtro.filter(_registro('GET / HTTP/1.1" 200')) is True
