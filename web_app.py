from pathlib import Path
import time
import traceback

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from core.agente import AgenteMaritimo

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "web" / "templates"),
    static_folder=str(BASE_DIR / "web" / "static"),
)
agente = AgenteMaritimo()


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/chat")
def chat():
    inicio = time.perf_counter()
    try:
        payload = request.get_json(silent=True) or {}
        message = (payload.get("message") or "").strip()
        history = payload.get("history") or []

        if not message:
            return jsonify({"error": "Mensagem vazia."}), 400

        resposta = agente.ask(message, history)
        duracao = time.perf_counter() - inicio
        print(f"[web_app] /api/chat concluido em {duracao:.2f}s")
        return jsonify({"reply": resposta, "duration_seconds": round(duracao, 2)})
    except Exception as exc:
        duracao = time.perf_counter() - inicio
        print(f"[web_app] erro em /api/chat apos {duracao:.2f}s: {exc}")
        traceback.print_exc()
        return jsonify({
            "error": f"Erro interno ao consultar o agente: {exc}",
            "duration_seconds": round(duracao, 2),
        }), 500


if __name__ == "__main__":
    app.run(debug=True, port=8000, threaded=True)
