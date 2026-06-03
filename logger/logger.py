"""日志模块 —— 按日期滚动的线程安全日志系统。

课内知识点：
- 文件 I/O: open/read/write（操作系统文件系统章节）
- 线程安全: threading.Lock() 保护写操作（并发编程）
- 日志轮转: 按日期创建不同文件，避免单文件过大
- 延迟初始化: _LOG_DIR 在首次使用时才从 config 读取，便于测试 mock

日志格式（空格分隔，便于 grep/awk 分析）:
    YYYY-MM-DD HH:MM:SS | 客户端IP | 方法 | URL | 状态码 | HIT/MISS
"""

import os
import threading
from datetime import datetime

_log_lock = threading.Lock()
_LOG_DIR = None


def _init_log_dir():
    global _LOG_DIR
    if _LOG_DIR is None:
        from config import LOG_DIR
        _LOG_DIR = LOG_DIR


def get_log_dir():
    """Return the log directory path."""
    _init_log_dir()
    return _LOG_DIR


def get_today_log_path():
    """Return today's log file path."""
    _init_log_dir()
    date_str = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(_LOG_DIR, f"proxy-{date_str}.log")


def get_latest_logs(limit=100):
    """Return the most recent log entries as a list of dicts."""
    _init_log_dir()
    entries = []
    log_dir = _LOG_DIR
    if not os.path.isdir(log_dir):
        return entries

    for fname in sorted(os.listdir(log_dir)):
        path = os.path.join(log_dir, fname)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(" | ")
                if len(parts) != 6:
                    continue
                entries.append({
                    "time": parts[0],
                    "ip": parts[1],
                    "method": parts[2],
                    "url": parts[3],
                    "status": int(parts[4]) if parts[4].isdigit() else parts[4],
                    "cache": parts[5],
                })

    return entries[-limit:]


def log_request(addr, method, url, status, cache_status=None):
    if cache_status is None:
        cache_status = False
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ip = addr[0]
    status_str = str(status)
    hit_str = "HIT" if cache_status else "MISS"
    line = f"{timestamp} | {ip} | {method} | {url} | {status_str} | {hit_str}\n"

    with _log_lock:
        _init_log_dir()
        log_path = get_today_log_path()
        os.makedirs(_LOG_DIR, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
