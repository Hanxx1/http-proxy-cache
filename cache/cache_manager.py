import threading


class CacheManager:
    """Simple thread-safe in-memory cache for proxy responses."""

    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()

    def is_hit(self, url: str) -> bool:
        with self._lock:
            return url in self._cache

    def get(self, url: str) -> bytes:
        with self._lock:
            return self._cache[url]

    def set(self, url: str, data: bytes) -> None:
        if not isinstance(data, bytes):
            raise TypeError("cache data must be bytes")

        with self._lock:
            self._cache[url] = data
