import socket
import threading
from proxy.handler import ProxyHandler

def start_server(host='127.0.0.1', port=8080):
    """启动代理服务器"""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind((host, port))
        server_socket.listen(100)
        print(f"[*] Proxy Server started on {host}:{port}")
        
        while True:
            client_socket, addr = server_socket.accept()
            # 为每个请求启动一个新线程
            handler_thread = threading.Thread(
                target=ProxyHandler.handle, 
                args=(client_socket, addr)
            )
            handler_thread.daemon = True
            handler_thread.start()
            
    except Exception as e:
        print(f"[!] Error starting server: {e}")
    finally:
        server_socket.close()

if __name__ == "__main__":
    start_server()
