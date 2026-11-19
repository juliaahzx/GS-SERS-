"""Camada conversacional do módulo de energia do Citizen Assist AI.

O assistente interpreta perguntas em português (regras + palavras-chave, sem
depender de serviço externo) e responde usando SOMENTE os cálculos de
`calculos.py` e `alternativas.py`. Toda resposta traz as fontes usadas e um
aviso de que os valores são estimativas.

Integração com o restante do Citizen Assist AI: basta chamar
`AssistenteEnergia().responder(texto)`, que devolve um dicionário com o texto
da resposta, a intenção detectada, os dados calculados e as referências.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from .alternativas import VIABILIDADE, comparar_alternativas
from .calculos import (Perfil, buscar_aparelho, consumo_aparelho_kwh_mes,
                       consumo_chuveiro_kwh_mes, conta_mensal, custo_marginal_kwh,
                       preco_kwh)
from .parametros import RAIZ, carregar_referencias, v

AVISO_PADRAO = ("Valores estimados com tarifa da Enel SP 2026 e premissas descritas no "
                "projeto. A conta real varia com tributos do mês, bandeira tarifária, "
                "iluminação pública e hábitos da casa. Não é garantia de economia.")


def brl(valor: float) -> str:
    s = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def num(valor: float, casas: int = 1) -> str:
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


class AssistenteEnergia:
    def __init__(self, perfil: Perfil | None = None):
        self.perfil = perfil or Perfil()
        self.refs = carregar_referencias()
        self.consumo_informado = False
        self.conta_informada = None

    # ------------------------------------------------------------ perfil ---
    NUMEROS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5,
               "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10}
    FAMILIA = r"(marido|esposa|mulher|esposo|namorad[oa]|companheir[oa]|mae|pai|filh[oa]s?|irma[o]?s?|av[oó]s?|vo|sogr[oa]|net[oa]s?|tia|tio|prim[oa]s?|crianca?s?|amig[oa]s?)"

    def _contar_moradores(self, t: str) -> int | None:
        t = re.sub(r"\b(" + "|".join(self.NUMEROS) + r")\b", lambda m: str(self.NUMEROS[m.group(1)]), t)
        if re.search(r"moro sozinh|so eu\b|apenas eu|somente eu", t):
            return 1
        if m := re.search(r"(\d+)\s*(pessoas|moradores|morador)|somos\s*(\d+)|moramos\s*(?:em\s*)?(\d+)|casa (?:com|de) (\d+)", t):
            return int(next(g for g in m.groups() if g and g.isdigit()))
        if m := re.search(r"(moro com|eu e|vivo com)(.*)", t):
            resto = m.group(2)
            total = 1
            usados = 0
            for qtd, _ in re.findall(r"(\d+)\s*" + self.FAMILIA, resto):
                total += int(qtd)
                usados += 1
            singulares = re.findall(r"(?<!\d )\b(meu|minha|o|a)\s+" + self.FAMILIA, resto)
            total += len(singulares)
            return total if total > 1 else None
        return None

    @staticmethod
    def _kwh_pela_conta(valor: float, tarifa_social: bool, ligacao: str) -> float:
        """Inverte o cálculo da conta: que consumo gera esse valor em reais?"""
        baixo, alto = 0.0, 3000.0
        for _ in range(60):
            meio = (baixo + alto) / 2
            if conta_mensal(meio, tarifa_social, ligacao) < valor:
                baixo = meio
            else:
                alto = meio
        return round(alto)

    def atualizar_perfil(self, t: str) -> list[str]:
        """Lê dados do usuário escritos na pergunta e atualiza o perfil."""
        mudou = []
        p = self.perfil
        mudou_banho = False

        nega_ts = re.search(r"(nao|sem)\s+(tenho|recebo|sou|estou|tem)?\s*(no|na|do|da|a|o)?\s*(tarifa social|cadunico|cad unico|bolsa familia|bpc)", t)
        if nega_ts:
            p.tarifa_social = False
            mudou.append("sem Tarifa Social")
        elif re.search(r"(tenho|recebo|sou da|estou na|com) (a )?tarifa social|cadunico|cad unico|bolsa familia|\bbpc\b", t):
            p.tarifa_social = True
            mudou.append("Tarifa Social ativa")

        if (n := self._contar_moradores(t)) is not None:
            p.moradores = n
            p.banhos_por_dia = n
            mudou_banho = True
            mudou.append(f"{n} morador{'es' if n > 1 else ''}")
        if m := re.search(r"(\d+)\s*banhos?", t):
            p.banhos_por_dia = int(m.group(1))
            mudou_banho = True
            mudou.append(f"{p.banhos_por_dia} banhos/dia")
        if m := re.search(r"(\d+(?:[.,]\d+)?)\s*(min|minutos)\b", t):
            p.minutos_por_banho = float(m.group(1).replace(",", "."))
            mudou_banho = True
            mudou.append(f"banho de {p.minutos_por_banho:g} min")
        if ("chuveiro" in t or "ducha" in t) and (m := re.search(r"(\d[\d.]{3,5})\s*(w|watts)\b", t)):
            p.potencia_chuveiro_w = float(m.group(1).replace(".", ""))
            mudou_banho = True
            mudou.append(f"chuveiro de {p.potencia_chuveiro_w:g} W")
        for tipo in ("monofasico", "bifasico", "trifasico"):
            if tipo in t:
                p.ligacao = tipo
                mudou.append(f"ligação {tipo}")

        if m := re.search(r"(\d+(?:[.,]\d+)?)\s*kwh", t):
            p.consumo_mensal_kwh = float(m.group(1).replace(",", "."))
            self.consumo_informado = True
            mudou.append(f"consumo de {p.consumo_mensal_kwh:g} kWh/mês")
        elif m := re.search(r"r\$\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*(reais|conto)", t):
            valor = float((m.group(1) or m.group(2)).replace(".", "").replace(",", "."))
            p.consumo_mensal_kwh = self._kwh_pela_conta(valor, p.tarifa_social, p.ligacao)
            self.consumo_informado = True
            self.conta_informada = valor
            mudou.append(f"conta de {brl(valor)} ≈ {num(p.consumo_mensal_kwh, 0)} kWh/mês")
        elif mudou_banho and not getattr(self, "consumo_informado", False):
            ch = consumo_chuveiro_kwh_mes(p.potencia_chuveiro_w, p.banhos_por_dia, p.minutos_por_banho)
            p.consumo_mensal_kwh = round(v("consumo", "outros_consumos_referencia") + ch, 1)
            mudou.append(f"consumo estimado da casa {num(p.consumo_mensal_kwh, 0)} kWh/mês")
        return mudou

    # ---------------------------------------------------------- resposta ---
    def responder(self, pergunta: str) -> dict:
        t = normalizar(pergunta)
        self.conta_informada = None
        mudancas = self.atualizar_perfil(t)

        regras = [
            (r"^\s*(obrigad|valeu|brigad|ok\b|beleza|tchau)", self._agradecimento),
            (r"\b(oi|ola|ajuda|menu|o que voce faz|comecar|bom dia|boa tarde|boa noite)\b", self._ajuda),
            (r"fonte|referencia|de onde|origem dos dados", self._fontes),
            (r"limitac|premissa|confiavel|garant|precis", self._limitacoes),
            (r"o que (e|eh|significa|quer dizer)\b(?! (que )?eu)|como funciona|nao entendi", self._conceitos),
            (r"(r\$|reais|conto)|conta (veio|vem|chegou|esta|ta|deu|ficou)|conta .*(cara|alta|absurd|subiu)", self._conta),
            (r"aluguel|alugad|inquilin|apartamento|\bape\b|predio|nao (e|eh) minha", self._aluguel),
            (r"trocar|substituir|troca\b", self._troca),
            (r"(?<!nao tenho )(?<!sem )(?<!nao recebo )(tarifa social|cadunico|cad unico|bolsa familia|\bbpc\b)|gratis|de graca|isencao|isento|baixa renda|luz do povo|desconto na conta", self._tarifa_social),
            (r"compar|alternativ|aquecedor solar|aquecimento solar|placa|painel|paineis|fotovolt|energia solar|renovav|vale a pena|compensa|investir|boiler|melhor opcao|o que (eu )?(faco|fazer)|recomend", self._comparar),
            (r"chuveiro|banho|ducha", self._chuveiro),
            (r"dica|economizar|reduzir|diminuir|gastar menos", self._dicas),
            (r"conta|simul|quanto (vou )?pag|fatura|kwh|reais|r\$", self._conta),
        ]
        handler = None
        for padrao, func in regras:
            if re.search(padrao, t):
                handler = func
                break
        if handler is None and buscar_aparelho(t):
            handler = self._aparelho
        if handler is None:
            handler = self._nao_entendi if not mudancas else self._perfil_atualizado

        resposta = handler(t)
        if mudancas and handler is not self._perfil_atualizado:
            resposta["texto"] = "Considerei: " + ", ".join(mudancas) + ".\n\n" + resposta["texto"]
        fontes = resposta.get("fontes", [])
        if fontes:
            resposta["texto"] += "\n\nFontes: " + "; ".join(
                f"[{r}] {self.refs[r]['orgao']}" for r in fontes)
        if resposta.get("aviso", True):
            resposta["texto"] += "\nAtenção: " + AVISO_PADRAO
        resposta["perfil"] = self.perfil.to_dict()
        resposta["referencias"] = {r: self.refs[r] for r in fontes}
        return resposta

    # -------------------------------------------------------- intenções ---
    def _agradecimento(self, t: str) -> dict:
        return {"intencao": "agradecimento", "aviso": False, "fontes": [],
                "texto": "Por nada! Se quiser, pergunte sobre o chuveiro, a conta de luz, a Tarifa Social ou se vale a pena energia solar."}

    def _conceitos(self, t: str) -> dict:
        texto = (
            "- Potência (W ou kW): é a 'força' do aparelho, quanto ele puxa de energia por instante. Está na etiqueta. "
            "Ex.: chuveiro 5.500 W = 5,5 kW.\n"
            "- kWh (quilowatt-hora): é a energia gasta, o que a conta cobra. kWh = potência em kW x horas ligado. "
            "Um chuveiro de 5,5 kW ligado 1 hora gasta 5,5 kWh.\n"
            f"- Na Enel SP, cada kWh custa hoje cerca de {brl(preco_kwh(self.perfil.consumo_mensal_kwh))} já com impostos.\n"
            "- Bandeira tarifária: valor extra que a ANEEL cobra quando a energia fica mais cara de produzir (amarela, vermelha).\n"
            "- Fio B: parte da tarifa que paga a rede da distribuidora; quem tem placa solar paga uma parte dele sobre a energia que injeta na rede.\n"
            "- Fonte renovável: energia que vem de recurso que se renova, como sol, vento e água."
        )
        return {"intencao": "conceitos", "texto": texto, "fontes": ["R1", "R2", "R3", "R12"], "aviso": False}

    def _aluguel(self, t: str) -> dict:
        r = comparar_alternativas(self.perfil)
        a1 = {a["id"]: a for a in r["alternativas"]}["A1"]
        texto = (
            "Morando de aluguel ou em apartamento, aquecedor solar e placas no telhado só podem ser instalados com "
            "autorização do proprietário ou do condomínio, e o equipamento fica no imóvel. Por isso, o que mais compensa é:\n"
            f"1) Hábitos (sem custo): banho de 6 min e posição verão economizam ~{brl(a1['economia_ano1'])}/ano "
            f"({num(a1['kwh_evitados_ano'], 0)} kWh/ano a menos).\n"
            "2) Conversar com o proprietário: aquecedor solar valoriza o imóvel e pode ser negociado no aluguel.\n"
            "3) Energia solar por assinatura (geração compartilhada): algumas empresas oferecem desconto na conta sem instalar "
            "nada em casa. Leia o contrato com atenção: prazo, multa de saída e se o desconto é sobre a tarifa ou só sobre a energia.\n"
            "4) Se a família for do CadÚnico, confira se já recebe a Tarifa Social (80 kWh/mês gratuitos)."
        )
        return {"intencao": "aluguel", "texto": texto, "fontes": ["R7", "R5", "R12"]}

    def _troca(self, t: str) -> dict:
        preco = custo_marginal_kwh(self.perfil.consumo_mensal_kwh, self.perfil.tarifa_social)
        qtd = 1
        if m := re.search(r"(\d+)\s*(lampadas|lampada|aparelhos|unidades)", t):
            qtd = int(m.group(1))
        horas = 5.0
        if m := re.search(r"(\d+(?:[.,]\d+)?)\s*(h|horas)\b", t):
            horas = float(m.group(1).replace(",", "."))
        if "lampada" in t or "led" in t:
            antiga = 15 if "fluorescente" in t else 60
            nome = "fluorescente compacta de 15 W" if antiga == 15 else "incandescente de 60 W"
            kwh = (antiga - 9) / 1000 * horas * 30 * qtd
            texto = (f"Trocar {qtd} lâmpada{'s' if qtd > 1 else ''} {nome} por LED de 9 W, acesas {num(horas)} h/dia:\n"
                     f"({antiga} W - 9 W) x {num(horas)} h x 30 dias x {qtd} = {num(kwh)} kWh/mês a menos, "
                     f"cerca de {brl(kwh * preco)} por mês ({brl(kwh * preco * 12)} por ano).\n"
                     "Uma lâmpada LED custa poucos reais e dura muitos anos, então a troca se paga rápido.")
            return {"intencao": "troca", "texto": texto, "fontes": ["R7", "R1", "R2"]}
        if "geladeira" in t:
            texto = ("Para a geladeira, compare o consumo em kWh/mês das etiquetas INMETRO da antiga e da nova: "
                     "a diferença x preço do kWh é a economia mensal. "
                     f"Cada kWh/mês a menos vale cerca de {brl(preco)} por mês.")
            return {"intencao": "troca", "texto": texto, "fontes": ["R7", "R1", "R2"]}
        return self._comparar(t)

    def _ajuda(self, t: str) -> dict:
        texto = (
            "Sou o módulo de energia do Citizen Assist AI. Ajudo famílias da Grande São Paulo "
            "a entender e reduzir a conta de luz, com foco no maior vilão da casa: o chuveiro elétrico.\n"
            "Você pode perguntar, por exemplo:\n"
            "- Quanto gasta meu chuveiro? (diga quantas pessoas e quantos minutos de banho)\n"
            "- Vale a pena aquecedor solar ou placa solar?\n"
            "- Quanto vou pagar com 150 kWh?\n"
            "- Tenho direito à conta de luz grátis? (Tarifa Social)\n"
            "- Quanto gasta uma geladeira / ar-condicionado / lâmpada?\n"
            "- Me dá dicas para economizar\n"
            "- Quais são as fontes? / Quais as limitações?"
        )
        return {"intencao": "ajuda", "texto": texto, "fontes": [], "aviso": False}

    def _perfil_atualizado(self, t: str) -> dict:
        p = self.perfil
        texto = (f"Anotei. Perfil atual: {p.moradores} morador{'es' if p.moradores != 1 else ''}, {p.banhos_por_dia} banho{'s' if p.banhos_por_dia != 1 else ''}/dia de "
                 f"{p.minutos_por_banho:g} min, chuveiro de {p.potencia_chuveiro_w:g} W, consumo de "
                 f"{p.consumo_mensal_kwh:g} kWh/mês, Tarifa Social: {'sim' if p.tarifa_social else 'não'}.\n"
                 "Agora pergunte, por exemplo: 'quanto gasta meu chuveiro?' ou 'vale a pena aquecedor solar?'")
        return {"intencao": "perfil", "texto": texto, "fontes": [], "aviso": False}

    def _fontes(self, t: str) -> dict:
        linhas = [f"[{k}] {r['titulo']} - {r['orgao']}. {r['url']}" for k, r in self.refs.items()]
        return {"intencao": "fontes", "texto": "Referências usadas nos cálculos:\n" + "\n".join(linhas),
                "fontes": [], "aviso": False}

    def _limitacoes(self, t: str) -> dict:
        texto = (
            "Como os números são calculados e onde podem errar:\n"
            "- A tarifa usa TE+TUSD da Enel SP de 2025/26 com o reajuste residencial médio de 9,02% (jul/2026). "
            "A tarifa exata da sua conta pode ser diferente: confira os valores 'Tarifa unit' na sua fatura.\n"
            "- PIS/COFINS muda todo mês (usamos 4,5%). ICMS em SP: 0% até 90 kWh, 12% até 200 kWh, 18% acima.\n"
            "- Não incluímos a taxa de iluminação pública (CIP/COSIP) nem multas ou parcelamentos.\n"
            "- Bandeira tarifária: usamos a média de 2026; anos mais secos podem ter bandeira vermelha.\n"
            "- Aquecedor solar: supomos que o sol forneça 70% do aquecimento; depende do telhado, sombra e uso.\n"
            "- Placas solares: o valor do Fio B da Enel SP foi estimado (R$ 0,15/kWh) e a regra após 2029 ainda não está definida.\n"
            "- Preços de equipamentos são médias de mercado em 2026; peça ao menos 3 orçamentos.\n"
            "- Hábitos (minutos de banho, posição do chuveiro) mudam muito a economia real."
        )
        return {"intencao": "limitacoes", "texto": texto, "fontes": ["R1", "R2", "R3", "R8", "R11", "R12"], "aviso": False}

    def _tarifa_social(self, t: str) -> dict:
        lim = v("tarifa_social", "limite_gratuidade_kwh")
        c = self.perfil.consumo_mensal_kwh
        com = conta_mensal(c, tarifa_social=True, ligacao=self.perfil.ligacao)
        sem = conta_mensal(c, tarifa_social=False, ligacao=self.perfil.ligacao)
        texto = (
            f"Pela Lei 15.235/2025, famílias inscritas no CadÚnico com renda de até meio salário mínimo por pessoa "
            f"(e pessoas que recebem BPC) não pagam a energia dos primeiros {lim} kWh do mês. O que passar de {lim} kWh "
            "é cobrado normalmente. O benefício é automático, mas o CadÚnico precisa estar atualizado e a conta "
            "deve estar no nome de alguém da família.\n"
            f"Com consumo de {num(c, 0)} kWh/mês, a parte de energia da conta fica em torno de {brl(com)} com o benefício, "
            f"contra {brl(sem)} sem ele.\n"
        )
        if c > lim:
            excesso = c - lim
            ch = consumo_chuveiro_kwh_mes(self.perfil.potencia_chuveiro_w, self.perfil.banhos_por_dia,
                                          self.perfil.minutos_por_banho)
            texto += (f"Você está {num(excesso, 0)} kWh acima do limite gratuito. Cada kWh acima custa cerca de "
                      f"{brl(custo_marginal_kwh(c))}. O chuveiro sozinho gasta ~{num(ch, 0)} kWh/mês: reduzir o banho "
                      "e usar a posição verão é o caminho mais rápido para se aproximar do limite.")
        else:
            texto += "Seu consumo já está dentro do limite gratuito: reduzir ainda mais não muda o valor da energia na conta, mas ajuda a manter a margem nos meses mais quentes ou frios."
        texto += ("\nFamílias com renda entre meio e um salário mínimo por pessoa têm um desconto menor "
                  "(isenção de um encargo, a CDE) até 120 kWh/mês.")
        return {"intencao": "tarifa_social", "texto": texto, "fontes": ["R5", "R1", "R2"],
                "dados": {"conta_com_beneficio": round(com, 2), "conta_sem_beneficio": round(sem, 2)}}

    def _chuveiro(self, t: str) -> dict:
        p = self.perfil
        kwh = consumo_chuveiro_kwh_mes(p.potencia_chuveiro_w, p.banhos_por_dia, p.minutos_por_banho)
        preco = custo_marginal_kwh(p.consumo_mensal_kwh, p.tarifa_social)
        custo = kwh * preco
        por_banho = p.potencia_chuveiro_w / 1000 * p.minutos_por_banho / 60 * preco_kwh(p.consumo_mensal_kwh)
        um_min = p.potencia_chuveiro_w / 1000 / 60 * p.banhos_por_dia * 30
        parte = kwh / p.consumo_mensal_kwh if p.consumo_mensal_kwh else 0
        texto = (
            f"Cálculo: energia = potência x tempo. {num(p.potencia_chuveiro_w / 1000, 1)} kW x "
            f"{p.banhos_por_dia} banho{'s' if p.banhos_por_dia != 1 else ''} x {p.minutos_por_banho:g} min x 30 dias = {num(kwh)} kWh por mês.\n"
            f"Isso custa cerca de {brl(custo)} por mês ({brl(por_banho)} por banho) e representa ~{parte:.0%} "
            f"do consumo da casa ({num(p.consumo_mensal_kwh, 0)} kWh/mês).\n"
            f"Cada minuto a menos em todos os banhos economiza ~{num(um_min)} kWh/mês (≈ {brl(um_min * preco)}).\n"
            "Para reduzir: banhos mais curtos e posição 'verão' nos dias quentes. Se puder investir, pergunte "
            "'vale a pena aquecedor solar ou placa solar?' para ver a comparação completa."
        )
        if p.tarifa_social and p.consumo_mensal_kwh <= v("tarifa_social", "limite_gratuidade_kwh"):
            texto += "\nComo seu consumo está dentro dos 80 kWh gratuitos da Tarifa Social, a economia aparece como margem de segurança, não como desconto na conta."
        return {"intencao": "chuveiro", "texto": texto, "fontes": ["R7", "R1", "R2"],
                "dados": {"kwh_mes": round(kwh, 1), "custo_mes": round(custo, 2)}}

    def _comparar(self, t: str) -> dict:
        r = comparar_alternativas(self.perfil)
        alts = {a["id"]: a for a in r["alternativas"]}
        linhas = []
        for a in r["alternativas"]:
            pb = ("imediato" if a["payback_anos"] == 0 else
                  "não se paga" if a["payback_anos"] is None else
                  f"{num(a['payback_anos'])} anos")
            linhas.append(
                f"{a['id']} {a['nome']}{' (renovável)' if a['renovavel'] else ''}: "
                f"chuveiro {num(a['chuveiro_kwh_mes'])} kWh/mês | conta {brl(a['conta_mes_ano1'])}/mês | "
                f"economia {brl(a['economia_ano1'])}/ano | investimento {brl(a['investimento'])} | retorno {pb} | "
                f"custo total em 10 anos {brl(a['custo_total_10a_base'])}")
        texto = (
            f"Necessidade: água quente para {self.perfil.banhos_por_dia} banhos/dia. Situação atual: o chuveiro gasta "
            f"{num(r['chuveiro_base_kwh_mes'])} kWh/mês e a parte de energia da conta fica em ~{brl(r['conta_base_mes'])}/mês.\n"
            f"Comparação (período de 12 meses e custo total em {r['horizonte_anos']} anos, tarifa constante):\n\n"
            + "\n".join(linhas) + "\n\nRecomendação:\n" + self._recomendacao(r)
        )
        return {"intencao": "comparar", "texto": texto,
                "fontes": ["R7", "R1", "R2", "R8", "R11", "R12", "R10", "R13"],
                "dados": r, "viabilidade": VIABILIDADE}

    def _recomendacao(self, r: dict) -> str:
        """Monta a recomendação a partir dos números calculados (nada é fixo no texto)."""
        alts = {a["id"]: a for a in r["alternativas"]}
        a1, a2, a3 = alts["A1"], alts["A2"], alts["A3"]
        vida_aq = v("aquecedor_solar", "vida_util_anos")
        partes = [f"1) Comece pelos hábitos (A1): custo zero e economia de ~{brl(a1['economia_ano1'])}/ano "
                  f"({num(a1['kwh_evitados_ano'], 0)} kWh/ano a menos)."]

        renov = sorted([a for a in r["alternativas"] if a["id"] in ("A2", "A3")],
                       key=lambda a: a["custo_total_10a_base"])
        melhor, outra = renov
        def retorno(a):
            return "não se paga" if a["payback_anos"] is None else f"retorno em ~{num(a['payback_anos'])} anos"
        partes.append(
            f"2) Entre as fontes renováveis, {melhor['nome'].lower()} ({melhor['id']}) tem o menor custo em "
            f"{r['horizonte_anos']} anos ({brl(melhor['custo_total_10a_base'])}; {retorno(melhor)}), contra "
            f"{brl(outra['custo_total_10a_base'])} de {outra['id']} ({retorno(outra)}).")
        if a2["payback_anos"] and a2["payback_anos"] > r["horizonte_anos"]:
            cabe = "dentro" if a2["payback_anos"] <= vida_aq else "além"
            partes.append(
                f"   O aquecedor solar economiza energia de verdade (~{num(a2['kwh_evitados_ano'], 0)} kWh/ano), mas com o preço "
                f"de {brl(a2['investimento'])} e só {self.perfil.banhos_por_dia} banhos/dia o retorno fica {cabe} da sua vida útil "
                f"(~{vida_aq} anos). Ele compensa mais se o orçamento for menor, com mais moradores ou com banhos mais longos.")
        partes.append(
            f"   Placas solares exigem telhado próprio, homologação e investimento de ~{brl(a3['investimento'])}; o resultado depende "
            "muito do preço de sistemas pequenos e do Fio B, que sobe até 2029.")

        combos = sorted([alts["A4"], alts["A5"]], key=lambda a: a["custo_total_10a_base"])
        partes.append(f"3) Melhor combinação: {combos[0]['nome'].split(': ')[1]} ({combos[0]['id']}), com economia de "
                      f"~{brl(combos[0]['economia_ano1'])}/ano. Fazer os hábitos antes reduz o tamanho (e o preço) do equipamento.")

        diferenca = a1["custo_total_10a_base"] - melhor["custo_total_10a_base"]
        partes.append(
            f"4) Investir ou só mudar hábitos? Em {r['horizonte_anos']} anos, {melhor['id']} sozinho custa "
            f"{brl(abs(diferenca))} {'a menos' if diferenca >= 0 else 'a mais'} que os hábitos gratuitos (A1), porque investimento "
            "e manutenção consomem parte da economia. Se não houver dinheiro ou crédito barato, os hábitos já trazem resultado parecido; "
            "o investimento compensa mais junto com os hábitos e ao longo da vida útil do equipamento (15 a 25 anos).")
        if self.perfil.tarifa_social:
            partes.append(
                "   Com Tarifa Social, a economia em reais é a mesma enquanto o consumo continuar acima dos 80 kWh gratuitos; "
                "procure também programas sociais que instalam aquecedores solares antes de investir do próprio bolso.")
        partes.append(
            f"Impacto ambiental: a matriz elétrica brasileira é muito renovável (~{num(v('ambiental', 'fator_emissao_sin') * 1000, 1)} gCO2/kWh), "
            f"então o CO2 evitado por uma casa é pequeno (de {num(a1['co2_evitado_kg_ano'], 0)} a "
            f"{num(max(a['co2_evitado_kg_ano'] for a in r['alternativas']), 0)} kg/ano). O ganho maior é tirar carga do horário de pico "
            "(18h-21h), quando o sistema aciona térmicas, e economizar água com banhos mais curtos.")
        return "\n".join(partes)

    def _conta(self, t: str) -> dict:
        p = self.perfil
        c = p.consumo_mensal_kwh
        valor = conta_mensal(c, p.tarifa_social, p.ligacao)
        if self.conta_informada:
            ch = consumo_chuveiro_kwh_mes(p.potencia_chuveiro_w, p.banhos_por_dia, p.minutos_por_banho)
            um_min = p.potencia_chuveiro_w / 1000 / 60 * p.banhos_por_dia * 30
            preco = custo_marginal_kwh(c, p.tarifa_social)
            texto = (f"Uma conta de {brl(self.conta_informada)} na Enel SP corresponde a cerca de {num(c, 0)} kWh/mês "
                     "(a conta real também tem iluminação pública, então seu consumo pode ser um pouco menor; confira o kWh na fatura).\n"
                     f"Com {p.banhos_por_dia} banhos/dia de {p.minutos_por_banho:g} min, o chuveiro deve gastar ~{num(ch, 0)} kWh "
                     f"(~{min(ch / c, 1):.0%} da conta, se esses números baterem com sua casa).\n"
                     "O que fazer, do mais rápido ao que exige investimento:\n"
                     f"1) Banho: cada minuto a menos em todos os banhos economiza ~{brl(um_min * preco)}/mês; posição verão nos dias quentes.\n"
                     "2) Geladeira, ar-condicionado e lâmpadas antigas: pergunte quanto cada um gasta.\n"
                     + ("3) Seu consumo passa de 200 kWh: em SP isso aumenta o ICMS de 12% para 18% sobre a conta toda.\n" if c > 200 else "")
                     + "Se a casa for própria, pergunte 'vale a pena aquecedor solar ou placa solar?'. "
                     "Se a família for do CadÚnico, pergunte sobre a Tarifa Social.")
            return {"intencao": "conta", "texto": texto, "fontes": ["R1", "R2", "R7"],
                    "dados": {"consumo_estimado_kwh": c}}
        if not self.consumo_informado and re.search(r"cara|alta|absurd|subiu", t):
            texto = ("Para eu ajudar com números, me diga o valor ou o consumo da conta, por exemplo: "
                     "'minha conta veio 230 reais' ou 'gasto 210 kWh' (o kWh aparece na fatura, em 'consumo').\n"
                     "Enquanto isso, o que mais pesa numa casa típica: chuveiro elétrico (cerca de metade da conta), "
                     "geladeira (fica ligada 24 h) e ar-condicionado. Em SP, passar de 200 kWh também aumenta o ICMS de 12% para 18% "
                     "sobre a conta inteira.")
            return {"intencao": "conta", "texto": texto, "fontes": ["R7", "R2"], "aviso": False}
        texto = (f"Para {num(c, 0)} kWh/mês na Enel SP, a parte de energia da conta fica em torno de {brl(valor)} "
                 f"(preço final ~{brl(preco_kwh(c))}/kWh com tributos"
                 f"{', já aplicando a Tarifa Social' if p.tarifa_social else ''}).\n"
                 "Em SP o ICMS muda conforme o consumo: até 90 kWh é isento, de 91 a 200 kWh é 12% e acima de 200 kWh é 18% "
                 "sobre todo o consumo. Por isso, passar de 200 para 201 kWh encarece a conta inteira.")
        if 200 < c <= 230:
            economia = conta_mensal(c, p.tarifa_social, p.ligacao) - conta_mensal(200, p.tarifa_social, p.ligacao)
            texto += f"\nVocê está logo acima de 200 kWh: voltar para 200 kWh reduziria a conta em ~{brl(economia)}."
        return {"intencao": "conta", "texto": texto, "fontes": ["R1", "R2", "R3", "R4"],
                "dados": {"consumo_kwh": c, "conta": round(valor, 2)}}

    def _aparelho(self, t: str) -> dict:
        ap = buscar_aparelho(t)
        horas = None
        if m := re.search(r"(\d+(?:[.,]\d+)?)\s*(h|horas)\b", t):
            horas = float(m.group(1).replace(",", "."))
        elif re.search(r"(o )?dia (todo|inteiro)|24 ?h", t):
            horas = 24.0
        potencia = None
        if m := re.search(r"(\d+)\s*(w|watts)\b", t):
            potencia = float(m.group(1))
        qtd = 1
        if m := re.search(r"(\d+)\s*(lampadas|aparelhos|unidades)", t):
            qtd = int(m.group(1))
        kwh = consumo_aparelho_kwh_mes(ap, potencia, horas, qtd)
        preco = custo_marginal_kwh(self.perfil.consumo_mensal_kwh, self.perfil.tarifa_social)
        if ap.get("kwh_mes_fixo") and potencia is None:
            como = "valor de referência (etiqueta INMETRO, ligada 24 h)"
        else:
            p = potencia or ap["potencia_w"]
            h = horas or ap["horas_dia"]
            como = f"{num(p, 0)} W x {num(h)} h/dia x {ap['dias_mes']:g} dias" + (f" x {qtd}" if qtd > 1 else "")
        texto = (f"{ap['aparelho'].capitalize()}: {como} = {num(kwh)} kWh/mês, cerca de {brl(kwh * preco)} por mês.\n"
                 + (f"Observação: {ap['obs']}.\n" if ap["obs"] else "") +
                 "Para um valor mais exato, use a potência da etiqueta do seu aparelho e diga quantas horas por dia ele fica ligado "
                 "(ex.: 'ar-condicionado 1200 W 6 horas').")
        return {"intencao": "aparelho", "texto": texto, "fontes": [ap["fonte"], "R1", "R2"],
                "dados": {"aparelho": ap["aparelho"], "kwh_mes": round(kwh, 1)}}

    def _dicas(self, t: str) -> dict:
        p = self.perfil
        preco = custo_marginal_kwh(p.consumo_mensal_kwh, p.tarifa_social)
        um_min = p.potencia_chuveiro_w / 1000 / 60 * p.banhos_por_dia * 30
        lamp = (60 - 9) / 1000 * 5 * 30
        texto = (
            "Dicas em ordem de impacto para uma casa típica:\n"
            f"1) Chuveiro: cada minuto a menos em todos os banhos economiza ~{num(um_min)} kWh/mês ({brl(um_min * preco)}). "
            "Use a posição verão nos dias quentes e evite ligar entre 18h e 21h quando possível.\n"
            "2) Geladeira: não deixe a porta aberta, afaste da parede e do fogão, confira a borracha da porta. "
            "Na troca, prefira etiqueta A do INMETRO/Selo Procel.\n"
            f"3) Iluminação: trocar uma lâmpada incandescente de 60 W por LED de 9 W (5 h/dia) economiza ~{num(lamp)} kWh/mês por lâmpada.\n"
            "4) Ferro e máquina de lavar: junte roupas e use de uma vez.\n"
            "5) Ar-condicionado: portas e janelas fechadas, 23-24 °C, filtros limpos.\n"
            "Quer saber quanto um aparelho específico gasta? Pergunte, por exemplo: 'quanto gasta minha geladeira?'"
        )
        return {"intencao": "dicas", "texto": texto, "fontes": ["R7", "R1", "R2"]}

    def _nao_entendi(self, t: str) -> dict:
        r = self._ajuda(t)
        r["intencao"] = "nao_entendi"
        r["texto"] = "Não entendi bem. " + r["texto"]
        return r


# ------------------------------------------------------------ feedback ---
ARQUIVO_FEEDBACK = RAIZ / "resultados" / "feedback_testes.csv"


def registrar_feedback(cenario: str, entendeu: str, nota_utilidade: int, comentario: str,
                       arquivo: Path = ARQUIVO_FEEDBACK) -> None:
    """Guarda o retorno de um teste com usuário SEM dados pessoais (sem nome, telefone ou endereço)."""
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    novo = not arquivo.exists()
    with open(arquivo, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(["data_hora", "cenario", "entendeu_resposta", "nota_utilidade_1a5", "comentario"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), cenario, entendeu, nota_utilidade, comentario])
