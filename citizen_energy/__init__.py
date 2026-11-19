"""Módulo de energia do Citizen Assist AI.

Contribuição da disciplina Soluções em Energias Renováveis e Sustentáveis
(Global Solution 2026.2 - FIAP, Ciência da Computação).
"""

from .parametros import carregar_parametros, carregar_referencias, carregar_aparelhos
from .calculos import Perfil, conta_mensal, preco_kwh, consumo_chuveiro_kwh_mes
from .alternativas import comparar_alternativas
from .assistente import AssistenteEnergia

__all__ = [
    "carregar_parametros",
    "carregar_referencias",
    "carregar_aparelhos",
    "Perfil",
    "conta_mensal",
    "preco_kwh",
    "consumo_chuveiro_kwh_mes",
    "comparar_alternativas",
    "AssistenteEnergia",
]
