"""Comparação de alternativas para a MESMA necessidade energética.

Necessidade analisada: aquecer a água do banho de uma família (padrão: 4 banhos
de 8 minutos por dia em chuveiro elétrico de 5.500 W), na área da Enel SP.
Período de referência comum: 12 meses (economia anual) e horizonte de 10 anos
(custo total acumulado).

Alternativas
  A0  Situação atual (chuveiro elétrico, posição inverno o ano todo)
  A1  Eficiência: banho mais curto + posição "verão" nos meses quentes
  A2  Aquecedor solar de água (fonte renovável - solar térmica)
  A3  Painéis fotovoltaicos dimensionados para o consumo do chuveiro (renovável)
  A4  Combinação A1 + A2
"""

from __future__ import annotations

import math

from .calculos import (Perfil, conta_mensal, consumo_chuveiro_kwh_mes, emissao_kg,
                       preco_kwh, aliquota_icms)
from .parametros import v


def _ano_fio_b(indice_ano: int) -> float:
    tabela = v("fotovoltaico", "fio_b_percentual_por_ano")
    ano = min(v("cenarios", "ano_inicio") + 1 + indice_ano, 2029)
    return tabela[str(ano)]


def _consumo_eficiente(perfil: Perfil) -> float:
    minutos = min(perfil.minutos_por_banho, v("eficiencia", "minutos_por_banho_meta"))
    meses_verao = v("eficiencia", "meses_posicao_verao")
    p_verao = min(v("chuveiro", "potencia_verao_w"), perfil.potencia_chuveiro_w)
    inverno = consumo_chuveiro_kwh_mes(perfil.potencia_chuveiro_w, perfil.banhos_por_dia, minutos)
    verao = consumo_chuveiro_kwh_mes(p_verao, perfil.banhos_por_dia, minutos)
    return (inverno * (12 - meses_verao) + verao * meses_verao) / 12


def dimensionar_fv(kwh_mes_alvo: float) -> dict:
    """Dimensiona a potência exata para gerar o consumo-alvo (mesma necessidade das outras opções).

    Na instalação real a potência é arredondada para um número inteiro de módulos;
    o número de módulos é informado apenas como referência.
    """
    wp_mod = v("fotovoltaico", "potencia_modulo_wp")
    kwh_por_kwp_mes = v("fotovoltaico", "hsp_sao_paulo") * 30 * v("fotovoltaico", "performance_ratio")
    kwp = kwh_mes_alvo / kwh_por_kwp_mes
    return {
        "kwh_por_kwp_mes": kwh_por_kwp_mes,
        "kwp": kwp,
        "modulos_referencia": max(1, math.ceil(kwp * 1000 / wp_mod)),
        "geracao_kwh_mes": kwp * kwh_por_kwp_mes,
        "investimento": kwp * 1000 * v("fotovoltaico", "custo_por_wp"),
    }


def _conta_com_fv(perfil: Perfil, geracao_mes: float, indice_ano: int, casa: float) -> float:
    """Conta mensal com geração fotovoltaica no sistema de compensação (Lei 14.300).

    Simplificação conservadora: o preço do kWh (faixa de ICMS) segue o consumo
    bruto retirado da rede, e não o saldo após a compensação.
    """
    auto = min(geracao_mes * v("fotovoltaico", "fracao_autoconsumo"), casa)
    injetada = geracao_mes - auto
    rede = casa - auto
    preco = preco_kwh(rede)
    if perfil.tarifa_social:
        compensada = max(min(injetada, rede), 0)
        liquido = rede - compensada
        conta = max(liquido - v("tarifa_social", "limite_gratuidade_kwh"), 0) * preco
    else:
        minimo = v("tarifa", "custo_disponibilidade_kwh")[perfil.ligacao]
        compensada = max(min(injetada, rede - minimo), 0)
        liquido = rede - compensada
        conta = liquido * preco
    # Parcela do Fio B que deixa de ser compensada (Lei 14.300), com tributos
    divisor = 1 - v("tarifa", "pis_cofins_efetivo") - aliquota_icms(rede)
    conta += compensada * _ano_fio_b(indice_ano) * v("fotovoltaico", "fio_b") / divisor
    return conta


