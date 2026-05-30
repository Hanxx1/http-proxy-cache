"""
Tests for HTTPS CONNECT tunnel.

Note: full HTTPS CONNECT requires a real TLS endpoint.
These tests verify the CONNECT handshake and tunnel mechanism
using a plain TCP echo server as the tunnel target.
"""

import threading
import time
import socket

import config


def _find_free_port():
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def test_connect_handshake():
    """Verify CONNECT request through the proxy receives 200 Connection Established
    when the target is available."""
    from proxy.server import start_server

    proxy_port = _find_free_port()
    echo_port = _find_free_port()

    # Start a simple echo server as the tunnel target
    def echo_server():
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", echo_port))
        server.listen(1)
        conn, _ = server.accept()
        data = conn.recv(4096)
        conn.sendall(data)
        conn.close()
        server.close()

    echo_thread = threading.Thread(target=echo_server, daemon=True)
    echo_thread.start()

    # Start proxy
    t = threading.Thread(
        target=start_server,
        kwargs={"host": "127.0.0.1", "port": proxy_port},
        daemon=True,
    )
    t.start()
    time.sleep(0.3)

    # Send CONNECT request via raw socket
    client = socket.socket()
    client.connect(("127.0.0.1", proxy_port))
    req = f"CONNECT 127.0.0.1:{echo_port} HTTP/1.1\r\nHost: 127.0.0.1:{echo_port}\r\n\r\n"
    client.sendall(req.encode())

    response = client.recv(4096).decode()
    assert "200" in response, f"Expected 200 Connection Established, got: {response}"
    client.close()


def test_connect_blocked_by_acl():
    """CONNECT to a blacklisted host should return 403."""
    import access_control.acl as acl_mod
    from proxy.server import start_server

    proxy_port = _find_free_port()

    orig_mode = acl_mod.get_mode()
    acl_mod.set_mode("blacklist")

    t = threading.Thread(
        target=start_server,
        kwargs={"host": "127.0.0.1", "port": proxy_port},
        daemon=True,
    )
    t.start()
    time.sleep(0.3)

    # Patch the handler's reference to is_allowed, since handler.py uses
    # `from access_control.acl import is_allowed` creating a local binding.
    import proxy.handler as handler_mod

    orig_is_allowed = handler_mod.is_allowed

    def blocking_is_allowed(host, client_ip=None):
        if "blocked" in host:
            return False
        return orig_is_allowed(host, client_ip)

    handler_mod.is_allowed = blocking_is_allowed

    try:
        client = socket.socket()
        client.connect(("127.0.0.1", proxy_port))
        req = "CONNECT blocked.com:443 HTTP/1.1\r\nHost: blocked.com:443\r\n\r\n"
        client.sendall(req.encode())

        response = client.recv(4096).decode()
        assert "403" in response, f"Expected 403 Forbidden, got: {response}"
        client.close()
    finally:
        handler_mod.is_allowed = orig_is_allowed
        acl_mod.set_mode(orig_mode)
