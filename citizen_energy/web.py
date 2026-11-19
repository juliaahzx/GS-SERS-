"""Servidor web mínimo (somente biblioteca padrão) para demonstrar o assistente.

    python -m citizen_energy --web     ->  http://localhost:8000

Endpoints:
    GET  /                  interface de chat
    POST /api/perguntar     {"pergunta": "...", "sessao": "id"}  -> resposta do assistente
    POST /api/feedback      {"cenario", "entendeu", "nota", "comentario"} -> grava teste com usuário
    GET  /api/alternativas  comparação completa para o perfil padrão (JSON)
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .alternativas import comparar_alternativas
from .assistente import AssistenteEnergia, registrar_feedback

STATIC = Path(__file__).resolve().parent / "static"
SESSOES: dict[str, AssistenteEnergia] = {}


class Handler(BaseHTTPRequestHandler):
    def _json(self, dados: dict, status: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/index.html"):
            corpo = (STATIC / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
        elif self.path == "/api/alternativas":
            self._json(comparar_alternativas())
        else:
            self._json({"erro": "não encontrado"}, 404)

    def do_POST(self):  # noqa: N802
        tamanho = int(self.headers.get("Content-Length", 0))
        try:
            dados = json.loads(self.rfile.read(tamanho) or b"{}")
        except json.JSONDecodeError:
            self._json({"erro": "JSON inválido"}, 400)
            return
        if self.path == "/api/perguntar":
            sessao = str(dados.get("sessao", "padrao"))[:64]
            assistente = SESSOES.setdefault(sessao, AssistenteEnergia())
            resposta = assistente.responder(str(dados.get("pergunta", ""))[:500])
            resposta.pop("dados", None)
            resposta.pop("viabilidade", None)
            self._json(resposta)
        elif self.path == "/api/feedback":
            try:
                nota = int(dados.get("nota", 0))
            except (TypeError, ValueError):
                nota = 0
            registrar_feedback(str(dados.get("cenario", ""))[:200], str(dados.get("entendeu", ""))[:20],
                               nota, str(dados.get("comentario", ""))[:500])
            self._json({"ok": True})
        else:
            self._json({"erro": "não encontrado"}, 404)

    def log_message(self, *args):  # silencia o log padrão
        pass


def rodar(porta: int = 8000) -> None:
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    print(f"Citizen Assist AI - Energia rodando em http://localhost:{porta}  (Ctrl+C para sair)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