def comparar_alternativas(perfil: Perfil | None = None) -> dict:
    perfil = perfil or Perfil()
    horizonte = int(v("cenarios", "horizonte_anos"))
    g = v("cenarios", "reajuste_tarifa_sensibilidade")

    chuveiro_base = consumo_chuveiro_kwh_mes(perfil.potencia_chuveiro_w, perfil.banhos_por_dia,
                                             perfil.minutos_por_banho)
    outros = max(perfil.consumo_mensal_kwh - chuveiro_base, 0)
    conta_base = conta_mensal(perfil.consumo_mensal_kwh, perfil.tarifa_social, perfil.ligacao)

    fracao_solar = v("aquecedor_solar", "fracao_solar")
    ch_eficiente = _consumo_eficiente(perfil)
    fv = dimensionar_fv(chuveiro_base)
    fv_eficiente = dimensionar_fv(ch_eficiente)

    definicoes = [
        {
            "id": "A0", "nome": "Situação atual (chuveiro elétrico)", "renovavel": False,
            "chuveiro_kwh_mes": chuveiro_base, "investimento": 0.0, "manutencao_anual": 0.0,
            "detalhe": f"{perfil.banhos_por_dia} banhos/dia de {perfil.minutos_por_banho:g} min a {perfil.potencia_chuveiro_w:g} W",
        },
        {
            "id": "A1", "nome": "Eficiência: banho mais curto + posição verão", "renovavel": False,
            "chuveiro_kwh_mes": ch_eficiente, "investimento": float(v("eficiencia", "investimento")),
            "manutencao_anual": 0.0,
            "detalhe": f"banho de {min(perfil.minutos_por_banho, v('eficiencia', 'minutos_por_banho_meta')):g} min e posição verão {v('eficiencia', 'meses_posicao_verao')} meses/ano",
        },
        {
            "id": "A2", "nome": "Aquecedor solar de água – solar térmico", "renovavel": True,
            "chuveiro_kwh_mes": chuveiro_base * (1 - fracao_solar),
            "investimento": float(v("aquecedor_solar", "investimento")),
            "manutencao_anual": float(v("aquecedor_solar", "manutencao_anual")),
            "detalhe": f"sol fornece ~{fracao_solar:.0%} do aquecimento; chuveiro fica como apoio",
        },
        {
            "id": "A3", "nome": "Painéis fotovoltaicos – solar elétrico", "renovavel": True,
            "chuveiro_kwh_mes": chuveiro_base, "investimento": fv["investimento"],
            "manutencao_anual": float(v("fotovoltaico", "manutencao_anual")),
            "detalhe": f"{fv['kwp']:.2f} kWp (~{fv['modulos_referencia']} módulos de {v('fotovoltaico', 'potencia_modulo_wp')} Wp), geração ~{fv['geracao_kwh_mes']:.0f} kWh/mês",
            "fv": fv,
        },
        {
            "id": "A4", "nome": "Combinação: hábitos (A1) + aquecedor solar (A2)", "renovavel": True,
            "chuveiro_kwh_mes": ch_eficiente * (1 - fracao_solar),
            "investimento": float(v("aquecedor_solar", "investimento")),
            "manutencao_anual": float(v("aquecedor_solar", "manutencao_anual")),
            "detalhe": "menos tempo de banho e água pré-aquecida pelo sol",
        },
        {
            "id": "A5", "nome": "Combinação: hábitos (A1) + fotovoltaico menor (A3)", "renovavel": True,
            "chuveiro_kwh_mes": ch_eficiente, "investimento": fv_eficiente["investimento"],
            "manutencao_anual": float(v("fotovoltaico", "manutencao_anual")),
            "detalhe": f"{fv_eficiente['kwp']:.2f} kWp, dimensionado para o consumo do chuveiro já reduzido ({ch_eficiente:.0f} kWh/mês)",
            "fv": fv_eficiente,
        },
    ]

    resultados = []
    for alt in definicoes:
        consumo_casa = outros + alt["chuveiro_kwh_mes"]
        contas_ano = []
        for i in range(horizonte):
            if "fv" in alt:
                ger = alt["fv"]["geracao_kwh_mes"] * (1 - v("fotovoltaico", "degradacao_anual")) ** i
                contas_ano.append(_conta_com_fv(perfil, ger, i, consumo_casa) * 12)
            else:
                contas_ano.append(conta_mensal(consumo_casa, perfil.tarifa_social, perfil.ligacao) * 12)

        economia_ano1 = conta_base * 12 - contas_ano[0]
        ganho_liquido = economia_ano1 - alt["manutencao_anual"]
        if alt["investimento"] == 0:
            payback = 0.0
        elif ganho_liquido > 0:
            payback = alt["investimento"] / ganho_liquido
        else:
            payback = math.inf

        def custo_total(taxa: float) -> float:
            return alt["investimento"] + sum(
                c * (1 + taxa) ** i + alt["manutencao_anual"] for i, c in enumerate(contas_ano))

        kwh_rede_evitado_ano = (chuveiro_base - alt["chuveiro_kwh_mes"]) * 12
        if "fv" in alt:
            kwh_rede_evitado_ano += alt["fv"]["geracao_kwh_mes"] * 12

        resultados.append({
            "id": alt["id"],
            "nome": alt["nome"],
            "renovavel": alt["renovavel"],
            "detalhe": alt["detalhe"],
            "chuveiro_kwh_mes": round(alt["chuveiro_kwh_mes"], 1),
            "consumo_casa_kwh_mes": round(consumo_casa, 1),
            "conta_mes_ano1": round(contas_ano[0] / 12, 2),
            "economia_mes_ano1": round(economia_ano1 / 12, 2),
            "economia_ano1": round(economia_ano1, 2),
            "investimento": round(alt["investimento"], 2),
            "manutencao_anual": alt["manutencao_anual"],
            "payback_anos": round(payback, 1) if math.isfinite(payback) else None,
            "custo_total_10a_base": round(custo_total(0.0), 2),
            "custo_total_10a_reajuste": round(custo_total(g), 2),
            "kwh_evitados_ano": round(kwh_rede_evitado_ano, 1),
            "co2_evitado_kg_ano": round(emissao_kg(kwh_rede_evitado_ano), 1),
            "contas_anuais": [round(c, 2) for c in contas_ano],
        })

    return {
        "perfil": perfil.to_dict(),
        "chuveiro_base_kwh_mes": round(chuveiro_base, 1),
        "outros_kwh_mes": round(outros, 1),
        "conta_base_mes": round(conta_base, 2),
        "preco_kwh_base": round(preco_kwh(perfil.consumo_mensal_kwh), 4),
        "horizonte_anos": horizonte,
        "alternativas": resultados,
    }


