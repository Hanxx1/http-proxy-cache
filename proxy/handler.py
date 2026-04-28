import socket
from access_control.acl import is_allowed
from logger.logger import log_request

class ProxyHandler:
    @staticmethod
    def handle(client_socket, addr):
        """处理客户端请求的入口"""
        try:
            # 1. 接收请求数据 (简化处理，仅读取头部)
            request_data = client_socket.recv(4096)
            if not request_data:
                client_socket.close()
                return
            
            # 2. 简单解析 Host 和 Method (此处仅为演示 D 模块集成)
            # 实际 A 同学需要写更完整的 HTTP 解析
            header_lines = request_data.decode('utf-8', errors='ignore').split('\r\n')
            if not header_lines:
                client_socket.close()
                return
            
            first_line = header_lines[0].split()
            if len(first_line) < 3:
                client_socket.close()
                return
                
            method = first_line[0]
            url = first_line[1]
            
            # 尝试从 Header 中提取 Host
            host = ""
            for line in header_lines:
                if line.lower().startswith("host:"):
                    host = line.split(":")[1].strip()
                    break
            
            if not host:
                # 如果 Header 没 Host，尝试从 URL 解析 (针对 HTTP)
                if url.startswith("http://"):
                    host = url.split("//")[1].split("/")[0]
                else:
                    host = url.split("/")[0]

            # --- D 模块集成点 ---
            print(f"[*] Checking ACL for host: {host} from IP: {addr[0]}")
            if not is_allowed(host, addr[0]):
                print(f"[!] Blocked: {host}")
                # 构造 403 响应
                response = (
                    "HTTP/1.1 403 Forbidden\r\n"
                    "Content-Type: text/html\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                    "<html><body><h1>403 Forbidden</h1><p>Access Denied by Proxy ACL.</p></body></html>"
                ).encode("utf-8")
                client_socket.sendall(response)
                
                # 记录日志 (C 模块)
                log_request(addr, method, url, 403, False)
                
                client_socket.close()
                return
            # --------------------

            # TODO: A 同学和 B 同学后续需要在这里实现真正的转发和缓存逻辑
            print(f"[+] Allowed: {host}. (Waiting for Team Member A/B to finish proxy logic)")
            
            # 暂时给个提示，证明 ACL 通过了
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html\r\n"
                "\r\n"
                "<html><body><h1>Proxy Works!</h1><p>ACL passed. Waiting for A/B modules implementation.</p></body></html>"
            ).encode("utf-8")
            client_socket.sendall(response)
            
        except Exception as e:
            print(f"[!] Handler Error: {e}")
        finally:
            client_socket.close()
