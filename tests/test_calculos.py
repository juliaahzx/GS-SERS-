"""Testes dos cálculos de energia (python -m unittest discover -s tests)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from citizen_energy.alternativas import comparar_alternativas, dimensionar_fv  # noqa: E402
from citizen_energy.calculos import (Perfil, aliquota_icms, conta_mensal,  # noqa: E402
                                     consumo_chuveiro_kwh_mes, energia_kwh, preco_kwh,
                                     tarifa_sem_tributos)
from citizen_energy.parametros import carregar_parametros, carregar_referencias  # noqa: E402


class TestEnergia(unittest.TestCase):
    def test_energia_potencia_tempo(self):
        # 1.000 W por 1 h/dia durante 30 dias = 30 kWh
        self.assertAlmostEqual(energia_kwh(1000, 1, 30), 30.0)

    def test_chuveiro_cenario_referencia(self):
        # 5.500 W, 4 banhos de 8 min/dia -> 88 kWh/mês (valor publicado em R7)
        self.assertAlmostEqual(consumo_chuveiro_kwh_mes(5500, 4, 8), 88.0, places=6)


class TestTarifa(unittest.TestCase):
    def test_faixas_icms_sp(self):
        self.assertEqual(aliquota_icms(90), 0.0)
        self.assertEqual(aliquota_icms(91), 0.12)
        self.assertEqual(aliquota_icms(200), 0.12)
        self.assertEqual(aliquota_icms(201), 0.18)

    def test_tarifa_reproduz_fatura_real(self):
        # Fatura B1 de jan/2026 (R2): TUSD+TE com tributos e ICMS 12% = 0,51660 + 0,34957
        # Sem reajuste e sem bandeira, nosso cálculo deve ficar a menos de 1,5% desse valor.
        p = carregar_parametros()["tarifa"]
        base = p["tusd_pre_reajuste"]["valor"] + p["te_pre_reajuste"]["valor"]
        calculado = base / (1 - p["pis_cofins_efetivo"]["valor"] - 0.12)
        self.assertAlmostEqual(calculado, 0.51660 + 0.34957, delta=0.015 * 0.86617)

    def test_reajuste_aplicado(self):
        self.assertGreater(tarifa_sem_tributos(False), 0.72518)
        self.assertAlmostEqual(tarifa_sem_tributos(False), 0.72518 * 1.0902, places=4)

    def test_preco_sobe_com_faixa(self):
        self.assertLess(preco_kwh(80), preco_kwh(150))
        self.assertLess(preco_kwh(150), preco_kwh(250))

    def test_custo_disponibilidade(self):
        # Bifásico paga no mínimo 50 kWh
        self.assertAlmostEqual(conta_mensal(10, ligacao="bifasico"), conta_mensal(50, ligacao="bifasico"))

    def test_tarifa_social_80_kwh(self):
        self.assertEqual(conta_mensal(80, tarifa_social=True), 0)
        self.assertAlmostEqual(conta_mensal(100, tarifa_social=True), 20 * preco_kwh(100))


class TestAlternativas(unittest.TestCase):
    def setUp(self):
        self.r = comparar_alternativas(Perfil())
        self.a = {x["id"]: x for x in self.r["alternativas"]}

    def test_todas_alternativas_presentes(self):
        self.assertEqual(set(self.a), {"A0", "A1", "A2", "A3", "A4", "A5"})

    def test_ha_alternativa_renovavel(self):
        self.assertTrue(any(x["renovavel"] for x in self.r["alternativas"]))

    def test_mesmo_horizonte(self):
        for x in self.r["alternativas"]:
            self.assertEqual(len(x["contas_anuais"]), self.r["horizonte_anos"])

    def test_alternativas_economizam(self):
        for i in ("A1", "A2", "A3", "A4", "A5"):
            self.assertGreater(self.a[i]["economia_ano1"], 0, i)

    def test_combinacao_economiza_mais_que_partes(self):
        self.assertGreater(self.a["A4"]["economia_ano1"], self.a["A2"]["economia_ano1"])
        self.assertGreater(self.a["A5"]["economia_ano1"], self.a["A1"]["economia_ano1"])

    def test_fv_dimensionado_para_necessidade(self):
        fv = dimensionar_fv(88)
        self.assertAlmostEqual(fv["geracao_kwh_mes"], 88, places=6)

    def test_fio_b_reduz_economia_ao_longo_do_tempo(self):
        contas = self.a["A3"]["contas_anuais"]
        self.assertGreater(contas[-1], contas[0])

    def test_toda_fonte_citada_existe(self):
        refs = carregar_referencias()
        for grupo, itens in carregar_parametros().items():
            if grupo.startswith("_"):
                continue
            for chave, p in itens.items():
                self.assertIn(p["tipo"], ("real", "estimado", "premissa"), chave)
                if p["fonte"] != "-":
                    self.assertIn(p["fonte"], refs, chave)


if __name__ == "__main__":
    unittest.main()