VIABILIDADE = {
    "A0": {
        "viabilidade": "Já é a situação da família.",
        "ambiental": "Toda a energia vem da rede; o chuveiro concentra consumo no horário de pico (18h-21h), quando o sistema mais usa térmicas.",
        "limitacoes": "Maior gasto mensal; potência alta pode sobrecarregar instalações antigas.",
    },
    "A1": {
        "viabilidade": "Alta: não exige compra, obra nem ser dono do imóvel. Depende de adesão de todos os moradores.",
        "ambiental": "Reduz energia e também água. Sem resíduos ou fabricação de equipamentos.",
        "limitacoes": "Economia depende do hábito ser mantido; conforto menor em dias frios na posição verão.",
    },
    "A2": {
        "viabilidade": "Média: exige telhado com sol (face norte), caixa d'água elevada, espaço para o reservatório e autorização do proprietário. Investimento inicial alto para baixa renda; vale procurar programas habitacionais e financiamentos.",
        "ambiental": "Usa energia renovável direto como calor (eficiência maior que converter sol em eletricidade). Fabricação usa vidro, cobre/alumínio e isolamento; vida útil longa.",
        "limitacoes": "Em dias nublados seguidos o chuveiro elétrico ainda é usado. Requer manutenção e instalação por profissional.",
    },
    "A3": {
        "viabilidade": "Média: exige telhado próprio com sol, homologação na distribuidora e dinheiro (ou crédito) para o investimento. Como os banhos acontecem sem sol, ~70% da geração é injetada na rede e paga parte do Fio B, que sobe ano a ano (Lei 14.300). A conta nunca fica abaixo do custo de disponibilidade.",
        "ambiental": "Energia renovável sem emissão na operação; módulos e inversor exigem descarte/reciclagem adequados no fim da vida útil (~25 anos).",
        "limitacoes": "Resultado muito sensível ao preço por Wp de sistemas pequenos e ao valor do Fio B (estimado). Inquilinos normalmente não podem instalar. Na Tarifa Social, a economia só se mantém enquanto o consumo líquido ficar acima dos 80 kWh gratuitos.",
    },
    "A4": {
        "viabilidade": "Média (mesmas exigências do aquecedor solar), mas com o menor consumo de eletricidade da casa entre as opções.",
        "ambiental": "Menor uso de energia da rede entre as opções; soma os ganhos de hábito e de fonte renovável.",
        "limitacoes": "Mesmas do aquecedor solar; o ganho extra do hábito é menor porque o sol já aquece boa parte da água.",
    },
    "A5": {
        "viabilidade": "Média (mesmas exigências do fotovoltaico), com investimento menor porque o consumo já foi reduzido pelos hábitos.",
        "ambiental": "Soma a redução de consumo com geração renovável.",
        "limitacoes": "Mesmas do fotovoltaico; se os hábitos não forem mantidos, o sistema fica subdimensionado.",
    },
}
