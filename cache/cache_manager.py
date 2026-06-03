import threading
import time
from datetime import datetime
from config import CACHE_TTL_SECONDS, CACHE_MAX_ITEMS


class CacheManager:
    """线程安全的内存缓存，TTL 过期 + FIFO 淘汰策略。

    课内知识点：
    - 缓存淘汰算法: FIFO (First-In-First-Out)，最简单的页面置换算法
    - TTL (Time-To-Live): 基于时间的过期机制，类比 DNS 缓存的 TTL
    - 线程安全: threading.Lock() 临界区保护（操作系统并发章节）
    - 空间换时间: 用内存存储换取网络延迟的减少

    数据结构:
        _cache: dict[url → {data, created_at, expires_at, hit_count}]
        _insert_order: list[url] 维护插入顺序，用于 FIFO 淘汰
    """

    def __init__(self, ttl_seconds=None, max_items=None):
        self._cache = {}                          # URL → 缓存项映射
        self._lock = threading.Lock()             # 互斥锁，保护临界区
        self._hits = 0
        self._misses = 0
        self._ttl = ttl_seconds if ttl_seconds is not None else CACHE_TTL_SECONDS
        self._max = max_items if max_items is not None else CACHE_MAX_ITEMS
        self._insert_order = []                   # FIFO 队列：记录插入顺序

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
        """TTL 过期判断：当前时间超过过期时间即失效。

        使用 time.time()（Unix 时间戳）而非 time.monotonic()，
        以便 snapshot() 中 datetime.fromtimestamp() 可读展示。"""
        return time.time() > entry["expires_at"]

    def _evict(self, url: str) -> None:
        """移除单个缓存条目（过期淘汰）。"""
        self._cache.pop(url, None)
        if url in self._insert_order:
            self._insert_order.remove(url)

    def _evict_one(self) -> None:
        """FIFO 淘汰：移除最早插入的条目。

        类似操作系统页面置换中的 FIFO 算法：
        - 队列头部是最早进入的页面
        - 缓存满时弹出头部（Belady 异常可能发生，但实现简单）
        """
        if self._insert_order:
            oldest = self._insert_order.pop(0)
            self._cache.pop(oldest, None)
