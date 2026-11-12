"""
Servidor HTTP local do Instalador de Impressoras.

- SPA em Bootstrap servida de /static
- API JSON em /api/*
- Eventos ao vivo (log/progresso/lista) via Server-Sent Events em /api/events
- Escuta apenas em 127.0.0.1 e exige um token de sessao (cookie HttpOnly),
  evitando que outra pagina local use o instalador.
"""
import json
import mimetypes
import os
import queue
import secrets
import threading
import time
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import api
from app.data import paths

STATIC = paths.STATIC_DIR

TOKEN = os.environ.get("PI_TOKEN") or secrets.token_urlsafe(24)
COOKIE = "pitoken"

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("audio/mpeg", ".mp3")
mimetypes.add_type("audio/ogg", ".ogg")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")


class Handler(BaseHTTPRequestHandler):
    server_version = "PrinterInstaller"
    sys_version = ""

    # ------------------------------------------------------------------
    # infra
    # ------------------------------------------------------------------
    def log_message(self, fmt, *args):  # silencia o log no console
        pass

    def _client_ip_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost", "[::1]", "::1")

    def _auth_ok(self, query=None):
        if not self._client_ip_ok():
            return False
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie") or "")
        except Exception:
            pass
        if cookie.get(COOKIE) and cookie[COOKIE].value == TOKEN:
            return True
        header = self.headers.get("X-Auth-Token")
        if header and header == TOKEN:
            return True
        if query:
            t = (query.get("t") or [""])[0]
            if t and t == TOKEN:
                return True
        return False

    def _send(self, code, body=b"", ctype="text/plain; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False),
                   "application/json; charset=utf-8")

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except Exception:
            n = 0
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            if not self._auth_ok(query):
                self._send(403, "<h1>403</h1><p>Abra o instalador pelo "
                                "atalho/app para obter o link de acesso.</p>",
                           "text/html; charset=utf-8")
                return
            extra = []
            if (query.get("t") or [""])[0]:
                extra.append(("Set-Cookie",
                              f"{COOKIE}={TOKEN}; Path=/; HttpOnly; SameSite=Strict"))
            self._send(200, (STATIC / "index.html").read_text(encoding="utf-8"),
                       "text/html; charset=utf-8", extra)
            return

        if path.startswith("/static/"):
            if not self._auth_ok(query):
                self._send(403, "403")
                return
            self._static(path[len("/static/"):])
            return

        if path == "/api/state":
            if not self._auth_ok(query):
                self._json({"error": "nao autorizado"}, 403)
                return
            self._json(api.snapshot())
            return

        if path == "/api/events":
            if not self._auth_ok(query):
                self._json({"error": "nao autorizado"}, 403)
                return
            self._sse()
            return

        if path == "/api/installed":
            if not self._auth_ok(query):
                self._json({"error": "nao autorizado"}, 403)
                return
            self._json({"printers": api.list_installed()})
            return

        self._send(404, "404")

    def _static(self, rel):
        rel = rel.replace("\\", "/")
        target = (STATIC / rel).resolve()
        try:
            target.relative_to(STATIC.resolve())
        except Exception:
            self._send(403, "403")
            return
        if not target.is_file():
            self._send(404, "404")
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",
                                                  "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    # ------------------------------------------------------------------
    # SSE
    # ------------------------------------------------------------------
    def _sse(self):
        self.protocol_version = "HTTP/1.0"
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        q = api.STATE.bus.subscribe()
        try:
            for msg in api.replay_snapshot():
                self.wfile.write(f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                                 .encode("utf-8"))
            self.wfile.flush()
            while True:
                try:
                    msg = q.get(timeout=15)
                    self.wfile.write(
                        f"data: {json.dumps(msg, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            api.STATE.bus.unsubscribe(q)

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if not self._auth_ok(query):
            self._json({"error": "nao autorizado"}, 403)
            return
        data = self._body()
        try:
            if path == "/api/scan":
                self._json(api.start_scan(data.get("cidrs")))
            elif path == "/api/test-ip":
                self._json(api.start_test_ip(data.get("ip")))
            elif path == "/api/resolve":
                self._json(api.start_resolve())
            elif path == "/api/install":
                self._json(api.start_install(data.get("uids") or data.get("ips") or []))
            elif path == "/api/test-page":
                self._json(api.start_test_page(data.get("uids") or data.get("ips") or []))
            elif path == "/api/remove":
                self._json(api.start_remove(
                    data.get("names") or [],
                    keep_virtual=bool(data.get("keep_virtual", True)),
                    remove_ports=bool(data.get("remove_ports", True)),
                    remove_drivers=bool(data.get("remove_drivers", False))))
            elif path == "/api/cancel":
                self._json(api.cancel_operation())
            elif path == "/api/settings":
                api.set_auto_download(data.get("auto_download", True))
                self._json({"ok": True, "auto_download": api.STATE.auto_download})
            elif path == "/api/open-drivers":
                self._json(api.open_drivers_folder())
            else:
                self._json({"error": "rota desconhecida"}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)


# --------------------------------------------------------------------------
def start_server(host="127.0.0.1", port=8765):
    """Sobe o servidor HTTP. Retorna (httpd, url_com_token)."""
    httpd = None
    for attempt in range(20):
        try:
            httpd = ThreadingHTTPServer((host, port + attempt), Handler)
            break
        except OSError:
            continue
    if httpd is None:
        raise RuntimeError("Nenhuma porta local disponivel para o servidor.")
    httpd.daemon_threads = True
    real_port = httpd.server_address[1]
    url = f"http://{host}:{real_port}/?t={TOKEN}"
    return httpd, url


def serve(host="127.0.0.1", port=8765, open_browser=True, wait=True):
    httpd, url = start_server(host, port)
    real_port = httpd.server_address[1]
    print("=" * 70)
    print("  Instalador de Impressoras  —  interface web")
    print("-" * 70)
    print(f"  Interface : {url}")
    print(f"  API       : http://{host}:{real_port}/api/...")
    print("  Feche esta janela ou pressione Ctrl+C para encerrar.")
    print("=" * 70)
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    if wait:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nEncerrado.")
        finally:
            httpd.shutdown()
    return httpd, url
