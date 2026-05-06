from unittest.mock import patch

from cache.cache_manager import CacheManager
from proxy.handler import ProxyHandler


class FakeClientSocket:
    def __init__(self, request_bytes):
        self._request_bytes = request_bytes
        self.sent = b""
        self.closed = False
        self._read_once = False

    def recv(self, _size):
        if self._read_once:
            return b""
        self._read_once = True
        return self._request_bytes

    def sendall(self, data):
        self.sent += data

    def close(self):
        self.closed = True


class FakeRemoteSocket:
    def __init__(self, response_bytes):
        self._response_bytes = response_bytes
        self.sent = b""
        self._read_once = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def recv(self, _size):
        if self._read_once:
            return b""
        self._read_once = True
        return self._response_bytes

    def sendall(self, data):
        self.sent += data


def test_handler_blocked_returns_403():
    ProxyHandler._cache = CacheManager()
    req = (
        b"GET http://blocked.com/ HTTP/1.1\r\n"
        b"Host: blocked.com\r\n"
        b"\r\n"
    )
    client = FakeClientSocket(req)

    with patch("proxy.handler.is_allowed", return_value=False), patch("proxy.handler.log_request") as log_mock:
        ProxyHandler.handle(client, ("127.0.0.1", 12345))

    assert b"403 Forbidden" in client.sent
    assert client.closed is True
    log_mock.assert_called_once()


def test_handler_forwards_http_and_rewrites_headers():
    ProxyHandler._cache = CacheManager()
    req = (
        b"GET http://example.com/path?q=1 HTTP/1.1\r\n"
        b"Host: example.com\r\n"
        b"X-Forwarded-For: 1.1.1.1\r\n"
        b"User-Agent: test-agent\r\n"
        b"\r\n"
    )
    resp = b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhello"
    client = FakeClientSocket(req)
    remote = FakeRemoteSocket(resp)

    with patch("proxy.handler.is_allowed", return_value=True), patch(
        "proxy.handler.socket.create_connection", return_value=remote
    ), patch("proxy.handler.log_request") as log_mock:
        ProxyHandler.handle(client, ("127.0.0.1", 12345))

    outbound_text = remote.sent.decode("iso-8859-1", errors="ignore")
    assert outbound_text.startswith("GET /path?q=1 HTTP/1.1")
    assert "X-Forwarded-For:" not in outbound_text
    assert "X-Proxy-Server: http-proxy-cache" in outbound_text
    assert b"200 OK" in client.sent
    log_mock.assert_called_once()
