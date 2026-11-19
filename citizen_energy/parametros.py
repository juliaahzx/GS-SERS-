"""Leitura dos dados (parâmetros, referências e tabela de aparelhos)."""

from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DADOS = RAIZ / "dados"


@lru_cache(maxsize=1)
def carregar_parametros() -> dict:
    with open(PASTA_DADOS / "parametros.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def carregar_referencias() -> dict:
    with open(PASTA_DADOS / "referencias.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def carregar_aparelhos() -> list[dict]:
    aparelhos = []
    with open(PASTA_DADOS / "aparelhos.csv", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            for campo in ("potencia_w", "horas_dia", "dias_mes", "kwh_mes_fixo"):
                linha[campo] = float(linha[campo]) if linha[campo] else None
            linha["sinonimos"] = [s.strip() for s in linha["sinonimos"].split("|") if s.strip()]
            aparelhos.append(linha)
    return aparelhos


def v(grupo: str, chave: str):
    """Atalho para o valor de um parâmetro: v('tarifa', 'tusd_pre_reajuste')."""
    return carregar_parametros()[grupo][chave]["valor"]
