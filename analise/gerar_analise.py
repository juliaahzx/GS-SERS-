"""Gera a análise energética completa a partir dos dados do projeto.

    python analise/gerar_analise.py

Saídas:
    docs/analise_energetica.md       relatório com cálculos, comparação e sensibilidade
    resultados/comparacao_*.csv      tabelas das alternativas
    resultados/sensibilidade.csv     testes de sensibilidade
    docs/graficos/*.png              gráficos (se matplotlib estiver instalado)

Todos os números do relatório saem do mesmo código usado pelo assistente
(citizen_energy), garantindo coerência entre análise e respostas.
"""

from __future__ import annotations

import csv
import sys
from contextlib import contextmanager
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from citizen_energy.alternativas import VIABILIDADE, comparar_alternativas, dimensionar_fv  # noqa: E402
from citizen_energy.assistente import brl, num  # noqa: E402
from citizen_energy.calculos import (Perfil, aliquota_icms, conta_mensal,  # noqa: E402
                                     consumo_chuveiro_kwh_mes, preco_kwh, tarifa_sem_tributos)
from citizen_energy.parametros import carregar_parametros, carregar_referencias, v  # noqa: E402

DOCS = RAIZ / "docs"
GRAF = DOCS / "graficos"
RES = RAIZ / "resultados"


@contextmanager
def parametro(grupo: str, chave: str, valor):
    p = carregar_parametros()[grupo][chave]
    antigo = p["valor"]
    p["valor"] = valor
    try:
        yield
    finally:
        p["valor"] = antigo


def salvar_csv(caminho: Path, linhas: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)


def pb(a: dict) -> str:
    if a["payback_anos"] == 0:
        return "imediato"
    return "não se paga" if a["payback_anos"] is None else f"{num(a['payback_anos'])} anos"


def tabela_alternativas(r: dict) -> str:
    cab = ("| Alternativa | Renovável | Chuveiro (kWh/mês) | Consumo da casa (kWh/mês) | Conta energia (R$/mês, ano 1) | "
           "Economia (R$/ano) | Investimento | Retorno simples | Custo total 10 anos (tarifa constante) | "
           "Custo total 10 anos (+5% a.a.) | CO2 evitado (kg/ano) |\n|---|---|---|---|---|---|---|---|---|---|---|\n")
    linhas = []
    for a in r["alternativas"]:
        linhas.append(
            f"| **{a['id']}** {a['nome']}<br><small>{a['detalhe']}</small> | {'sim' if a['renovavel'] else 'não'} | "
            f"{num(a['chuveiro_kwh_mes'])} | {num(a['consumo_casa_kwh_mes'])} | {brl(a['conta_mes_ano1'])} | "
            f"{brl(a['economia_ano1'])} | {brl(a['investimento'])} | {pb(a)} | {brl(a['custo_total_10a_base'])} | "
            f"{brl(a['custo_total_10a_reajuste'])} | {num(a['co2_evitado_kg_ano'])} |")
    return cab + "\n".join(linhas)


