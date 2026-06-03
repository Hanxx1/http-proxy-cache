import re
import select
import socket
from urllib.parse import urlsplit, urlunsplit

from access_control.acl import get_block_reason, is_allowed
from cache.cache_manager import CacheManager
from logger.logger import log_request


class ProxyHandler:
    """HTTP/HTTPS 前向代理请求处理器。

    课内知识点：
    - HTTP 协议 (RFC 7230-7235): 请求/响应格式、状态码、头部处理
    - TCP socket 编程: connect/send/recv/settimeout
    - I/O 多路复用: select.select 用于 CONNECT 隧道双向转发
    - 前向代理架构: 客户端 → 代理 → 目标服务器
    """

    _cache = CacheManager()
    _buffer_size = 65536                     # 64KB 缓冲区上限
    _connect_timeout = 8                     # TCP 三次握手超时（秒）
    _read_timeout = 10                       # 响应读取超时（秒）
    _client_timeout = 30                     # 客户端发送请求超时（秒）
    _custom_header_key = "X-Proxy-Server"
    _custom_header_value = "http-proxy-cache"

    # 逐跳头（hop-by-hop headers）：仅对当前连接有效，代理必须删除
    # 端到端头（end-to-end headers）则透传 —— 参见 RFC 7230 §6.1
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
        """从客户端 socket 读取完整 HTTP 请求。

        HTTP 请求格式（RFC 7230）:
            GET http://host/path HTTP/1.1\r\n   ← 请求行
            Host: host\r\n                       ← 头部（key: value）
            Content-Length: 13\r\n               ← 指示 Body 字节数
            \r\n                                  ← 空行分隔头部和 Body
            key=value&foo=bar                    ← Body（仅 POST/PUT 等有）
        """
        data = b""
        # 首先读取到 \r\n\r\n（空行），标记头部结束
        while b"\r\n\r\n" not in data and len(data) < ProxyHandler._buffer_size:
            chunk = client_socket.recv(4096)
            if not chunk:
                break
            data += chunk

        if b"\r\n\r\n" not in data:
            return data

        head, _, body_so_far = data.partition(b"\r\n\r\n")

        # 根据 Content-Length 头部读取剩余 Body 字节
        # 没有 Content-Length 的 GET 请求 Body 为空
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
        """从远端服务器读取完整 HTTP 响应。

        HTTP 响应体长度确定方式（RFC 7230 §3.3.3）:
        1. Content-Length  → 读取指定字节数
        2. Transfer-Encoding: chunked → 逐块读取直到零长度终止块
        3. 无长度 → 读取直到服务器关闭连接（HTTP/1.0 风格）
        对前向代理，响应原样转发给客户端（保留原始编码格式）。
        """
        remote_socket.settimeout(ProxyHandler._read_timeout)

        data = b""
        while b"\r\n\r\n" not in data and len(data) < ProxyHandler._buffer_size:
            try:
                chunk = remote_socket.recv(4096)
            except socket.timeout:
                break
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

        # Parse chunked transfer encoding: read until zero-length chunk
        # Matches \r\n0, \r\n00, \r\n0;ext=val\r\n (with optional chunk extension)
        _ZERO_CHUNK = re.compile(br'\r\n0+(?:;[^\r\n]*)?\r\n')
        if chunked:
            buf = body_so_far
            while True:
                m = _ZERO_CHUNK.search(buf)
                if m:
                    after = buf[m.end():]
                    if b"\r\n\r\n" in after or after in (b"", b"\r\n"):
                        break
                try:
                    chunk = remote_socket.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                except socket.timeout:
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
    def _normalize_url(url: str) -> str:
        """Normalize URL for cache-key consistency.

        - Lowercase scheme + hostname
        - Strip default ports (80, 443)
        - Ensure trailing / for empty path
        - Remove empty query string
        """
        parsed = urlsplit(url)
        scheme = (parsed.scheme or "").lower()
        hostname = (parsed.hostname or "").lower()
        port = parsed.port

        # Strip default ports
        if port is None:
            port_str = ""
        elif scheme == "http" and port == 80:
            port_str = ""
        elif scheme == "https" and port == 443:
            port_str = ""
        else:
            port_str = f":{port}"

        # Normalize path
        path = parsed.path or "/"

        # Normalize query
        query = parsed.query
        if query.endswith("?"):
            query = ""
        if query == "":
            query = ""

        netloc = f"{hostname}{port_str}" if hostname else parsed.netloc.lower()
        return urlunsplit((scheme, netloc, path, query, ""))

    @staticmethod
    def _cacheable_response(response_data: bytes) -> bool:
        """Check if response is cacheable based on its headers.

        Skips no-store, no-cache, and private cache-control directives.
        """
        try:
            head = response_data.split(b"\r\n\r\n", 1)[0]
            head_text = head.decode("iso-8859-1", errors="ignore")
            cache_control = ""
            for line in head_text.split("\r\n")[1:]:
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                k = key.strip().lower()
                if k == "cache-control":
                    cache_control = value.strip().lower()
                    break
            if not cache_control:
                return True  # No Cache-Control header → default to cacheable
            # Reject if no-store, no-cache, or private
            if "no-store" in cache_control:
                return False
            if "no-cache" in cache_control:
                return False
            if "private" in cache_control:
                return False
            return True
        except Exception:
            return True  # If we can't parse, default to cacheable

    @staticmethod
    def _connect_with_retry(host, port):
        """Attempt TCP connect with 1 retry on refused connections only."""
        for attempt in (0, 1):
            try:
                return socket.create_connection((host, port), timeout=ProxyHandler._connect_timeout)
            except ConnectionRefusedError:
                if attempt == 0:
                    continue
                raise

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
        """CONNECT 隧道双向数据转发。

        使用 select.select 实现 I/O 多路复用（操作系统课程知识点）：
        - 同时监听客户端和远端两个 socket
        - 任一 socket 有数据到达即转发到对端
        - 任一 socket 关闭则隧道结束
        30 秒超时防止空闲隧道永久占用线程资源。
        """
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
            with ProxyHandler._connect_with_retry(host, port) as remote_socket:
                client_socket.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                log_request(addr, "CONNECT", url, 200, False)
                ProxyHandler._tunnel(client_socket, remote_socket)
        except Exception:
            client_socket.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            log_request(addr, "CONNECT", url, 502, False)

    @staticmethod
    def _handle_http(client_socket, addr, method, host, port, url, path, version, headers, body):
        """HTTP 请求代理主流程。

        GET 请求的处理路径（体现缓存的价值）：
        1. ACL 检查 ──→ 不通过 → 403
        2. 缓存查询 ──→ 命中 → 直接返回缓存内容（零网络开销）
        3. 缓存未命中 → 连接目标服务器、转发请求、读取响应
        4. 响应满足条件 → 存入缓存供后续请求使用
        """
        if not is_allowed(host, addr[0]):
            ProxyHandler._send_blocked(client_socket, host, get_block_reason(host, addr[0]))
            log_request(addr, method, url, 403, False)
            return

        method_upper = method.upper()
        cache_key = ProxyHandler._normalize_url(url)

        if method_upper == "GET" and ProxyHandler._cache.is_hit(cache_key):
            cached = ProxyHandler._cache.get(cache_key)
            client_socket.sendall(cached)
            status = ProxyHandler._parse_status_code(cached)
            log_request(addr, method_upper, url, status, True)
            return

        rewritten_headers = ProxyHandler._rewrite_headers(headers, host, port)
        outbound = ProxyHandler._build_request_bytes(method_upper, path, version, rewritten_headers, body)

        try:
            with ProxyHandler._connect_with_retry(host, port) as remote_socket:
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
        if method_upper == "GET" and status == 200 and ProxyHandler._cacheable_response(response):
            ProxyHandler._cache.set(cache_key, response)
        client_socket.sendall(response)
        log_request(addr, method_upper, url, status, False)

    @staticmethod
    def handle(client_socket, addr):
        """处理客户端请求入口。"""
        client_socket.settimeout(ProxyHandler._client_timeout)
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
