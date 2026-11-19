# Citizen Assist AI – Módulo de Energia Consciente

**Global Solution 2026.2 · Ciência da Computação (1CC) · FIAP**
**Disciplina:** Soluções em Energias Renováveis e Sustentáveis

> Este repositório contém **a contribuição da disciplina Soluções em Energias Renováveis e Sustentáveis** ao Citizen Assist AI: análise de consumo, comparação de alternativas (incluindo fontes renováveis) e integração dos resultados às respostas do assistente.

## Integrantes

| Nome | RM |
|---|---|
| Julia Nunes Frederici | 569858 |

## Público e problema

* **Público:** famílias de baixa e média renda da Região Metropolitana de São Paulo (área da Enel SP), incluindo famílias do CadÚnico que têm direito à Tarifa Social.
* **Necessidade energética:** reduzir o gasto com **aquecimento de água para o banho**. O chuveiro elétrico representa cerca de metade do consumo de uma casa típica (88 de 180 kWh/mês no cenário de referência) e concentra demanda no horário de pico.
* **Como o assistente ajuda:** explica quanto cada hábito ou aparelho custa, compara alternativas de economia e de fonte renovável com números, custos e limitações, e orienta sobre a Tarifa Social. Detalhes em [`docs/contexto.md`](docs/contexto.md).

## Funcionalidades de energia no assistente

| Pergunta do usuário (exemplos) | O que o assistente faz |
|---|---|
| "Somos 5 pessoas, quanto gasta o chuveiro?" | Calcula E = P × t, custo mensal, custo por banho e quanto 1 minuto a menos economiza |
| "Vale a pena aquecedor solar ou placa solar?" | Compara 6 alternativas para a mesma necessidade (12 meses e 10 anos) e recomenda com base nos números |
| "Tenho tarifa social e gasto 150 kWh" | Aplica a Lei 15.235/2025 (80 kWh gratuitos) e mostra quanto falta para o limite |
| "Quanto vou pagar com 210 kWh?" | Estima a conta com tarifa Enel SP 2026, PIS/COFINS e faixas de ICMS de SP |
| "Quanto gasta uma geladeira / ar-condicionado 1200 W 6 horas?" | Consumo e custo de aparelhos (tabela Procel/INMETRO ou dados do usuário) |
| "Dicas para economizar" / "Fontes" / "Limitações" | Dicas por impacto, referências e premissas das estimativas |

Toda resposta traz **fontes** e um **aviso de que os valores são estimativas**, não resultados garantidos.

## Principais resultados (família de 4 pessoas, Enel SP)

| Alternativa | Conta energia (R$/mês) | Economia (R$/ano) | Investimento | Retorno | Custo em 10 anos |
|---|---|---|---|---|---|
| A0 Situação atual (chuveiro 5.500 W, 8 min) | 172,12 | – | – | – | 20.654 |
| A1 Hábitos (6 min + posição verão) | 137,89 | 411 | R$ 0 | imediato | 16.546 |
| A2 Aquecedor solar de água (renovável) | 113,22 | 707 | R$ 7.000 | 12,6 anos | 22.086 |
| A3 Fotovoltaico 0,82 kWp (renovável) | 96,27 | 910 | R$ 3.434 | 4,2 anos | 16.467 |
| A4 Hábitos + aquecedor solar | 102,95 | 830 | R$ 7.000 | 10,3 anos | 20.854 |
| A5 Hábitos + fotovoltaico menor | 92,90 | 951 | R$ 2.037 | 2,4 anos | 14.469 |

Análise completa, fórmulas, sensibilidade, viabilidade e impactos ambientais: **[`docs/analise_energetica.md`](docs/analise_energetica.md)**.

## Como executar

Requisitos: Python 3.10+. O assistente usa só a biblioteca padrão; `matplotlib` é opcional (gráficos da análise).

```bash
git clone <url-do-repositorio>
cd gs-energia-citizen-assist
pip install -r requirements.txt          # opcional, só para os gráficos

python -m citizen_energy                 # chat no terminal (/perfil, /feedback, /sair)
python -m citizen_energy --web           # interface web em http://localhost:8000
python -m citizen_energy "vale a pena aquecedor solar?"   # pergunta única

python analise/gerar_analise.py          # recalcula a análise, tabelas e gráficos
python -m unittest discover -s tests -v  # testes automatizados
```

### Integração com o restante do Citizen Assist AI

```python
from citizen_energy import AssistenteEnergia

energia = AssistenteEnergia()
resposta = energia.responder("quanto gasta meu chuveiro? somos 3 pessoas")
resposta["texto"]        # resposta pronta para o usuário (com fontes e aviso)
resposta["intencao"]     # chuveiro, comparar, tarifa_social, conta, aparelho, dicas...
resposta["referencias"]  # fontes usadas na resposta
```

Também há uma API HTTP: `POST /api/perguntar` com `{"pergunta": "...", "sessao": "id"}`.

## Estrutura do repositório

```
dados/
  parametros.json      todos os valores usados, com unidade, tipo (real/estimado/premissa) e fonte
  referencias.json     fontes verificáveis [R1]..[R13]
  aparelhos.csv        potência e uso típico de aparelhos
citizen_energy/
  calculos.py          energia, potência, tarifa, ICMS, Tarifa Social
  alternativas.py      comparação das alternativas (mesma necessidade, 12 meses e 10 anos)
  assistente.py        respostas do assistente + registro de testes com usuários
  web.py, static/      interface web de demonstração
analise/gerar_analise.py   gera docs/analise_energetica.md, resultados/*.csv e gráficos
docs/
  contexto.md          público, necessidade e como as orientações ajudam
  analise_energetica.md  cálculos, comparação, sensibilidade, conclusões (gerado)
  limitacoes.md        premissas e limitações das estimativas
  testes_usuarios.md   protocolo, registros dos testes e ajustes realizados
  roteiro_video.md     roteiro do vídeo técnico (até 3 min)
  graficos/            gráficos da análise
resultados/            tabelas CSV da comparação e da sensibilidade
tests/                 testes automatizados
```

## Dados, referências e limitações

* Origem, unidade, período e tipo de cada dado: [`dados/parametros.json`](dados/parametros.json) e seção 7 da análise.
* Referências: [`dados/referencias.json`](dados/referencias.json) e seção 8 da análise.
* Limitações e condições das recomendações: [`docs/limitacoes.md`](docs/limitacoes.md).
* Testes com usuários e ajustes: [`docs/testes_usuarios.md`](docs/testes_usuarios.md).

## Links

* Vídeo técnico (YouTube, não listado): 
