import select
import socket
from urllib.parse import urlsplit

from access_control.acl import is_allowed
from cache.cache_manager import CacheManager
from logger.logger import log_request


class ProxyHandler:
    """HTTP/HTTPS proxy request handler."""

    _cache = CacheManager()
    _buffer_size = 65536
    _custom_header_key = "X-Proxy-Server"
    _custom_header_value = "http-proxy-cache"
    _drop_headers = {
        "proxy-connection",
        "connection",
        "keep-alive",
        "transfer-encoding",
        "te",
        "trailer",
        "upgrade",
        "x-forwarded-for",
    }

    @staticmethod
    def _recv_request(client_socket):
        data = b""
        while b"\r\n\r\n" not in data and len(data) < ProxyHandler._buffer_size:
            chunk = client_socket.recv(4096)
            if not chunk:
                break
            data += chunk
        return data

    @staticmethod
    def _parse_request(request_data):
        head, _, body = request_data.partition(b"\r\n\r\n")
        head_lines = head.decode("iso-8859-1", errors="ignore").split("\r\n")
        if not head_lines or len(head_lines[0].split()) < 3:
            raise ValueError("invalid request line")

        method, target, version = head_lines[0].split()[:3]
        headers = {}
        for line in head_lines[1:]:
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()
        return method, target, version, headers, body

    @staticmethod
    def _extract_target(method, target, headers):
        if method.upper() == "CONNECT":
            host, _, port_s = target.partition(":")
            port = int(port_s) if port_s.isdigit() else 443
            return host, port, target, ""

        parsed = urlsplit(target)
        if parsed.scheme in ("http", "https") and parsed.hostname:
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            path = parsed.path or "/"
            if parsed.query:
                path = f"{path}?{parsed.query}"
            full_url = target
            return host, port, full_url, path

        host_header = headers.get("Host", "")
        host_only = host_header.split(":")[0].strip()
        port = 80
        if ":" in host_header:
            port_raw = host_header.rsplit(":", 1)[-1]
            if port_raw.isdigit():
                port = int(port_raw)
        path = target if target.startswith("/") else f"/{target}"
        full_url = f"http://{host_header}{path}" if host_header else path
        return host_only, port, full_url, path

    @staticmethod
    def _rewrite_headers(headers, host, port):
        rewritten = {}
        for key, value in headers.items():
            if key.lower() in ProxyHandler._drop_headers:
                continue
            rewritten[key] = value

        if "Host" not in rewritten:
            rewritten["Host"] = f"{host}:{port}" if port not in (80, 443) else host

        rewritten[ProxyHandler._custom_header_key] = ProxyHandler._custom_header_value
        rewritten["Connection"] = "close"
        return rewritten

    @staticmethod
    def _build_request_bytes(method, path, version, headers, body):
        lines = [f"{method} {path} {version}"]
        for key, value in headers.items():
            lines.append(f"{key}: {value}")
        lines.append("")
        lines.append("")
        head_bytes = "\r\n".join(lines).encode("iso-8859-1", errors="ignore")
        return head_bytes + body

    @staticmethod
    def _read_full_response(remote_socket):
        chunks = []
        while True:
            data = remote_socket.recv(4096)
            if not data:
                break
            chunks.append(data)
        return b"".join(chunks)

    @staticmethod
    def _parse_status_code(response_data):
        first = response_data.split(b"\r\n", 1)[0].decode("iso-8859-1", errors="ignore")
        parts = first.split()
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1])
        return 502

    @staticmethod
    def _send_403(client_socket):
        response = (
            "HTTP/1.1 403 Forbidden\r\n"
            "Content-Type: text/html\r\n"
            "Connection: close\r\n"
            "\r\n"
            "<html><body><h1>403 Forbidden</h1><p>Access Denied by Proxy ACL.</p></body></html>"
        ).encode("utf-8")
        client_socket.sendall(response)

    @staticmethod
    def _tunnel(client_socket, remote_socket):
        sockets = [client_socket, remote_socket]
        while True:
            readable, _, _ = select.select(sockets, [], [], 30)
            if not readable:
                continue
            for sock in readable:
                data = sock.recv(4096)
                if not data:
                    return
                if sock is client_socket:
                    remote_socket.sendall(data)
                else:
                    client_socket.sendall(data)

    @staticmethod
    def _handle_connect(client_socket, addr, host, port, url):
        if not is_allowed(host, addr[0]):
            ProxyHandler._send_403(client_socket)
            log_request(addr, "CONNECT", url, 403, False)
            return

        try:
            with socket.create_connection((host, port), timeout=10) as remote_socket:
                client_socket.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                log_request(addr, "CONNECT", url, 200, False)
                ProxyHandler._tunnel(client_socket, remote_socket)
        except Exception:
            client_socket.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            log_request(addr, "CONNECT", url, 502, False)

    @staticmethod
    def _handle_http(client_socket, addr, method, host, port, url, path, version, headers, body):
        if not is_allowed(host, addr[0]):
            ProxyHandler._send_403(client_socket)
            log_request(addr, method, url, 403, False)
            return

        method_upper = method.upper()
        if method_upper == "GET" and ProxyHandler._cache.is_hit(url):
            cached = ProxyHandler._cache.get(url)
            client_socket.sendall(cached)
            status = ProxyHandler._parse_status_code(cached)
            log_request(addr, method_upper, url, status, True)
            return

        rewritten_headers = ProxyHandler._rewrite_headers(headers, host, port)
        outbound = ProxyHandler._build_request_bytes(method_upper, path, version, rewritten_headers, body)

        try:
            with socket.create_connection((host, port), timeout=10) as remote_socket:
                remote_socket.sendall(outbound)
                response = ProxyHandler._read_full_response(remote_socket)
        except Exception:
            client_socket.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            log_request(addr, method_upper, url, 502, False)
            return

        if not response:
            client_socket.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            log_request(addr, method_upper, url, 502, False)
            return

        status = ProxyHandler._parse_status_code(response)
        if method_upper == "GET" and status == 200:
            ProxyHandler._cache.set(url, response)
        client_socket.sendall(response)
        log_request(addr, method_upper, url, status, False)

    @staticmethod
    def handle(client_socket, addr):
        """处理客户端请求入口。"""
        try:
            request_data = ProxyHandler._recv_request(client_socket)
            if not request_data:
                return

            method, target, version, headers, body = ProxyHandler._parse_request(request_data)
            host, port, url, path = ProxyHandler._extract_target(method, target, headers)
            if not host:
                client_socket.sendall(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
                return

            if method.upper() == "CONNECT":
                ProxyHandler._handle_connect(client_socket, addr, host, port, url)
            else:
                ProxyHandler._handle_http(
                    client_socket, addr, method, host, port, url, path, version, headers, body
                )
        except Exception as e:
            print(f"[!] Handler Error: {e}")
            try:
                client_socket.sendall(b"HTTP/1.1 500 Internal Server Error\r\nConnection: close\r\n\r\n")
            except Exception:
                pass
        finally:
            client_socket.close()
