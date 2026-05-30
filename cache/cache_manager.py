import threading
import time
from datetime import datetime
from config import CACHE_TTL_SECONDS, CACHE_MAX_ITEMS


class CacheManager:
    """Thread-safe in-memory cache with TTL and stats."""

    def __init__(self, ttl_seconds=None, max_items=None):
        self._cache = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._ttl = ttl_seconds if ttl_seconds is not None else CACHE_TTL_SECONDS
        self._max = max_items if max_items is not None else CACHE_MAX_ITEMS
        self._insert_order = []

    def is_hit(self, url: str) -> bool:
        with self._lock:
            entry = self._cache.get(url)
            if entry is None:
                self._misses += 1
                return False
            if self._is_expired(entry):
                self._evict(url)
                self._misses += 1
                return False
            return True

    def get(self, url: str) -> bytes:
        with self._lock:
            entry = self._cache.get(url)
            if entry is None:
                raise KeyError(url)
            if self._is_expired(entry):
                self._evict(url)
                raise KeyError(url)
            entry["hit_count"] += 1
            self._hits += 1
            return entry["data"]

    def set(self, url: str, data: bytes) -> None:
        if not isinstance(data, bytes):
            raise TypeError("cache data must be bytes")
        with self._lock:
            now = time.time()
            if url in self._cache:
                self._cache[url]["data"] = data
                self._cache[url]["created_at"] = now
                self._cache[url]["expires_at"] = now + self._ttl
                return
            if len(self._cache) >= self._max:
                self._evict_one()
            self._cache[url] = {
                "data": data,
                "created_at": now,
                "expires_at": now + self._ttl,
                "hit_count": 0,
            }
            self._insert_order.append(url)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._insert_order.clear()

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "size": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "max_items": self._max,
                "ttl_seconds": self._ttl,
            }

    def snapshot(self) -> dict:
        with self._lock:
            entries = []
            for url, entry in self._cache.items():
                if self._is_expired(entry):
                    continue
                entries.append({
                    "url": url,
                    "size": len(entry["data"]),
                    "created_at": datetime.fromtimestamp(entry["created_at"]).strftime("%Y-%m-%d %H:%M:%S"),
                    "expires_at": datetime.fromtimestamp(entry["expires_at"]).strftime("%Y-%m-%d %H:%M:%S"),
                    "hit_count": entry["hit_count"],
                })
            return {
                "size": len(entries),
                "hits": self._hits,
                "misses": self._misses,
                "entries": entries,
            }

    def _is_expired(self, entry: dict) -> bool:
        return time.time() > entry["expires_at"]

    def _evict(self, url: str) -> None:
        self._cache.pop(url, None)
        if url in self._insert_order:
            self._insert_order.remove(url)

    def _evict_one(self) -> None:
        if self._insert_order:
            oldest = self._insert_order.pop(0)
            self._cache.pop(oldest, None)
