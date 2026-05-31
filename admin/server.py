import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from access_control.acl import load_acl_config
from config import ADMIN_HOST, ADMIN_PORT, BASE_DIR, PROXY_HOST, PROXY_PORT
from logger.logger import get_latest_logs, get_log_dir
from proxy.handler import ProxyHandler
from stats import _read_logs, parse_logs


STATIC_DIR = Path(__file__).resolve().parent / "static"


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def get_summary():
    lines = _read_logs()
    total, hits, url_counter = parse_logs(lines)
    misses = total - hits
    hit_rate = (hits / total * 100) if total else 0.0
    return {
        "total": total,
        "hits": hits,
        "misses": misses,
        "hit_rate": round(hit_rate, 2),
        "top_urls": [
            {"url": url, "count": count}
            for url, count in url_counter.most_common(5)
        ],
    }


def get_status(admin_host=ADMIN_HOST, admin_port=ADMIN_PORT):
    return {
        "proxy_host": PROXY_HOST,
        "proxy_port": PROXY_PORT,
        "admin_host": admin_host,
        "admin_port": admin_port,
        "log_dir": get_log_dir(),
    }


def get_cache_snapshot():
    stats = ProxyHandler._cache.get_stats()
    snapshot = ProxyHandler._cache.snapshot()
    return {
        **stats,
        "entries": snapshot["entries"],
    }


def clear_cache_entries():
    before = ProxyHandler._cache.snapshot()["size"]
    ProxyHandler._cache.clear()
    return {
        "ok": True,
        "cleared": before,
        "cache": get_cache_snapshot(),
    }


def clear_logs():
    deleted = 0
    log_dir = Path(get_log_dir())
    if log_dir.is_dir():
        for path in log_dir.glob("*.log"):
            if path.is_file():
                try:
                    path.unlink()
                    deleted += 1
                except OSError:
                    pass

    legacy_log = BASE_DIR / "proxy.log"
    if legacy_log.is_file():
        try:
            legacy_log.unlink()
            deleted += 1
        except OSError:
            pass

    return {
        "ok": True,
        "deleted": deleted,
        "summary": get_summary(),
        "logs": get_latest_logs(100),
    }


class AdminRequestHandler(BaseHTTPRequestHandler):
    server_version = "ProxyAdmin/1.0"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api(parsed)
            return
        self._serve_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/cache/clear":
            self._send_json(clear_cache_entries())
        elif parsed.path == "/api/logs/clear":
            self._send_json(clear_logs())
        else:
            self._send_json({"error": "not found"}, status=404)

    def _handle_api(self, parsed):
        query = parse_qs(parsed.query)
        path = parsed.path

        if path == "/api/status":
            self._send_json(self._status_payload())
        elif path == "/api/summary":
            self._send_json(get_summary())
        elif path == "/api/logs":
            limit = self._parse_limit(query.get("limit", ["100"])[0])
            self._send_json({"entries": get_latest_logs(limit)})
        elif path == "/api/cache":
            self._send_json(get_cache_snapshot())
        elif path == "/api/acl":
            self._send_json(load_acl_config())
        elif path == "/api/dashboard":
            limit = self._parse_limit(query.get("limit", ["100"])[0])
            self._send_json({
                "status": self._status_payload(),
                "summary": get_summary(),
                "logs": get_latest_logs(limit),
                "cache": get_cache_snapshot(),
                "acl": load_acl_config(),
            })
        else:
            self._send_json({"error": "not found"}, status=404)

    def _serve_static(self, request_path):
        if request_path in ("", "/"):
            target = STATIC_DIR / "index.html"
        else:
            target = STATIC_DIR / request_path.lstrip("/")

        try:
            resolved = target.resolve()
            static_root = STATIC_DIR.resolve()
            if static_root not in resolved.parents and resolved != static_root:
                self.send_error(403)
                return
            if not resolved.is_file():
                self.send_error(404)
                return
            content = resolved.read_bytes()
        except OSError:
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload, status=200):
        content = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _status_payload(self):
        admin_host, admin_port = self.server.server_address[:2]
        return get_status(admin_host, admin_port)

    @staticmethod
    def _parse_limit(raw):
        try:
            return max(1, min(500, int(raw)))
        except (TypeError, ValueError):
            return 100

    def log_message(self, fmt, *args):
        return


def start_admin_server(host=ADMIN_HOST, port=ADMIN_PORT):
    try:
        server = ThreadingHTTPServer((host, port), AdminRequestHandler)
    except OSError as exc:
        print(f"[!] Admin server failed on {host}:{port}: {exc}")
        return

    print(f"[*] Admin dashboard started on http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    start_admin_server()
