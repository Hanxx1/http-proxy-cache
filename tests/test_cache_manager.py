import pytest

from cache.cache_manager import CacheManager


def test_cache_miss_before_set():
    cache = CacheManager()

    assert cache.is_hit("http://example.com/") is False


def test_cache_hit_after_set():
    cache = CacheManager()
    url = "http://example.com/"

    cache.set(url, b"hello")

    assert cache.is_hit(url) is True


def test_cache_get_returns_bytes():
    cache = CacheManager()
    url = "http://example.com/"
    data = b"HTTP/1.1 200 OK\r\n\r\nhello"

    cache.set(url, data)

    assert cache.get(url) == data


def test_cache_set_overwrites_old_data():
    cache = CacheManager()
    url = "http://example.com/"

    cache.set(url, b"old")
    cache.set(url, b"new")

    assert cache.get(url) == b"new"


def test_cache_rejects_non_bytes():
    cache = CacheManager()

    with pytest.raises(TypeError):
        cache.set("http://example.com/", "not bytes")
