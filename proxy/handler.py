import select
import socket
from urllib.parse import urlsplit

from access_control.acl import get_block_reason, is_allowed
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

        if b"\r\n\r\n" not in data:
            return data

        head, _, body_so_far = data.partition(b"\r\n\r\n")

        # Parse Content-Length from headers to read remaining body
        content_length = 0
        head_text = head.decode("iso-8859-1", errors="ignore")
        for line in head_text.split("\r\n")[1:]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            if key.strip().lower() == "content-length" and value.strip().isdigit():
                content_length = int(value.strip())
                break

        remaining = content_length - len(body_so_far)
        while remaining > 0:
            chunk = client_socket.recv(min(4096, remaining))
            if not chunk:
                break
            body_so_far += chunk
            remaining -= len(chunk)

        return head + b"\r\n\r\n" + body_so_far

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
    def _read_response(remote_socket):
        """Read HTTP response from remote server, handling Content-Length and chunked encoding."""
        remote_socket.settimeout(15)

        data = b""
        while b"\r\n\r\n" not in data and len(data) < ProxyHandler._buffer_size:
            chunk = remote_socket.recv(4096)
            if not chunk:
                break
            data += chunk

        if b"\r\n\r\n" not in data:
            return data

        head, _, body_so_far = data.partition(b"\r\n\r\n")

        content_length = 0
        chunked = False
        head_text = head.decode("iso-8859-1", errors="ignore")
        for line in head_text.split("\r\n")[1:]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            k = key.strip().lower()
            if k == "content-length" and value.strip().isdigit():
                content_length = int(value.strip())
            if k == "transfer-encoding" and "chunked" in value.strip().lower():
                chunked = True

        # Parse chunked transfer encoding
        if chunked:
            buf = body_so_far
            while True:
                try:
                    chunk = remote_socket.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                except socket.timeout:
                    break
                # Check if we have the terminating chunk: 0\r\n\r\n
                if b"0\r\n\r\n" in buf or buf.endswith(b"0\r\n\r\n"):
                    break
                # Also check for 0\r\n at the end of a line
                head_part = buf.split(b"\r\n")
                if len(head_part) >= 2 and head_part[-2].strip() == b"0":
                    if buf.endswith(b"\r\n"):
                        break
            return head + b"\r\n\r\n" + buf

        if content_length > 0:
            remaining = content_length - len(body_so_far)
            while remaining > 0:
                try:
                    chunk = remote_socket.recv(min(4096, remaining))
                    if not chunk:
                        break
                    body_so_far += chunk
                    remaining -= len(chunk)
                except socket.timeout:
                    break
            return head + b"\r\n\r\n" + body_so_far

        # Fallback: read until close (with timeout)
        chunks = [body_so_far]
        while True:
            try:
                chunk = remote_socket.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
            except socket.timeout:
                break
        return head + b"\r\n\r\n" + b"".join(chunks)

    @staticmethod
    def _parse_status_code(response_data):
        first = response_data.split(b"\r\n", 1)[0].decode("iso-8859-1", errors="ignore")
        parts = first.split()
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1])
        return 502

    @staticmethod
    def _send_blocked(client_socket, host, reason):
        body = (
            '<!doctype html><html lang="en"><head>'
            '<meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>403 — Access Denied</title>'
            '<style>'
            ':root{--bg:#f5f5f5;--card:#fff;--text:#333;--muted:#666;--red:#c0392b;--line:#e0e0e0}'
            '*{box-sizing:border-box;margin:0}'
            'body{display:flex;align-items:center;justify-content:center;min-height:100vh;'
            'font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text)}'
            '.card{max-width:540px;width:90%;padding:40px 36px;border-radius:12px;'
            'background:var(--card);box-shadow:0 2px 12px rgba(0,0,0,.08);text-align:center}'
            '.icon{width:64px;height:64px;margin:0 auto 20px;border-radius:50%;'
            'background:#fde8e8;display:flex;align-items:center;justify-content:center;font-size:32px}'
            'h1{font-size:22px;font-weight:700;margin-bottom:8px;color:var(--red)}'
            'p{color:var(--muted);line-height:1.6;margin:6px 0}'
            '.row{display:flex;justify-content:space-between;padding:8px 0;'
            'border-bottom:1px solid var(--line);font-size:13px}'
            '.row span:first-child{color:var(--muted)}'
            '.row span:last-child{font-weight:600}'
            '.info{margin:20px 0;background:#fafafa;border-radius:8px;padding:14px 16px}'
            '.foot{margin-top:18px;font-size:12px;color:var(--muted)}'
            '</style></head><body><div class="card">'
            f'<div class="icon">⛔</div>'
            f'<h1>Access Denied</h1>'
            f'<p>This request was blocked by the proxy access control policy.</p>'
            f'<div class="info">'
            f'<div class="row"><span>Blocked Host</span><span>{host}</span></div>'
            f'<div class="row"><span>Reason</span><span>{reason}</span></div>'
            f'<div class="row"><span>Status</span><span>403 Forbidden</span></div>'
            f'</div>'
            f'<p class="foot">HTTP Proxy Cache &mdash; Access Control</p>'
            '</div></body></html>'
        ).encode("utf-8")
        response = (
            "HTTP/1.1 403 Forbidden\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("utf-8") + body
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
            ProxyHandler._send_blocked(client_socket, host, get_block_reason(host, addr[0]))
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
            ProxyHandler._send_blocked(client_socket, host, get_block_reason(host, addr[0]))
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
                response = ProxyHandler._read_response(remote_socket)
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
                log_request(addr, method, url, 400, False)
                return

            if method.upper() == "CONNECT":
                ProxyHandler._handle_connect(client_socket, addr, host, port, url)
            else:
                ProxyHandler._handle_http(
                    client_socket, addr, method, host, port, url, path, version, headers, body
                )
        except Exception as e:
            print(f"[!] Handler Error: {e}")
            log_request(addr, "UNKNOWN", "unknown", 500, False)
            try:
                client_socket.sendall(b"HTTP/1.1 500 Internal Server Error\r\nConnection: close\r\n\r\n")
            except Exception:
                pass
        finally:
            client_socket.close()