def sensibilidade() -> list[dict]:
    linhas = []

    def registra(variavel, valor_txt, perfil=None, ids=("A2", "A3")):
        r = comparar_alternativas(perfil or Perfil())
        alts = {a["id"]: a for a in r["alternativas"]}
        for i in ids:
            a = alts[i]
            linhas.append({"variavel": variavel, "valor": valor_txt, "alternativa": i,
                           "investimento": a["investimento"], "economia_ano1": a["economia_ano1"],
                           "payback_anos": a["payback_anos"] if a["payback_anos"] is not None else "não se paga",
                           "custo_total_10a": a["custo_total_10a_base"],
                           "custo_total_10a_A1_referencia": alts["A1"]["custo_total_10a_base"]})

    for cwp in (3.40, 4.20, 5.50, 7.00):
        with parametro("fotovoltaico", "custo_por_wp", cwp):
            registra("FV: custo por Wp (R$)", num(cwp, 2), ids=("A3",))
    for fio in (0.10, 0.15, 0.25):
        with parametro("fotovoltaico", "fio_b", fio):
            registra("FV: Fio B (R$/kWh)", num(fio, 2), ids=("A3",))
    for aut in (0.10, 0.30, 0.50):
        with parametro("fotovoltaico", "fracao_autoconsumo", aut):
            registra("FV: autoconsumo simultâneo", f"{aut:.0%}", ids=("A3",))
    for inv in (5000, 7000, 9000):
        with parametro("aquecedor_solar", "investimento", inv):
            registra("Aquecedor: investimento (R$)", num(inv, 0), ids=("A2",))
    for fr in (0.60, 0.70, 0.80):
        with parametro("aquecedor_solar", "fracao_solar", fr):
            registra("Aquecedor: fração solar", f"{fr:.0%}", ids=("A2",))
    for mor in (2, 4, 6):
        consumo = 180 - 88 + consumo_chuveiro_kwh_mes(5500, mor, 8)
        registra("Moradores (1 banho de 8 min cada)", f"{mor} (casa {consumo:.0f} kWh/mês)",
                 Perfil(moradores=mor, banhos_por_dia=mor, consumo_mensal_kwh=consumo))
    registra("Tarifa Social (CadÚnico)", "sim", Perfil(tarifa_social=True))
    return linhas


def tabela_sens(linhas: list[dict]) -> str:
    cab = ("| Variável | Valor | Alternativa | Investimento | Economia ano 1 | Retorno | Custo 10 anos | Custo 10 anos de A1 (hábitos) |\n"
           "|---|---|---|---|---|---|---|---|\n")
    out = []
    for l in linhas:
        ret = l["payback_anos"] if isinstance(l["payback_anos"], str) else f"{num(l['payback_anos'])} anos"
        out.append(f"| {l['variavel']} | {l['valor']} | {l['alternativa']} | {brl(l['investimento'])} | "
                   f"{brl(l['economia_ano1'])} | {ret} | {brl(l['custo_total_10a'])} | {brl(l['custo_total_10a_A1_referencia'])} |")
    return cab + "\n".join(out)


