"""Cálculos de energia, potência e custo usados pelo assistente.

Conceitos aplicados
-------------------
* Energia (kWh) = Potência (kW) x tempo de uso (h).
* Preço final do kWh = tarifa sem tributos / (1 - PIS/COFINS - ICMS)
  (os tributos são calculados "por dentro", como aparece na fatura).
* Conta de energia = consumo faturado x preço final do kWh
  (não inclui a contribuição de iluminação pública - CIP/COSIP).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

from .parametros import v, carregar_aparelhos


@dataclass
class Perfil:
    """Situação da família atendida (todos os campos podem ser ajustados pelo usuário)."""

    moradores: int = 4
    banhos_por_dia: int = 4
    minutos_por_banho: float = field(default_factory=lambda: v("chuveiro", "minutos_por_banho"))
    potencia_chuveiro_w: float = field(default_factory=lambda: v("chuveiro", "potencia_inverno_w"))
    consumo_mensal_kwh: float = field(default_factory=lambda: v("consumo", "consumo_familia_referencia"))
    tarifa_social: bool = False
    ligacao: str = "bifasico"  # monofasico | bifasico | trifasico

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- energia ---

def energia_kwh(potencia_w: float, horas_dia: float, dias: float = 30) -> float:
    """E = P x t. Retorna kWh no período."""
    return potencia_w / 1000 * horas_dia * dias


def consumo_chuveiro_kwh_mes(potencia_w: float, banhos_dia: float, minutos: float, dias: int = 30) -> float:
    return energia_kwh(potencia_w, banhos_dia * minutos / 60, dias)


def buscar_aparelho(texto: str) -> dict | None:
    """Encontra o aparelho cujo nome ou sinônimo aparece no texto (o mais específico primeiro)."""
    texto = texto.lower()
    candidatos = []
    for ap in carregar_aparelhos():
        for termo in [ap["aparelho"], *ap["sinonimos"]]:
            if termo and re.search(r"\b" + re.escape(termo) + r"\b", texto):
                candidatos.append((len(termo), ap))
    if not candidatos:
        return None
    candidatos.sort(key=lambda c: c[0], reverse=True)
    return candidatos[0][1]


def consumo_aparelho_kwh_mes(ap: dict, potencia_w: float | None = None,
                             horas_dia: float | None = None, quantidade: int = 1) -> float:
    if ap.get("kwh_mes_fixo") and potencia_w is None:
        return ap["kwh_mes_fixo"] * quantidade
    p = potencia_w if potencia_w is not None else ap["potencia_w"]
    h = horas_dia if horas_dia is not None else ap["horas_dia"]
    return energia_kwh(p, h, ap["dias_mes"]) * quantidade


# ----------------------------------------------------------------- tarifa ---

def tarifa_sem_tributos(incluir_bandeira: bool = True) -> float:
    """TE + TUSD após o reajuste de jul/2026 (estimado) + bandeira média do ano."""
    reajuste = 1 + v("tarifa", "reajuste_residencial_2026")
    base = (v("tarifa", "tusd_pre_reajuste") + v("tarifa", "te_pre_reajuste")) * reajuste
    if incluir_bandeira:
        base += v("tarifa", "bandeira_media_2026")
    return base


def aliquota_icms(consumo_kwh: float) -> float:
    for limite, aliquota in v("tarifa", "icms_faixas"):
        if consumo_kwh <= limite:
            return aliquota
    return v("tarifa", "icms_faixas")[-1][1]


def preco_kwh(consumo_kwh: float, incluir_bandeira: bool = True) -> float:
    """Preço final do kWh (com tributos) para uma conta com esse consumo mensal."""
    divisor = 1 - v("tarifa", "pis_cofins_efetivo") - aliquota_icms(consumo_kwh)
    return tarifa_sem_tributos(incluir_bandeira) / divisor


def conta_mensal(consumo_kwh: float, tarifa_social: bool = False, ligacao: str = "bifasico") -> float:
    """Valor estimado da parcela de energia da conta (R$/mês).

    * Respeita o custo de disponibilidade (consumo mínimo faturado).
    * Tarifa Social (Lei 15.235/2025): os primeiros 80 kWh não são cobrados;
      o excedente é cobrado normalmente.
    """
    minimo = v("tarifa", "custo_disponibilidade_kwh")[ligacao]
    if tarifa_social:
        gratis = v("tarifa_social", "limite_gratuidade_kwh")
        cobrado = max(consumo_kwh - gratis, 0)
        return cobrado * preco_kwh(consumo_kwh)
    faturado = max(consumo_kwh, minimo)
    return faturado * preco_kwh(faturado)


def custo_marginal_kwh(consumo_kwh: float, tarifa_social: bool = False) -> float:
    """Quanto 1 kWh a mais (ou a menos) muda a conta, na faixa de consumo atual."""
    if tarifa_social and consumo_kwh <= v("tarifa_social", "limite_gratuidade_kwh"):
        return 0.0
    return preco_kwh(consumo_kwh)


def emissao_kg(kwh: float) -> float:
    return kwh * v("ambiental", "fator_emissao_sin")
