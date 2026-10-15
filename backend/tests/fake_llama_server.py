"""Faux llama-server pour les tests de la surveillance de l'IA locale (aucun modèle, aucune donnée).

Répond comme llama-server sur /health, /slots, /v1/models et /v1/chat/completions (flux SSE ou JSON).
`--fige` reproduit le blocage constaté le 15/10/2026 : /health répond « ok », mais /slots montre une
demande qui n'avance plus et les complétions ne répondent jamais.

usage : python fake_llama_server.py --port 8099 [--fige]
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    frozen = False

    def log_message(self, *_args) -> None:
        pass

    def _json(self, code: int, data) -> None:
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            return self._json(200, {"status": "ok"})
        if self.path == "/slots":
            return self._json(200, [{"id": 0, "is_processing": self.frozen, "id_task": 7,
                                     "n_prompt_tokens_processed": 150, "next_token": [{"n_decoded": 12}]}])
        if self.path == "/v1/models":
            return self._json(200, {"data": [{"id": "faux"}]})
        return self._json(404, {"error": "inconnu"})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if self.frozen:
            time.sleep(3600)  # figé : la demande reste sans réponse
            return
        if not body.get("stream"):
            return self._json(200, {"choices": [{"message": {"content": "Bonjour coach."}, "finish_reason": "stop"}],
                                    "model": "faux"})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for part in ("Bonjour", " coach."):
            chunk = {"choices": [{"delta": {"content": part}, "finish_reason": None}], "model": "faux"}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.flush()
        end = {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 2}}
        self.wfile.write(f"data: {json.dumps(end)}\n\ndata: [DONE]\n\n".encode())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--fige", action="store_true")
    args = parser.parse_args()
    Handler.frozen = args.fige
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