def graficos(r: dict, r_ts: dict) -> list[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib não instalado: gráficos não gerados (pip install matplotlib)")
        return []
    GRAF.mkdir(parents=True, exist_ok=True)
    gerados = []
    cores = {"A0": "#8a8f88", "A1": "#3b7dd8", "A2": "#e8a33d", "A3": "#2e9e5b", "A4": "#c46a2f", "A5": "#1f6f43"}
    alts = r["alternativas"]
    rotulos = {"A0": "A0\nAtual", "A1": "A1\nHábitos", "A2": "A2\nAquecedor solar", "A3": "A3\nFotovoltaico",
               "A4": "A4\nHábitos +\naquecedor", "A5": "A5\nHábitos +\nfotovoltaico"}

    fig, ax = plt.subplots(figsize=(9, 4.8))
    ids = [a["id"] for a in alts]
    ax.bar([rotulos[i] for i in ids], [a["conta_mes_ano1"] for a in alts], color=[cores[i] for i in ids])
    for i, a in enumerate(alts):
        ax.text(i, a["conta_mes_ano1"] + 2, brl(a["conta_mes_ano1"]), ha="center", fontsize=9)
    ax.set_ylabel("R$ por mês (energia, ano 1)")
    ax.set_title("Conta de energia estimada por alternativa – família de 4 pessoas, Enel SP")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(GRAF / "conta_mensal_por_alternativa.png", dpi=150)
    plt.close(fig)
    gerados.append("conta_mensal_por_alternativa.png")

    fig, ax = plt.subplots(figsize=(9, 4.8))
    for a in alts:
        acumulado, total = [a["investimento"]], a["investimento"]
        for c in a["contas_anuais"]:
            total += c + a["manutencao_anual"]
            acumulado.append(total)
        ax.plot(range(0, len(acumulado)), acumulado, marker="o", markersize=3, label=rotulos[a["id"]].replace("\n", " "),
                color=cores[a["id"]], linewidth=2 if a["id"] in ("A0", "A1", "A5") else 1.4)
    ax.set_xlabel("Anos")
    ax.set_ylabel("Custo acumulado (R$)")
    ax.set_title("Custo acumulado em 10 anos (investimento + contas + manutenção)")
    ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(GRAF / "custo_acumulado_10_anos.png", dpi=150)
    plt.close(fig)
    gerados.append("custo_acumulado_10_anos.png")

    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.bar([rotulos[i] for i in ids], [a["kwh_evitados_ano"] for a in alts], color=[cores[i] for i in ids])
    for i, a in enumerate(alts):
        ax.text(i, a["kwh_evitados_ano"] + 15, f"{num(a['kwh_evitados_ano'], 0)} kWh\n{num(a['co2_evitado_kg_ano'], 0)} kg CO2",
                ha="center", fontsize=8.5)
    ax.set_ylabel("Energia da rede evitada (kWh/ano)")
    ax.set_title("Energia da rede evitada e CO2 evitado por ano (fator SIN 38,5 gCO2/kWh)")
    ax.set_ylim(0, max(a["kwh_evitados_ano"] for a in alts) * 1.2)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(GRAF / "energia_e_co2_evitados.png", dpi=150)
    plt.close(fig)
    gerados.append("energia_e_co2_evitados.png")
    return gerados


def main() -> None:
    params = carregar_parametros()
    refs = carregar_referencias()
    perfil = Perfil()
    r = comparar_alternativas(perfil)
    r_ts = comparar_alternativas(Perfil(tarifa_social=True))
    alts = {a["id"]: a for a in r["alternativas"]}
    alts_ts = {a["id"]: a for a in r_ts["alternativas"]}

    for nome, res in (("comparacao_padrao.csv", r), ("comparacao_tarifa_social.csv", r_ts)):
        salvar_csv(RES / nome, [{k: val for k, val in a.items() if k != "contas_anuais"} for a in res["alternativas"]])
    sens = sensibilidade()
    salvar_csv(RES / "sensibilidade.csv", sens)
    imgs = graficos(r, r_ts)

    t_sem = tarifa_sem_tributos(False)
    t_band = tarifa_sem_tributos(True)
    fv = dimensionar_fv(r["chuveiro_base_kwh_mes"])
    ch = r["chuveiro_base_kwh_mes"]

    linhas_param = []
    for grupo, itens in params.items():
        if grupo.startswith("_"):
            continue
        for chave, p in itens.items():
            valor = p["valor"]
            if isinstance(valor, (dict, list)):
                valor = str(valor).replace("'", "")
            linhas_param.append(f"| {grupo}.{chave} | {valor} | {p['unidade']} | {p['tipo']} | {p['fonte']} | {p['obs']} |")

    renov = sorted([alts["A2"], alts["A3"]], key=lambda a: a["custo_total_10a_base"])
    melhor_combo = min((alts["A4"], alts["A5"]), key=lambda a: a["custo_total_10a_base"])
    sens_fv_caro = [s for s in sens if s["variavel"].startswith("FV: custo") and s["valor"] == "7,00" and s["alternativa"] == "A3"][0]
    sens_aq_barato = [s for s in sens if s["variavel"].startswith("Aquecedor: invest") and s["valor"] == "5.000" and s["alternativa"] == "A2"][0]

    md = f"""# Análise energética – Citizen Assist AI (módulo de energia)

> Documento gerado automaticamente por `analise/gerar_analise.py` a partir de `dados/parametros.json`.
> Os mesmos cálculos alimentam as respostas do assistente (`citizen_energy/`).

## 1. Necessidade analisada e período de referência

* **Público:** famílias de baixa e média renda da Região Metropolitana de São Paulo (área da Enel SP), que usam chuveiro elétrico.
* **Necessidade energética:** aquecer a água do banho, o maior consumo individual de uma casa típica.
* **Família de referência:** {perfil.moradores} moradores, {perfil.banhos_por_dia} banhos/dia de {perfil.minutos_por_banho:g} min, chuveiro de {perfil.potencia_chuveiro_w:g} W, consumo total de {perfil.consumo_mensal_kwh:g} kWh/mês (próximo do consumo residencial médio nacional de 181,8 kWh/mês [R6]), ligação bifásica.
* **Período comum de comparação:** 12 meses (economia anual) e horizonte de **10 anos** (custo total acumulado). Cenário base com tarifa constante; sensibilidade com reajuste de 5% ao ano.

## 2. Conceitos e fórmulas

* **Potência (W)** é a taxa de uso de energia; **energia (kWh)** = potência (kW) × tempo (h).
* Chuveiro: E = {num(perfil.potencia_chuveiro_w / 1000)} kW × ({perfil.banhos_por_dia} × {perfil.minutos_por_banho:g} min ÷ 60) h/dia × 30 dias = **{num(ch)} kWh/mês** ({ch / perfil.consumo_mensal_kwh:.0%} do consumo da casa). O mesmo cenário aparece em simulação pública baseada em dados Procel/INMETRO [R7].
* **Preço final do kWh** = tarifa sem tributos ÷ (1 − PIS/COFINS − ICMS), cálculo "por dentro" usado na fatura.
* **Fotovoltaico:** geração mensal = kWp × HSP × 30 × PR = kWp × {num(v('fotovoltaico', 'hsp_sao_paulo'))} × 30 × {num(v('fotovoltaico', 'performance_ratio'), 2)} = **{num(fv['kwh_por_kwp_mes'])} kWh por kWp/mês**.
* **Aquecedor solar:** energia elétrica do chuveiro × (1 − fração solar).
* **Retorno simples (payback)** = investimento ÷ (economia anual − manutenção).
* **Emissões** = kWh evitados × fator de emissão do SIN ({num(v('ambiental', 'fator_emissao_sin'), 4)} kgCO2/kWh [R13]).

## 3. Tarifa usada (Enel SP, B1 residencial)

| Etapa | Valor |
|---|---|
| TUSD + TE vigentes até jul/2026 (sem tributos) [R2] | {brl(v('tarifa', 'tusd_pre_reajuste') + v('tarifa', 'te_pre_reajuste'))}/kWh |
| Reajuste residencial ANEEL 2026 (+{num(v('tarifa', 'reajuste_residencial_2026') * 100, 2)}%) [R1] → **estimado** | {brl(t_sem)}/kWh |
| + bandeira média de 2026 (amarela de maio a setembro) [R3] | {brl(t_band)}/kWh |
| Preço final com PIS/COFINS ({num(v('tarifa', 'pis_cofins_efetivo') * 100)}%) e ICMS de 12% (91–200 kWh) | **{brl(preco_kwh(180))}/kWh** |
| Preço final até 90 kWh (ICMS isento) / acima de 200 kWh (ICMS 18%) | {brl(preco_kwh(80))} / {brl(preco_kwh(250))} por kWh |
| Conta de energia da família de referência (180 kWh) | **{brl(conta_mensal(180))}/mês** (sem CIP/COSIP) |
| Mesma família com Tarifa Social (80 kWh gratuitos, Lei 15.235/2025 [R5]) | {brl(conta_mensal(180, tarifa_social=True))}/mês |

A tarifa pós-reajuste é **estimada** aplicando o efeito médio residencial às componentes TE e TUSD; a alíquota de ICMS por faixa e o PIS/COFINS efetivo foram observados em faturas reais de 2026 [R2].

## 4. Alternativas comparadas (mesma necessidade, mesmo período)

{tabela_alternativas(r)}

### Mesma comparação para uma família com Tarifa Social

{tabela_alternativas(r_ts)}

{"".join(f"![{i}](graficos/{i})" + chr(10) + chr(10) for i in imgs)}
### Viabilidade e impactos ambientais

| Alternativa | Viabilidade | Impacto ambiental | Limitações |
|---|---|---|---|
""" + "\n".join(f"| {i} | {VIABILIDADE[i]['viabilidade']} | {VIABILIDADE[i]['ambiental']} | {VIABILIDADE[i]['limitacoes']} |" for i in VIABILIDADE) + f"""

## 5. Análise de sensibilidade

As premissas mais incertas foram variadas uma de cada vez (demais valores no cenário base):

{tabela_sens(sens)}

## 6. Conclusões (e como viram respostas do assistente)

1. **Hábitos primeiro (A1).** Banho de {num(v('eficiencia', 'minutos_por_banho_meta'), 0)} min e posição verão por {v('eficiencia', 'meses_posicao_verao')} meses reduzem o chuveiro de {num(ch)} para {num(alts['A1']['chuveiro_kwh_mes'])} kWh/mês, economizando ~{brl(alts['A1']['economia_ano1'])}/ano **sem investimento**. Para famílias na Tarifa Social, a economia em reais é a mesma, porque o consumo continua acima dos 80 kWh gratuitos.
2. **Entre as renováveis, {renov[0]['id']} ({renov[0]['nome'].lower()}) tem menor custo em 10 anos** ({brl(renov[0]['custo_total_10a_base'])}, retorno {pb(renov[0])}) do que {renov[1]['id']} ({brl(renov[1]['custo_total_10a_base'])}, retorno {pb(renov[1])}), no cenário base.
3. **O resultado depende de premissas incertas.** Se o fotovoltaico pequeno custar R$ 7,00/Wp, o retorno de A3 passa a {sens_fv_caro['payback_anos'] if isinstance(sens_fv_caro['payback_anos'], str) else num(sens_fv_caro['payback_anos']) + ' anos'}; se o aquecedor solar custar R$ 5.000, o retorno de A2 cai para {sens_aq_barato['payback_anos'] if isinstance(sens_aq_barato['payback_anos'], str) else num(sens_aq_barato['payback_anos']) + ' anos'}. Por isso o assistente sempre pede orçamentos reais e mostra as premissas.
4. **Melhor combinação: {melhor_combo['id']} ({melhor_combo['nome'].split(': ')[1]})**, com economia de ~{brl(melhor_combo['economia_ano1'])}/ano. Reduzir o consumo antes diminui o tamanho e o preço do equipamento.
5. **Investir ou só mudar hábitos?** Em 10 anos, a melhor renovável isolada custa {brl(renov[0]['custo_total_10a_base'])} contra {brl(alts['A1']['custo_total_10a_base'])} dos hábitos gratuitos (diferença de {brl(abs(alts['A1']['custo_total_10a_base'] - renov[0]['custo_total_10a_base']))}): investimento e manutenção consomem boa parte da economia extra no horizonte de 10 anos. O investimento se destaca quando combinado com hábitos ({melhor_combo['id']}) e ao longo da vida útil completa dos equipamentos (15 a 25 anos). Para quem não tem capital, os hábitos entregam resultado parecido sem risco.
   **Viabilidade social:** as opções renováveis exigem casa própria, telhado adequado e capital ou crédito – barreiras reais para o público. Na Tarifa Social, a economia em reais é a mesma enquanto o consumo líquido continuar acima dos 80 kWh gratuitos; abaixo disso, reduzir mais não diminui a conta.
6. **Impacto ambiental:** com a matriz elétrica brasileira muito renovável, o CO2 evitado por casa é pequeno (até {num(max(a['co2_evitado_kg_ano'] for a in r['alternativas']), 0)} kg/ano). Os ganhos ambientais mais relevantes são reduzir a demanda no horário de pico (18h–21h), quando o sistema recorre a térmicas, e economizar água com banhos curtos. Fabricação e descarte de módulos, inversores e coletores devem ser considerados.

## 7. Parâmetros, origem e tipo de dado

Tipos: **real** = publicado em fonte verificável; **estimado** = calculado a partir de dado real com hipótese explícita; **premissa** = hipótese da equipe, ajustável pelo usuário.

| Parâmetro | Valor | Unidade | Tipo | Fonte | Observação |
|---|---|---|---|---|---|
""" + "\n".join(linhas_param) + """

## 8. Referências

""" + "\n".join(f"* **[{k}]** {r_['titulo']}. {r_['orgao']}. Disponível em: <{r_['url']}>. Acesso em: {r_['acesso']}." for k, r_ in refs.items()) + "\n"

    (DOCS / "analise_energetica.md").write_text(md, encoding="utf-8")
    print("Gerado: docs/analise_energetica.md, resultados/*.csv" + (", docs/graficos/*.png" if imgs else ""))


if __name__ == "__main__":
    main()
