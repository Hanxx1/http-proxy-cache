import threading

from admin.server import start_admin_server
from config import ADMIN_HOST, ADMIN_PORT, PROXY_HOST, PROXY_PORT
from proxy.server import start_server

if __name__ == "__main__":
    admin_thread = threading.Thread(
        target=start_admin_server,
        kwargs={"host": ADMIN_HOST, "port": ADMIN_PORT},
        daemon=True,
    )
    admin_thread.start()

    start_server(host=PROXY_HOST, port=PROXY_PORT)
