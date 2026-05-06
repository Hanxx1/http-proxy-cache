# B模块（缓存管理）交付说明

本文档用于说明 B 同学负责的 Cache 模块如何使用、如何测试，以及后续如何与 A/C/D 模块集成。

## 1. 模块定位

B 模块在项目中的角色是“仓库管理员”，负责把已经从外网获取到的响应数据保存下来。当后续再次访问同一个 URL 时，可以直接从缓存中取出数据，减少重复访问外网的次数。

当前实现文件：

- `cache/cache_manager.py`
- `tests/test_cache_manager.py`

## 2. 已实现接口

根据作业要求，已经实现 `CacheManager` 类，并提供以下三个方法：

```python
class CacheManager:
    def is_hit(self, url: str) -> bool:
        ...

    def get(self, url: str) -> bytes:
        ...

    def set(self, url: str, data: bytes) -> None:
        ...
```

### 方法说明

- `is_hit(url: str) -> bool`
  - 判断指定 URL 是否已经存在于缓存中。
  - 已缓存返回 `True`，未缓存返回 `False`。

- `get(url: str) -> bytes`
  - 根据 URL 读取缓存内容。
  - 返回值类型为 `bytes`，用于保存完整 HTTP 响应数据。

- `set(url: str, data: bytes) -> None`
  - 将指定 URL 和响应数据写入缓存。
  - 如果同一个 URL 已存在，会用新数据覆盖旧数据。
  - 如果传入的数据不是 `bytes`，会抛出 `TypeError`。

## 3. 实现思路

当前版本采用内存缓存，内部使用字典保存数据：

```python
{
    url: response_bytes
}
```

其中：

- key 是请求的 URL。
- value 是对应的响应数据，类型为 `bytes`。

因为代理服务器会为多个客户端请求开启多个线程，所以 Cache 模块内部使用了 `threading.Lock`，保证多个线程同时读写缓存时不会出现数据混乱。

## 4. 使用示例

A 同学的代理处理模块可以这样使用 B 模块：

```python
from cache.cache_manager import CacheManager

cache = CacheManager()

url = "http://example.com/"

if cache.is_hit(url):
    response_data = cache.get(url)
    hit = True
else:
    response_data = fetch_from_remote_server(url)
    cache.set(url, response_data)
    hit = False
```

其中 `fetch_from_remote_server(url)` 表示 A 同学负责实现的外网请求逻辑。

## 5. 与其他模块的集成方式

### 与 A 模块（代理转发）的关系

A 模块负责真正向外网请求数据。建议处理流程如下：

1. 客户端请求进入代理服务器。
2. A 模块解析出 URL。
3. A 模块先调用 `cache.is_hit(url)`。
4. 如果命中缓存，直接调用 `cache.get(url)` 并返回给客户端。
5. 如果未命中缓存，A 模块访问外网获取响应。
6. 外网响应成功后，调用 `cache.set(url, response_data)` 保存。
7. 最后把响应返回给客户端。

### 与 C 模块（日志）的关系

C 模块需要记录当前请求是否命中缓存。B 模块可以为 C 模块提供 `hit` 值：

```python
log_request(addr, method, url, status, hit)
```

例如：

- 缓存命中：`hit=True`
- 缓存未命中：`hit=False`

### 与 D 模块（访问控制）的关系

D 模块负责判断网站是否允许访问。建议先执行 D 模块检查：

1. 如果 D 模块拒绝访问，直接返回 `403`，不需要读取或写入缓存。
2. 如果 D 模块允许访问，再进入 B 模块缓存判断。

## 6. 测试说明

已补充 B 模块单元测试：

```text
tests/test_cache_manager.py
```

测试覆盖内容：

- 未写入缓存前，`is_hit()` 返回 `False`。
- 写入缓存后，`is_hit()` 返回 `True`。
- `get()` 可以正确返回 `bytes` 数据。
- 同一个 URL 再次写入时可以覆盖旧数据。
- `set()` 拒绝非 `bytes` 类型数据。

运行 B 模块测试：

```bash
python -m pytest tests/test_cache_manager.py -q
```

运行全部测试：

```bash
python -m pytest -q
```

## 7. 手动测试示例

也可以在 Python 交互环境中手动测试：

```python
from cache.cache_manager import CacheManager

cache = CacheManager()
url = "http://example.com/"

print(cache.is_hit(url))
cache.set(url, b"hello")
print(cache.is_hit(url))
print(cache.get(url))
```

预期输出：

```text
False
True
b'hello'
```

## 8. 当前版本说明

当前 B 模块是基础版内存缓存，已经满足作业中要求的三个核心接口。

当前版本特点：

- 实现简单，便于和 A 模块集成。
- 使用 `bytes` 保存响应，适合 HTTP 响应数据。
- 支持多线程环境下安全读写。

当前版本限制：

- 程序关闭后缓存会消失。
- 暂未实现缓存过期时间。
- 暂未实现缓存大小限制。
- 暂未实现磁盘持久化缓存。

如果后续老师或组长要求扩展，可以继续增加缓存过期、最大容量、文件缓存等功能。

## 9. 交付清单

B 模块最终交付内容：

- 已实现 `cache/cache_manager.py`
- 已实现 `CacheManager` 类
- 已实现 `is_hit(url: str) -> bool`
- 已实现 `get(url: str) -> bytes`
- 已实现 `set(url: str, data: bytes) -> None`
- 已补充 `tests/test_cache_manager.py`
- 可通过 pytest 进行功能验证

**交付负责人**：B 同学（仓库管理员）

**日期**：2026-05-06
