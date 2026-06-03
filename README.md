# HTTP 代理缓存服务器

> 计算机网络课程实验 — Python 标准库实现的 HTTP/HTTPS 前向代理，支持内存缓存、访问控制、日志统计和 Web 管理面板。

---

## 目录

- [项目概览](#项目概览)
- [课内知识关联](#课内知识关联)
- [系统架构](#系统架构)
- [模块详解](#模块详解)
- [快速开始](#快速开始)
- [演示流程](#演示流程)
- [配置说明](#配置说明)
- [测试](#测试)
- [项目结构](#项目结构)

---

## 项目概览

这是一个基于 Python 标准库（无第三方依赖）开发的前向 HTTP 代理服务器，核心功能：

| 功能 | 说明 |
|------|------|
| **HTTP 代理** | 转发 GET/POST 等 HTTP 请求，重写请求头 |
| **HTTPS 隧道** | 通过 CONNECT 方法建立 TCP 隧道，透明转发加密流量 |
| **内容缓存** | 内存缓存，TTL 过期 + FIFO 淘汰，线程安全 |
| **访问控制** | 域名黑名单/白名单/IP 黑名单，支持子域名匹配 |
| **日志系统** | 按日期滚动日志，记录请求来源/IP/方法/URL/状态/缓存命中 |
| **统计面板** | Web 管理页（Chart.js 图表），实时查看命中率、缓存条目、请求日志 |
| **在线 ACL 编辑** | 管理页直接增删黑白名单，无需重启 |

---

## 课内知识关联

### 计算机网络

| 知识点 | 对应实现 | 代码位置 |
|--------|---------|---------|
| **HTTP 请求/响应格式** | 解析请求行、头部、Body；构造响应 | `proxy/handler.py:64-77, 122-130` |
| **HTTP 方法 (GET/POST/CONNECT)** | 分发 CONNECT 隧道 vs HTTP 转发 | `proxy/handler.py:418-423` |
| **HTTP 状态码** | 200/301/302/403/502/503 的处理与日志 | `proxy/handler.py:211-216` |
| **HTTP 头部处理** | 过滤 X-Forwarded-For、Connection 等逐跳头 | `proxy/handler.py:107-120` |
| **Transfer-Encoding: chunked** | 按块读取响应体，识别零长度终止块 | `proxy/handler.py:162-183` |
| **Content-Length** | 按字节数精确读取响应 Body | `proxy/handler.py:185-196` |
| **Cache-Control 指令** | 识别 no-store/no-cache/private 跳过缓存 | `proxy/handler.py:255-284` |
| **前向代理 vs 反向代理** | 客户端配置代理地址，代理转发到目标服务器 | `proxy/server.py` |
| **CONNECT 隧道 (HTTPS)** | 建立 TCP 隧道，`select.select` 双向转发加密流量 | `proxy/handler.py:331-345` |
| **DNS 解析** | `socket.create_connection` 自动解析域名 | `proxy/handler.py:290-295` |

### 操作系统 / 并发编程

| 知识点 | 对应实现 | 代码位置 |
|--------|---------|---------|
| **多线程并发** | `ThreadingTCPServer` 为每个连接创建独立线程 | `proxy/server.py` |
| **线程安全** | `threading.Lock()` 保护缓存的读写操作 | `cache/cache_manager.py:22-28` |
| **守护线程** | 代理和管理面板在独立 daemon 线程中运行 | `main.py` |
| **select I/O 多路复用** | CONNECT 隧道中用 `select.select` 同时监听两个 socket | `proxy/handler.py:331-345` |
| **socket 超时** | `settimeout()` 防止恶意/异常连接永久挂起 | `proxy/handler.py:29, 135, 419` |
| **文件 I/O** | 日志按日期写入不同文件，ACL 配置文件读写 | `logger/logger.py`, `access_control/acl.py` |

### 数据结构 / 算法

| 知识点 | 对应实现 | 代码位置 |
|--------|---------|---------|
| **FIFO 缓存淘汰** | `_insert_order` 列表维护插入顺序，满时弹出最旧条目 | `cache/cache_manager.py:106-109` |
| **TTL 过期机制** | `time.time()` 比对 `expires_at`，过期即淘汰 | `cache/cache_manager.py:98-99` |
| **子域名匹配** | 后缀匹配算法：`host.endswith("." + rule)` | `access_control/acl.py:28-38` |
| **URL 规范化** | `urlsplit/urlunsplit` 统一大小写、去除默认端口 | `proxy/handler.py:219-253` |
| **LRU 思想的变体** | 缓存命中时更新 `hit_count` 但不调整位置（简化实现） | `cache/cache_manager.py:39-41` |

### 软件工程

| 知识点 | 对应实现 | 代码位置 |
|--------|---------|---------|
| **模块化设计** | proxy/cache/access_control/logger/admin 六模块分离 | 顶层目录结构 |
| **单一职责原则** | 每个模块职责明确：缓存只管缓存，ACL 只管访问控制 | 各模块文件 |
| **配置与代码分离** | `config.py` 集中管理所有可调参数 | `config.py` |
| **单元测试** | 46 个测试覆盖所有核心模块，使用 Mock 隔离外部依赖 | `tests/` |
| **日志系统** | 结构化日志格式，支持命令行统计和 Web 展示 | `logger/logger.py`, `stats.py` |

---

## 系统架构

```
浏览器 (Edge/Chrome)                管理面板 (浏览器)
      │                                   │
      │ 配置代理 127.0.0.1:8080           │ http://127.0.0.1:8081
      ▼                                   ▼
┌──────────────┐                   ┌──────────────┐
│  ProxyServer │                   │ AdminServer  │
│  :8080       │                   │  :8081       │
│  Threading   │                   │  HTTP Server │
│  TCPServer   │                   │  + REST API  │
└──────┬───────┘                   └──────┬───────┘
       │                                  │
       ▼                                  ▼
┌──────────────────────────────────────────────────┐
│                  ProxyHandler                     │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ 请求解析  │  │ 头部改写  │  │ 响应读取       │  │
│  │ (HTTP格式)│  │ (过滤逐跳)│  │ (CL/chunked)  │  │
│  └──────────┘  └──────────┘  └───────────────┘  │
│                                                     │
│  ┌──────────────┐  ┌────────────┐  ┌──────────┐  │
│  │ CacheManager │  │    ACL     │  │  Logger  │  │
│  │ (TTL+FIFO)  │  │ (黑白名单)  │  │ (按日滚动)│  │
│  └──────────────┘  └────────────┘  └──────────┘  │
└──────────────────────────────────────────────────┘
       │
       ▼
  互联网 (目标服务器)
  HTTP :80 / HTTPS :443
```

**请求处理流程（HTTP GET）：**

```
1. 客户端连接 → ProxyServer 分配线程
2. _recv_request() 读取完整 HTTP 请求
3. _parse_request() 解析方法、目标、头部、Body
4. _extract_target() 提取主机名、端口、路径
5. is_allowed() ACL 检查 → 不通过返回 403 美化页面
6. _normalize_url() 规范化 URL 作为缓存键
7. is_hit(cache_key)? → 命中直接返回缓存内容
8. _rewrite_headers() 过滤逐跳头，添加 X-Proxy-Server
9. _connect_with_retry() 建立到目标服务器的 TCP 连接
10. 发送改写后的请求到目标服务器
11. _read_response() 读取完整响应（处理 Content-Length/chunked）
12. _cacheable_response() 检查是否可缓存 → 存入缓存
13. 转发响应给客户端
14. log_request() 记录日志
```

**CONNECT 隧道流程（HTTPS）：**

```
1. 客户端发送 CONNECT host:443 HTTP/1.1
2. ACL 检查 → 不通过返回 403
3. 建立到目标服务器的 TCP 连接
4. 返回 200 Connection Established 给客户端
5. 进入 _tunnel(): select.select 双向转发加密数据
6. 任一端断开 → 隧道结束
```

---

## 模块详解

### 1. `proxy/` — 代理核心

**server.py** — TCP 监听 + 多线程调度
- `ProxyServer(ThreadingTCPServer)`: 为每个客户端连接创建独立线程
- 设置 `allow_reuse_address = True` 避免重启时端口占用

**handler.py** — 请求处理核心（~430 行）
- `_recv_request()`: 从客户端 socket 读取完整 HTTP 请求，处理 Content-Length 读取 Body
- `_parse_request()`: 按 HTTP/1.1 RFC 7230 格式解析请求行和头部
- `_extract_target()`: 从请求行提取目标（绝对 URL 或相对路径 + Host 头）
- `_rewrite_headers()`: 过滤 Connection/Proxy-Connection 等逐跳头，注入 `X-Proxy-Server`
- `_build_request_bytes()`: 构造发往目标服务器的 HTTP 请求字节流
- `_read_response()`: 读取完整 HTTP 响应，按规范处理：
  - **Content-Length**: 读取指定字节数
  - **Transfer-Encoding: chunked**: 逐块读取直到零长度终止块
  - **无长度**: 读取直到服务器关闭连接或超时
- `_normalize_url()`: 缓存键规范化（小写域名、去默认端口、补路径）
- `_cacheable_response()`: 检查 Cache-Control 是否允许缓存
- `_handle_http()`: HTTP 请求主流程（ACL → 缓存查询 → 转发 → 缓存存储）
- `_handle_connect()`: CONNECT 隧道（ACL → 连接 → select 双向转发）
- `_tunnel()`: `select.select` 实现的双向字节转发
- `_send_blocked()`: 返回美化版 403 页面

### 2. `cache/` — 内存缓存

**cache_manager.py** — 线程安全的内存缓存
- 底层数据结构：`dict` (url → entry) + `list` (插入顺序)
- TTL 过期：`time.time() > expires_at` 时自动淘汰
- FIFO 淘汰：缓存满时移除最早插入的条目
- 线程安全：所有公开方法使用 `threading.Lock()` 保护
- 统计接口：`get_stats()` 返回命中/未命中/大小
- 快照接口：`snapshot()` 返回所有有效条目的详细信息

```
CacheManager 内部结构:
_cache = {
    "http://example.com/": {
        "data": b"HTTP/1.1 200 OK\r\n...<html>...",
        "created_at": 1717459200.0,
        "expires_at": 1717459260.0,
        "hit_count": 3,
    },
    ...
}
_insert_order = ["http://example.com/", "http://neverssl.com/", ...]
```

### 3. `access_control/` — 访问控制

**acl.py** — 域名/IP 访问控制
- 三种模式：`blacklist`（黑名单） / `whitelist`（白名单） / `off`（关闭）
- 子域名匹配：`baidu.com` 匹配 `www.baidu.com`、`map.baidu.com`，不匹配 `fakebaidu.com`
- 配置文件热读取：每次请求都从文件重新读取，无需重启
- Web 接口：`load_acl_config()` / `update_acl_config()` 支持管理面板在线编辑

### 4. `logger/` — 日志系统

**logger.py** — 按日期滚动日志
- 日志格式：`YYYY-MM-DD HH:MM:SS | 客户端IP | 方法 | URL | 状态码 | HIT/MISS`
- 文件命名：`logs/proxy-YYYY-MM-DD.log`
- 线程安全：`threading.Lock()` 保护文件写入
- `get_latest_logs(limit)`: 返回最近 N 条日志供管理面板展示

### 5. `admin/` — Web 管理面板

**server.py** — REST API 服务
- 端点：`/api/dashboard`(聚合数据)、`/api/status`、`/api/summary`、`/api/logs`、`/api/cache`、`/api/acl`
- POST `/api/acl` 在线保存 ACL 配置
- POST `/api/cache/clear` 清空缓存
- 静态文件服务（`static/index.html`, `app.js`, `style.css`）

**static/** — 前端单页应用
- **app.js**: 3 秒轮询 `/api/dashboard`，Chart.js 饼图(HIT/MISS)+柱状图(Top URLs)，ACL 行内编辑
- **style.css**: 响应式网格布局，720px 以下单列
- **index.html**: 面板布局（指标卡片 → 图表 → 表格 → ACL 编辑）

### 6. `config.py` — 集中配置

所有可调参数集中在一处，无需修改业务代码：

```python
PROXY_HOST = "127.0.0.1"     # 代理监听地址
PROXY_PORT = 8080             # 代理监听端口
ADMIN_PORT = 8081             # 管理面板端口
CACHE_TTL_SECONDS = 60        # 缓存过期时间
CACHE_MAX_ITEMS = 128         # 最大缓存条目数
ACL_MODE = "blacklist"        # blacklist / whitelist / off
```

---

## 快速开始

### 环境准备

```bash
# 激活 conda 环境（Python 3.11）
conda activate http-proxy-cache

# 运行测试确认环境正常
python -m pytest tests/ -q
# 46 passed
```

### 启动服务

```bash
python main.py
```

```
[*] Proxy Server started on 127.0.0.1:8080
[*] Admin dashboard started on http://127.0.0.1:8081
```

### 配置浏览器

**方法一：Edge 系统代理设置**

地址栏输入 `edge://settings/system` → 打开代理设置 → 手动设置代理：
- 地址：`127.0.0.1`
- 端口：`8080`

**方法二：SwitchyOmega 插件**

新建情景模式 → 代理服务器 `127.0.0.1:8080` → 一键切换。

---

## 演示流程

### 1. HTTP 代理访问

浏览器访问 `http://neverssl.com/`（专为代理测试设计的纯 HTTP 站点，永不跳转 HTTPS），页面正常加载。

```bash
# 查看日志
cat logs/proxy-$(date +%Y-%m-%d).log
# 2026-06-03 21:30:00 | 127.0.0.1 | GET | http://neverssl.com/ | 200 | MISS
```

### 2. 缓存 HIT/MISS 效果

访问 `http://neverssl.com/`，按 **F5 刷新**。

- 首次：MISS（3-5s，跨洋网络延迟）
- 刷新：HIT（<1ms，从内存缓存读取）

管理面板 `http://127.0.0.1:8081` 可实时看到：
- HIT/MISS 饼图变化
- 命中率数字更新
- 缓存条目列表中出现 `neverssl.com`

```bash
# 命令行查看统计
python stats.py
# Hit Rate: 50.00%
# Top URL: http://neverssl.com/  (2 requests)
```

### 3. ACL 黑名单拦截

```bash
echo "neverssl.com" >> acl.txt
```

无需重启代理（ACL 文件每次请求都会重新读取）。

浏览器访问 `http://neverssl.com/` → **403 Forbidden** 美化页面：
- 显示被拦截的域名
- 显示拦截原因（匹配了哪条黑名单规则）
- 显示代理标识

```bash
# 演示完删除规则
sed -i '/^neverssl.com$/d' acl.txt
```

> 也可以在管理面板 `http://127.0.0.1:8081` 中在线增删黑名单/白名单。

### 4. HTTPS CONNECT 隧道

浏览器访问 `https://www.baidu.com/`，正常加载 HTTPS 页面。

```bash
# 日志中可看到 CONNECT 记录
cat logs/proxy-$(date +%Y-%m-%d).log | grep CONNECT
# 2026-06-03 21:35:00 | 127.0.0.1 | CONNECT | www.baidu.com:443 | 200 | MISS
```

> CONNECT 隧道的流量是加密的，代理无法缓存 HTTPS 内容。这是所有前向代理的通用限制。

### 5. 请求头修改

访问 `http://eu.httpbin.org/get`，返回 JSON 中可看到代理注入的 `X-Proxy-Server: http-proxy-cache`，而 `X-Forwarded-For` 等头已被过滤。

### 6. 并发浏览

同时打开多个标签页访问不同网站，所有请求独立记录，日志无错乱。管理面板可实时看到所有请求流。

### 7. 管理面板总览

`http://127.0.0.1:8081` 展示：
- **指标卡片**：总请求数、命中率、缓存条目、ACL 模式
- **图表**：HIT/MISS 饼图、Top URLs 柱状图（Chart.js 渲染，3s 自动刷新）
- **数据表格**：Top URLs 排行、缓存条目详情、请求日志（支持筛选）
- **ACL 编辑**：行内增删黑白名单/IP 黑名单，点 Save 即时生效

---

## 配置说明

编辑 `config.py`：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `PROXY_HOST` | `127.0.0.1` | 代理监听地址 |
| `PROXY_PORT` | `8080` | 代理监听端口 |
| `ADMIN_HOST` | `127.0.0.1` | 管理面板地址 |
| `ADMIN_PORT` | `8081` | 管理面板端口 |
| `CACHE_TTL_SECONDS` | `60` | 缓存过期时间（秒） |
| `CACHE_MAX_ITEMS` | `128` | 最大缓存条目 |
| `ACL_MODE` | `blacklist` | `blacklist`（黑名单）/ `whitelist`（白名单）/ `off`（关闭） |

ACL 配置文件（纯文本，每行一条规则，`#` 开头为注释）：

- `acl.txt` — 域名黑名单（如 `tencent.com`）
- `whitelist.txt` — 域名白名单（ACL_MODE 设为 whitelist 时生效）
- `ip_blacklist.txt` — IP 黑名单（如 `192.168.1.100`）

---

## 测试

```bash
python -m pytest tests/ -v
```

46 个测试覆盖：

| 测试文件 | 测试数 | 覆盖模块 |
|---------|--------|---------|
| `test_handler.py` | 3 | 403 拦截、POST Body、头部改写 |
| `test_cache_manager.py` | 5 | TTL 过期、FIFO 淘汰、命中统计 |
| `test_acl.py` | 14 | 子域名匹配、黑白名单、IP 黑名单、模式切换 |
| `test_logger.py` | 8 | 日志写入、格式、多线程安全 |
| `test_stats.py` | 6 | 日志解析、统计聚合 |
| `test_integration_proxy.py` | 4 | 端到端 HTTP 代理 |
| `test_connect.py` | 2 | CONNECT 隧道 |
| `test_admin_server.py` | 4 | REST API、仪表盘数据 |

---

## 项目结构

```
http-proxy-cache/
├── main.py                      # 启动入口：同时启动代理和管理面板
├── config.py                    # 集中配置文件
├── stats.py                     # 命令行统计工具
├── acl.txt                      # 域名黑名单文件
├── whitelist.txt                # 域名白名单文件
├── ip_blacklist.txt             # IP 黑名单文件
│
├── proxy/                       # 代理核心模块
│   ├── server.py                # TCP 监听 + ThreadingTCPServer 多线程
│   └── handler.py               # HTTP/HTTPS 请求处理（解析/转发/缓存/ACL/隧道）
│
├── cache/                       # 缓存模块
│   └── cache_manager.py         # 线程安全内存缓存（TTL + FIFO 淘汰）
│
├── access_control/              # 访问控制模块
│   └── acl.py                   # 域名/IP 黑白名单（子域名匹配）
│
├── logger/                      # 日志模块
│   └── logger.py                # 按日期滚动日志（线程安全）
│
├── admin/                       # Web 管理面板
│   ├── server.py                # REST API 服务 + 静态文件托管
│   └── static/
│       ├── index.html           # 管理页 HTML（Chart.js CDN）
│       ├── app.js               # 前端逻辑（图表渲染、ACL编辑、3s轮询）
│       └── style.css            # 响应式样式（支持移动端）
│
├── tests/                       # 测试套件（46 个测试）
│   ├── test_handler.py          # 代理请求处理
│   ├── test_cache_manager.py    # 缓存逻辑
│   ├── test_acl.py              # 访问控制
│   ├── test_logger.py           # 日志写入
│   ├── test_stats.py            # 统计解析
│   ├── test_integration_proxy.py # 集成测试
│   ├── test_connect.py          # CONNECT 隧道
│   └── test_admin_server.py     # 管理 API
│
└── logs/                        # 日志输出目录（自动创建）
    └── proxy-YYYY-MM-DD.log     # 按日期滚动的日志文件
```
