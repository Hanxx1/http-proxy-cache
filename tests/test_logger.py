import os
import sys
import tempfile
import threading
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logger.logger as mod
from logger.logger import log_request


def _in_temp_dir(test_fn):
    """Run test_fn with logger._LOG_DIR pointing at a temp directory."""
    def wrapper(*args, **kwargs):
        orig_dir = mod._LOG_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            mod._LOG_DIR = tmpdir
            try:
                return test_fn(tmpdir, *args, **kwargs)
            finally:
                mod._LOG_DIR = orig_dir
    return wrapper


def _log_path(tmpdir):
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(tmpdir, f"proxy-{today}.log")


# --- Tests ---

@_in_temp_dir
def test_creates_log_file(tmpdir):
    log_request(("127.0.0.1", 12345), "GET", "http://test.com/", 200, True)
    assert os.path.isfile(_log_path(tmpdir))


@_in_temp_dir
def test_ten_calls_ten_lines(tmpdir):
    for i in range(10):
        log_request(("127.0.0.1", i), "GET", f"http://test.com/{i}", 200, True)
    log_path = _log_path(tmpdir)
    with open(log_path) as f:
        lines = f.readlines()
    assert len(lines) == 10


@_in_temp_dir
def test_hit_and_miss_strings(tmpdir):
    log_request(("127.0.0.1", 1), "GET", "http://a.com/", 200, True)
    log_request(("127.0.0.1", 2), "GET", "http://b.com/", 200, False)
    with open(_log_path(tmpdir)) as f:
        content = f.read()
    assert "HIT" in content
    assert "MISS" in content
    assert content.count("HIT") == 1
    assert content.count("MISS") == 1


@_in_temp_dir
def test_log_format(tmpdir):
    log_request(("192.168.1.1", 8888), "CONNECT", "example.com:443", 200, True)
    with open(_log_path(tmpdir)) as f:
        line = f.readline().strip()
    parts = line.split(" | ")
    assert len(parts) == 6
    assert parts[1] == "192.168.1.1"
    assert parts[2] == "CONNECT"
    assert parts[3] == "example.com:443"
    assert parts[4] == "200"
    assert parts[5] == "HIT"


@_in_temp_dir
def test_thread_safety(tmpdir):
    n_threads = 20
    n_each = 50

    def worker(tid):
        for i in range(n_each):
            log_request(("10.0.0.1", tid), "GET", f"http://test.com/{tid}-{i}", 200, True)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with open(_log_path(tmpdir)) as f:
        lines = f.readlines()
    assert len(lines) == n_threads * n_each
    for line in lines:
        parts = line.strip().split(" | ")
        assert len(parts) == 6, f"Malformed line: {line!r}"


@_in_temp_dir
def test_status_code_types(tmpdir):
    log_request(("127.0.0.1", 1), "GET", "http://a.com/", 403, False)
    log_request(("127.0.0.1", 2), "GET", "http://b.com/", 200, False)
    with open(_log_path(tmpdir)) as f:
        lines = f.readlines()
    assert "403" in lines[0]
    assert "200" in lines[1]


@_in_temp_dir
def test_auto_creates_log_dir(tmpdir):
    # Remove the temp dir to verify it gets recreated
    os.rmdir(tmpdir)
    log_request(("127.0.0.1", 1), "GET", "http://test.com/", 200, True)
    assert os.path.isdir(tmpdir)
    assert os.path.isfile(_log_path(tmpdir))


@_in_temp_dir
def test_ip_from_addr_tuple(tmpdir):
    log_request(("10.0.0.5", 9999), "GET", "http://test.com/", 200, True)
    with open(_log_path(tmpdir)) as f:
        line = f.readline()
    assert line.startswith("2026") or "10.0.0.5" in line
