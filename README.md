# HTTP 代理缓存服务器

Python 标准库实现，支持 HTTP/HTTPS 代理、缓存、访问控制、日志统计。

---

## 环境准备

```bash
conda activate http-proxy-cache
pip install -r requirements.txt
python -m pytest -q
```

## 启动代理

```bash
python main.py
```

看到 `[*] Proxy Server started on 127.0.0.1:8080` 即启动成功。

---

## 演示步骤

### 1. 配置 Edge 浏览器

Edge 地址栏输入 `edge://settings/system` → 打开代理设置 → 手动设置代理：
- 地址：`127.0.0.1`
- 端口：`8080`

> 或用 SwitchyOmega 插件一键切换。

### 2. HTTP 代理访问

Edge 访问 `http://httpbin.org/get`，页面正常加载即成功。

查看日志：

```bash
cat logs/proxy-$(date +%Y-%m-%d).log
```

日志输出：

```
2026-05-30 16:00:00 | 127.0.0.1 | GET | http://httpbin.org/get | 200 | MISS
```

### 3. 缓存 HIT/MISS

Edge 打开 `http://httpbin.org/headers`，然后 **按 F5 刷新一次**。

第一次：`MISS` → 第二次：`HIT`

查看统计：

```bash
python stats.py
```

输出：

```
HTTP Proxy Cache Statistics
===========================
Total Requests  : 12
Cache Hits      : 5
Cache Misses    : 7
Hit Rate        : 41.67%

Top 5 URLs
----------
1. http://httpbin.org/headers           3
2. http://httpbin.org/get               2
```

### 4. ACL 黑名单拦截

```bash
echo "httpbin.org" >> acl.txt
```

重启代理（Ctrl+C 停掉，再 `python main.py`）。

Edge 访问 `http://httpbin.org/headers` → **403 Forbidden**。

日志显示：

```
2026-05-30 16:05:00 | 127.0.0.1 | GET | http://httpbin.org/headers | 403 | MISS
```

演示完后把 `httpbin.org` 从 `acl.txt` 删掉，重启恢复正常。

> 子域名匹配：`baidu.com` 会拦截 `www.baidu.com` 和 `map.baidu.com`，但不拦 `fakebaidu.com`。
>
> 白名单模式：改 `config.py` 中 `ACL_MODE = "whitelist"`，只允许 `whitelist.txt` 中的域名。

### 5. HTTPS CONNECT 隧道

Edge 访问 `https://www.baidu.com`，正常加载 HTTPS 页面即成功。

日志显示：

```
2026-05-30 16:10:00 | 127.0.0.1 | CONNECT | www.baidu.com:443 | 200 | MISS
```

### 6. 并发浏览

Edge 同时打开多个标签页访问不同网站，所有请求独立记录、日志无错乱。

### 7. 请求头修改

代理自动添加 `X-Proxy-Server: http-proxy-cache`，过滤 `X-Forwarded-For` 等头。

访问 `http://httpbin.org/headers`，返回内容中可看到 `X-Proxy-Server`。

---

## 演示清单

| 演示项 | 操作 | 看什么 |
|--------|------|--------|
| HTTP 代理 | Edge 访问 HTTP 网站 | 页面正常加载 |
| 缓存命中 | 同一页面 F5 刷新两次 | MISS → HIT |
| ACL 拦截 | `echo xxx >> acl.txt` 后访问 | 返回 403 |
| HTTPS 隧道 | Edge 访问 HTTPS 网站 | 页面正常，日志有 CONNECT 200 |
| 并发 | 打开多个标签页 | 日志独立不交错 |
| 统计 | `python stats.py` | 请求数、命中率、热门 URL |
| 请求头修改 | 访问 httpbin.org/headers | 看到 X-Proxy-Server |

---

## 配置

编辑 `config.py`：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `PROXY_PORT` | `8080` | 监听端口 |
| `CACHE_TTL_SECONDS` | `60` | 缓存过期秒数 |
| `CACHE_MAX_ITEMS` | `128` | 最大缓存条目 |
| `ACL_MODE` | `blacklist` | `blacklist` / `whitelist` / `off` |

## 项目结构

```
├── main.py                  # 启动代理
├── config.py                # 配置
├── stats.py                 # 命令行统计
├── proxy/
│   ├── server.py            # TCP 监听 + 多线程
│   └── handler.py           # HTTP/HTTPS 处理
├── cache/
│   └── cache_manager.py     # 内存缓存（TTL）
├── access_control/
│   └── acl.py               # 黑白名单（子域名匹配）
├── logger/
│   └── logger.py            # 日志（按日期滚动）
├── tests/                   # 42 个测试
├── acl.txt                  # 域名黑名单
├── whitelist.txt            # 域名白名单
└── ip_blacklist.txt         # IP 黑名单
```
