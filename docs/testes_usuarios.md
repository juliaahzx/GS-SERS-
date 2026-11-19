# Testes com usuários

> **Status:** protocolo definido e testes internos de usabilidade realizados (seção 4.2), com os ajustes aplicados. Os testes com usuários externos (seção 3) estão em andamento e serão registrados aqui conforme forem concluídos.
> Nenhum dado pessoal é registrado (sem nome, telefone, endereço ou CPF). Use apenas um código (P1, P2...) e uma descrição geral do perfil.

## 1. Objetivo

Verificar se as orientações de energia do Citizen Assist AI são **compreensíveis** e **úteis** para o público (famílias da Grande SP com chuveiro elétrico) e ajustar as respostas a partir dos comentários.

## 2. Protocolo (cerca de 10 minutos por pessoa, 3 a 5 pessoas)

1. Explique que é um teste de um assistente sobre conta de luz e que nenhum dado pessoal será guardado.
2. Abra `python -m citizen_energy --web` (ou o chat de terminal) e peça para a pessoa fazer, com as próprias palavras:
   * **S1 – Chuveiro:** perguntar quanto o chuveiro da casa dela gasta (informando moradores e tempo de banho).
   * **S2 – Comparação:** perguntar se vale a pena aquecedor solar ou placa solar.
   * **S3 – Tarifa Social:** perguntar se tem direito à conta de luz grátis.
   * **S4 – Livre:** qualquer dúvida sobre a conta de luz.
3. Depois de cada resposta, pergunte:
   * "Com suas palavras, o que o assistente recomendou?" (verifica compreensão)
   * "De 1 a 5, quanto isso ajuda você a decidir algo?" (utilidade)
   * "Alguma palavra ou número que ficou confuso?"
4. Registre no formulário "Registrar teste com usuário" da interface web (ou `/feedback` no terminal). Os registros vão para `resultados/feedback_testes.csv`.
5. Anote na tabela da seção 3 e, se houver ajuste, descreva na seção 4.

**Critério de sucesso:** a pessoa resume corretamente a recomendação principal e dá nota ≥ 4 em pelo menos 3 dos 4 cenários.

## 3. Registro dos testes com usuários externos

| Código | Perfil geral (sem dados pessoais) | Cenário | Entendeu? (sim/parcial/não) | Utilidade (1–5) | Comentário | Ajuste gerado |
|---|---|---|---|---|---|---|
| P1 | | S1 | | | | |
| P1 | | S2 | | | | |
| P1 | | S3 | | | | |
| P2 | | S1 | | | | |
| P2 | | S2 | | | | |
| P2 | | S3 | | | | |
| P3 | | S1 | | | | |
| P3 | | S2 | | | | |
| P3 | | S3 | | | | |

Exemplos de perfil geral: "adulta, 4 moradores, casa alugada", "aposentado, mora sozinho, tem Tarifa Social".

## 4. Ajustes realizados

### 4.1 Ajustes a partir dos testes com usuários externos

| Comentário recebido | Ajuste feito no assistente | Arquivo alterado |
|---|---|---|
| | | |

### 4.2 Ajustes de testes internos da equipe (já realizados)

Testes feitos pela equipe durante o desenvolvimento, **não substituem** os testes com usuários acima.

| Situação testada | Problema encontrado | Ajuste |
|---|---|---|
| Pergunta "quanto vou pagar" | A busca de aparelhos encontrava "ar" (ar-condicionado) dentro de "pagar" | Busca passou a usar palavras inteiras (`calculos.buscar_aparelho`) |
| Comparação de alternativas | O texto da recomendação era fixo e dizia que placas solares não compensavam, contrariando os números calculados | Recomendação passou a ser montada a partir dos resultados (`AssistenteEnergia._recomendacao`) e um teste garante que os valores citados são os da análise |
| Fotovoltaico com conta baixa | A conta com placas caía para a faixa isenta de ICMS, inflando a economia | Preço do kWh passou a seguir o consumo bruto retirado da rede (cenário conservador) |
| Fotovoltaico x outras opções | O sistema era arredondado para 2 módulos e gerava 34% mais que a necessidade, tornando a comparação injusta | Dimensionamento exato para a mesma necessidade; número de módulos aparece só como referência |
| Resposta sobre geladeira | Frase repetia o mesmo valor duas vezes | Texto simplificado |
| Teste de linguagem natural: 17 frases informais ("luz de graça", "somos 3", "moro com meu marido e 2 filhos", "minha conta veio 250 reais", "moro de aluguel", "qual a melhor opção pra mim", "obrigada", "o que é kWh") | 9 frases não eram entendidas ou caíam na resposta errada | Novas intenções (aluguel, troca de lâmpadas, conceitos, agradecimento, diagnóstico da conta em reais); contagem de moradores em linguagem natural; negação de CadÚnico/Bolsa Família; frases viraram testes automáticos (`tests/test_assistente.py`) |
| Banho de 15 min com 4 pessoas | O chuveiro aparecia como 92% de uma casa fixa de 180 kWh | Quando o usuário não informa o consumo, a casa passa a ser estimada como 92 kWh (outros aparelhos) + chuveiro |
| "Minha conta veio 250 reais" | O valor em reais era ignorado | O assistente converte reais em kWh (inverte o cálculo da tarifa) e faz um diagnóstico da conta |
| Gráfico de economia anual | Barras com e sem Tarifa Social ficavam iguais (consumo continua acima de 80 kWh), sem informação nova | Substituído por gráfico de energia e CO2 evitados |
