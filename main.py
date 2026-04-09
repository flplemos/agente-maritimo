import itertools
import sys
import threading
import time

from dotenv import load_dotenv

from core.agente import AgenteMaritimo

load_dotenv()


def _iniciar_spinner(mensagem: str = "Consultando mar e gerando resposta"):
    stop_event = threading.Event()

    def _rodar():
        for frame in itertools.cycle(["|", "/", "-", "\\"]):
            if stop_event.is_set():
                break
            sys.stdout.write(f"\r{mensagem}... {frame}")
            sys.stdout.flush()
            time.sleep(0.12)
        sys.stdout.write("\r" + " " * (len(mensagem) + 8) + "\r")
        sys.stdout.flush()

    thread = threading.Thread(target=_rodar, daemon=True)
    thread.start()
    return stop_event, thread


def iniciar_agente():
    print("Montando o orquestrador do Agente Marítimo...\n")
    agente = AgenteMaritimo()

    print("🌊 Agente Marítimo Online! Digite 'sair' para encerrar.")
    print("-" * 50)

    chat_history: list[dict[str, str]] = []

    while True:
        pergunta = input("\nVocê: ").strip()

        if pergunta.lower() in ["sair", "exit", "quit"]:
            print("Encerrando o agente. Boas ondas!")
            break

        if not pergunta:
            print("Digite uma pergunta ou 'sair' para encerrar.")
            continue

        stop_event = None
        spinner_thread = None
        try:
            stop_event, spinner_thread = _iniciar_spinner()
            resposta = agente.ask(pergunta, chat_history)
            stop_event.set()
            spinner_thread.join()

            print(f"\n🏄 Agente: {resposta}")

            chat_history.append({"role": "user", "content": pergunta})
            chat_history.append({"role": "assistant", "content": resposta})
            if len(chat_history) > 6:
                chat_history = chat_history[-6:]
        except Exception as e:
            if stop_event:
                stop_event.set()
            if spinner_thread:
                spinner_thread.join()
            print(f"\n❌ Erro durante a execução: {e}")


if __name__ == "__main__":
    iniciar_agente()
