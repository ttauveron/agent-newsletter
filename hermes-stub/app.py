import json
import logging
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import psycopg2

NEWSLETTER_ENGINE_URL = os.environ["NEWSLETTER_ENGINE_URL"]
DATABASE_URL = os.environ["DATABASE_URL"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _post_json(url: str, data: dict) -> None:
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req) as r:
        log.info("POST %s → %s", url, r.status)


class StubHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length))
        log.info("Received webhook: %s %s", self.path, payload)

        try:
            if self.path == "/webhooks/daily-digest":
                self._handle_digest(payload)
            elif self.path == "/webhooks/user-message":
                self._handle_user_message(payload)
            self.send_response(200)
        except Exception:
            log.exception("Stub error processing %s", self.path)
            self.send_response(500)
        self.end_headers()

    def _handle_digest(self, payload: dict) -> None:
        date = payload["date"]
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM digests WHERE digest_date = %s LIMIT 1", (date,)
                )
                row = cur.fetchone()
        if not row:
            raise ValueError(f"No digest found for date {date}")
        _post_json(
            f"{NEWSLETTER_ENGINE_URL}/actions/send-digest",
            {"digest_id": str(row[0]), "content": "Stub e2e digest"},
        )

    def _handle_user_message(self, payload: dict) -> None:
        _post_json(
            f"{NEWSLETTER_ENGINE_URL}/actions/send-reply",
            {"user_message_id": payload["message_id"], "content": "Stub e2e reply"},
        )

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8644), StubHandler)
    log.info("Hermes stub listening on :8644")
    server.serve_forever()
