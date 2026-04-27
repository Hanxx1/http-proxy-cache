import os
import threading
from datetime import datetime

_log_lock = threading.Lock()
_LOG_DIR = "logs"


def _get_log_path():
    date_str = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(_LOG_DIR, f"proxy-{date_str}.log")


def log_request(addr, method, url, status, hit):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ip = addr[0]
    status_str = str(status)
    hit_str = "HIT" if hit else "MISS"
    line = f"{timestamp} | {ip} | {method} | {url} | {status_str} | {hit_str}\n"

    with _log_lock:
        log_path = _get_log_path()
        os.makedirs(_LOG_DIR, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
