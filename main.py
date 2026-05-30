from config import PROXY_HOST, PROXY_PORT
from proxy.server import start_server

if __name__ == "__main__":
    start_server(host=PROXY_HOST, port=PROXY_PORT)
