"""Testes da integração dos cálculos às respostas do assistente."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from citizen_energy.alternativas import comparar_alternativas  # noqa: E402
from citizen_energy.assistente import AssistenteEnergia, brl, registrar_feedback  # noqa: E402
from citizen_energy.calculos import Perfil  # noqa: E402


class TestAssistente(unittest.TestCase):
    def setUp(self):
        self.bot = AssistenteEnergia()

    def test_intencoes(self):
        casos = {
            "oi": "ajuda",
            "quanto gasta meu chuveiro?": "chuveiro",
            "vale a pena aquecedor solar?": "comparar",
            "placa solar compensa?": "comparar",
            "tenho direito a tarifa social?": "tarifa_social",
            "quanto vou pagar com 150 kwh?": "conta",
            "quanto gasta uma geladeira?": "aparelho",
            "me da dicas para economizar": "dicas",
            "quais as fontes?": "fontes",
            "quais as limitações?": "limitacoes",
        }
        for pergunta, intencao in casos.items():
            self.assertEqual(AssistenteEnergia().responder(pergunta)["intencao"], intencao, pergunta)

    def test_frases_do_dia_a_dia(self):
        """Frases informais usadas no teste interno de linguagem natural."""
        casos = {
            "tenho direito a luz de graça?": "tarifa_social",
            "recebo bolsa familia": "tarifa_social",
            "nao tenho cadunico, quanto pago com 180 kwh": "conta",
            "minha conta veio 250 reais, o que eu faço?": "conta",
            "a conta ta muito cara": "conta",
            "eu moro de aluguel, posso por aquecedor solar?": "aluguel",
            "qual a melhor opção pra mim?": "comparar",
            "e se eu trocar 10 lampadas incandescentes por led?": "troca",
            "o que é kwh?": "conceitos",
            "obrigada": "agradecimento",
            "lâmpada": "aparelho",
        }
        for pergunta, intencao in casos.items():
            self.assertEqual(AssistenteEnergia().responder(pergunta)["intencao"], intencao, pergunta)

    def test_conta_negativa_desliga_tarifa_social(self):
        bot = AssistenteEnergia()
        bot.responder("nao tenho cadunico")
        self.assertFalse(bot.perfil.tarifa_social)

    def test_conta_em_reais_vira_kwh(self):
        from citizen_energy.calculos import conta_mensal
        bot = AssistenteEnergia()
        bot.responder("minha conta veio 250 reais")
        self.assertAlmostEqual(conta_mensal(bot.perfil.consumo_mensal_kwh), 250, delta=2)

    def test_conta_moradores_em_linguagem_natural(self):
        casos = {"moro com meu marido e 2 filhos": 4, "somos 3": 3, "somos cinco pessoas": 5,
                 "moro sozinha": 1, "eu e minha mãe": 2}
        for frase, n in casos.items():
            bot = AssistenteEnergia()
            bot.responder(frase)
            self.assertEqual(bot.perfil.moradores, n, frase)

    def test_consumo_da_casa_acompanha_banho(self):
        bot = AssistenteEnergia()
        bot.responder("somos 4 e o banho dura 15 minutos")
        self.assertGreater(bot.perfil.consumo_mensal_kwh, 165)  # chuveiro sozinho = 165 kWh

    def test_extrai_perfil(self):
        self.bot.responder("somos 5 pessoas, banho de 10 minutos, chuveiro de 7500 W e gastamos 250 kWh")
        p = self.bot.perfil
        self.assertEqual((p.moradores, p.banhos_por_dia, p.minutos_por_banho, p.potencia_chuveiro_w, p.consumo_mensal_kwh),
                         (5, 5, 10, 7500, 250))

    def test_resposta_coerente_com_analise(self):
        """O valor citado pelo assistente é exatamente o da análise."""
        r = comparar_alternativas(Perfil())
        resposta = AssistenteEnergia().responder("compare as alternativas")["texto"]
        for a in r["alternativas"]:
            self.assertIn(brl(a["custo_total_10a_base"]), resposta)

    def test_resposta_traz_fontes_e_aviso(self):
        texto = self.bot.responder("quanto gasta meu chuveiro?")["texto"]
        self.assertIn("Fontes:", texto)
        self.assertIn("Não é garantia", texto)

    def test_tarifa_social_ativa_pelo_texto(self):
        self.bot.responder("estou no cadunico")
        self.assertTrue(self.bot.perfil.tarifa_social)

    def test_feedback_sem_dados_pessoais(self):
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d) / "fb.csv"
            registrar_feedback("chuveiro", "sim", 5, "claro", arquivo=arq)
            cabecalho = arq.read_text(encoding="utf-8").splitlines()[0]
            for campo in ("nome", "telefone", "email", "endereco", "cpf"):
                self.assertNotIn(campo, cabecalho)


if __name__ == "__main__":
    unittest.main()
