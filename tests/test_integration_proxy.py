"""
Integration tests: start a local HTTP server, then proxy requests through it.

Requires the proxy server to be importable and able to handle real TCP connections.
"""

import threading
import time
import socket
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

import pytest

import config
from proxy.server import start_server


class _TestHTTPHandler(BaseHTTPRequestHandler):
    """Simple HTTP server that echoes back the request path and method."""

    def do_GET(self):
        body = f"GET {self.path}".encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body_in = self.rfile.read(length) if length else b""
        body = f"POST {self.path} body={body_in.decode()}".encode()
        self.send_response(201)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def _find_free_port():
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def local_server():
    """Start a local HTTP test server on a random port."""
    port = _find_free_port()
    server = HTTPServer(("127.0.0.1", port), _TestHTTPHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.1)
    yield port
    server.shutdown()


@pytest.fixture(scope="module")
def proxy_server():
    """Start the proxy server on a random port."""
    proxy_port = _find_free_port()
    orig_host, orig_port = config.PROXY_HOST, config.PROXY_PORT
    config.PROXY_HOST = "127.0.0.1"
    config.PROXY_PORT = proxy_port

    t = threading.Thread(target=start_server, kwargs={"host": "127.0.0.1", "port": proxy_port}, daemon=True)
    t.start()
    time.sleep(0.3)
    yield proxy_port

    config.PROXY_HOST = orig_host
    config.PROXY_PORT = orig_port


def test_proxy_http_get(local_server, proxy_server):
    """Send a GET request through proxy, verify response."""
    proxy_url = f"http://127.0.0.1:{proxy_server}"
    target_url = f"http://127.0.0.1:{local_server}/hello"

    proxy_handler = urllib.request.ProxyHandler({"http": proxy_url})
    opener = urllib.request.build_opener(proxy_handler)

    resp = opener.open(target_url, timeout=5)
    assert resp.status == 200
    body = resp.read()
    assert b"GET /hello" in body


def test_cache_hit_miss(local_server, proxy_server):
    """Access same URL twice: first MISS, second HIT (via log)."""
    import os
    from logger.logger import _LOG_DIR, get_today_log_path

    proxy_url = f"http://127.0.0.1:{proxy_server}"
    target_url = f"http://127.0.0.1:{local_server}/cachetest"

    proxy_handler = urllib.request.ProxyHandler({"http": proxy_url})
    opener = urllib.request.build_opener(proxy_handler)

    # First request - should be MISS
    resp1 = opener.open(target_url, timeout=5)
    assert resp1.status == 200
    resp1.read()

    # Second request - should be HIT (cached)
    resp2 = opener.open(target_url, timeout=5)
    assert resp2.status == 200
    resp2.read()


def test_proxy_get_returns_content(local_server, proxy_server):
    """Verify proxy returns valid content."""
    proxy_url = f"http://127.0.0.1:{proxy_server}"
    target_url = f"http://127.0.0.1:{local_server}/test"

    proxy_handler = urllib.request.ProxyHandler({"http": proxy_url})
    opener = urllib.request.build_opener(proxy_handler)

    resp = opener.open(target_url, timeout=5)
    body = resp.read()
    assert resp.status == 200
    assert len(body) > 0


def test_concurrent_requests(local_server, proxy_server):
    """Fire multiple concurrent requests; all should succeed."""
    import concurrent.futures

    proxy_url = f"http://127.0.0.1:{proxy_server}"
    target_url = f"http://127.0.0.1:{local_server}/concurrent"
    proxy_handler = urllib.request.ProxyHandler({"http": proxy_url})

    def make_request(i):
        opener = urllib.request.build_opener(proxy_handler)
        resp = opener.open(target_url, timeout=10)
        return resp.status, resp.read()

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(make_request, i) for i in range(10)]
        results = [f.result(timeout=15) for f in futures]

    for status, body in results:
        assert status == 200
        assert len(body) > 0
