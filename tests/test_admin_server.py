import admin.server as admin_server
import logger.logger as logger_mod
import stats as stats_mod
from admin.server import clear_cache_entries, clear_logs, get_cache_snapshot, get_summary
from cache.cache_manager import CacheManager
from logger.logger import log_request
from proxy.handler import ProxyHandler


def test_admin_summary_reads_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(logger_mod, "_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(stats_mod, "_LOG_FILES", [])

    log_request(("127.0.0.1", 1), "GET", "http://a.test/", 200, True)
    log_request(("127.0.0.1", 2), "GET", "http://b.test/", 200, False)
    log_request(("127.0.0.1", 3), "GET", "http://a.test/", 200, False)

    summary = get_summary()

    assert summary["total"] == 3
    assert summary["hits"] == 1
    assert summary["misses"] == 2
    assert summary["hit_rate"] == 33.33
    assert summary["top_urls"][0] == {"url": "http://a.test/", "count": 2}


def test_admin_cache_snapshot_and_clear(monkeypatch):
    cache = CacheManager(ttl_seconds=60, max_items=3)
    monkeypatch.setattr(ProxyHandler, "_cache", cache)

    cache.set("http://cache.test/", b"HTTP/1.1 200 OK\r\n\r\nhello")
    snapshot = get_cache_snapshot()

    assert snapshot["size"] == 1
    assert snapshot["max_items"] == 3
    assert snapshot["ttl_seconds"] == 60
    assert snapshot["entries"][0]["url"] == "http://cache.test/"

    result = clear_cache_entries()

    assert result["ok"] is True
    assert result["cleared"] == 1
    assert result["cache"]["size"] == 0
    assert cache.snapshot()["entries"] == []


def test_admin_clear_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(logger_mod, "_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(stats_mod, "_LOG_FILES", [])
    monkeypatch.setattr(admin_server, "BASE_DIR", tmp_path)

    log_request(("127.0.0.1", 1), "GET", "http://log.test/", 200, True)
    assert any(tmp_path.glob("*.log"))

    result = clear_logs()

    assert result["ok"] is True
    assert result["deleted"] == 1
    assert result["summary"]["total"] == 0
    assert result["logs"] == []
    assert not any(tmp_path.glob("*.log"))
