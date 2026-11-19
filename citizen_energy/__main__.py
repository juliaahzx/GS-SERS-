"""Chat de terminal do módulo de energia.

Uso:
    python -m citizen_energy            # conversa interativa
    python -m citizen_energy --web      # abre a interface web em http://localhost:8000
    python -m citizen_energy "vale a pena aquecedor solar?"   # pergunta única

Comandos no chat: /perfil, /feedback, /sair
"""

import sys

from .assistente import AssistenteEnergia, registrar_feedback


def coletar_feedback() -> None:
    print("\nRegistro de teste com usuário (não informe nome, telefone ou endereço).")
    cenario = input("Cenário testado (ex.: 'chuveiro 5 pessoas'): ").strip()
    entendeu = input("A pessoa entendeu a resposta? (sim/parcial/não): ").strip()
    nota = input("Nota de utilidade de 1 a 5: ").strip()
    comentario = input("Comentário da pessoa / ajuste sugerido: ").strip()
    try:
        nota_int = max(1, min(5, int(nota)))
    except ValueError:
        nota_int = 0
    registrar_feedback(cenario, entendeu, nota_int, comentario)
    print("Registrado em resultados/feedback_testes.csv\n")


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--web":
        from .web import rodar
        rodar()
        return

    assistente = AssistenteEnergia()
    if args:
        print(assistente.responder(" ".join(args))["texto"])
        return

    print("Citizen Assist AI - Energia (digite 'ajuda', /perfil, /feedback ou /sair)\n")
    while True:
        try:
            pergunta = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not pergunta:
            continue
        if pergunta in ("/sair", "sair", "exit"):
            break
        if pergunta == "/perfil":
            print(assistente.perfil.to_dict(), "\n")
            continue
        if pergunta == "/feedback":
            coletar_feedback()
            continue
        print("\nAssistente:", assistente.responder(pergunta)["texto"], "\n")


if __name__ == "__main__":
    main()
