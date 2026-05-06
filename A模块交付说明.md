# A模块（请求处理与转发）交付说明

本文档用于说明 A 模块当前已交付功能、接口行为、与其他模块集成方式，以及验收测试方法。

## 1. 模块定位

A 模块负责代理请求处理主链路，核心职责包括：

- 解析客户端 HTTP 请求行与请求头
- 将请求转发到目标服务器
- 将目标服务器响应原样回传给客户端
- 修改转发请求头（添加自定义头、过滤指定字段）
- 支持 HTTPS `CONNECT` 隧道转发

当前实现文件：

- `proxy/handler.py`
- `tests/test_handler.py`

## 2. 已实现功能

### 2.1 HTTP 请求解析与转发

已实现：

- 解析请求行：`METHOD TARGET VERSION`
- 解析请求头字段（`Key: Value`）
- 识别绝对 URL 与相对路径两种请求形式
- 解析目标主机、端口、路径后建立 TCP 连接转发
- 读取目标服务器响应并原样返回客户端

错误处理：

- 非法请求返回 `400 Bad Request`
- 上游连接失败或读取失败返回 `502 Bad Gateway`
- 处理异常返回 `500 Internal Server Error`

### 2.2 请求头改写

已实现请求头处理策略：

- 添加自定义头：`X-Proxy-Server: http-proxy-cache`
- 过滤 `X-Forwarded-For`
- 同时过滤常见 hop-by-hop 头（如 `Connection`、`Proxy-Connection` 等）
- 强制转发请求使用 `Connection: close`

### 2.3 HTTPS CONNECT 隧道

已实现：

- 识别 `CONNECT host:port` 请求
- ACL 允许后与目标建立连接
- 向客户端返回 `200 Connection Established`
- 进入双向隧道透传（客户端 <-> 目标服务器）

## 3. 与其他模块集成

### 3.1 D 模块（ACL）

集成点：`proxy/handler.py` 在 HTTP 与 CONNECT 路径中均调用 `is_allowed(host, client_ip)`。

- 不允许访问时返回 `403 Forbidden`
- 通过 `log_request(...)` 记录被拦截请求

### 3.2 C 模块（Logger）

A 模块在以下场景记录日志：

- HTTP 命中缓存返回
- HTTP 转发成功/失败
- CONNECT 允许/拒绝/失败

日志字段格式由 C 模块维护，A 模块仅按约定传参与调用。

### 3.3 B 模块（Cache）

当前 A 模块已接入基础缓存调用：

- 对 `GET` 请求先检查 `cache.is_hit(url)`
- 命中则直接 `cache.get(url)` 返回
- 未命中转发上游，`200` 响应则 `cache.set(url, response)`

## 4. 验收测试

## 4.1 自动化测试

运行：

```bash
python -m pytest -q
```

结果：`27 passed`

`tests/test_handler.py` 已覆盖基础场景：

- ACL 拒绝时返回 `403`
- 转发请求头已过滤 `X-Forwarded-For`
- 转发请求头已添加 `X-Proxy-Server`
- 转发链路可返回 `200`

### 4.2 手动测试 1（curl 代理 GET 百度）

注意：若 `acl.txt` 中存在 `baidu.com`，会被 ACL 拦截返回 `403`，测试前请确认策略允许。

代理启动：

```bash
python main.py
```

测试命令（Windows）：

```bash
curl.exe -x http://127.0.0.1:8080 -L -o NUL -s -w "%{http_code}" http://www.baidu.com/
```

预期输出：

```text
200
```

### 4.3 手动测试 2（请求头改写验证）

可通过 Wireshark 或本地打印服务确认。

关键验收点：

- 存在 `X-Proxy-Server: http-proxy-cache`
- 不存在 `X-Forwarded-For`

## 5. 交付清单

- 已完成 `proxy/handler.py` 代理主链路实现
- 已完成 HTTP 请求解析与上游转发
- 已完成请求头改写策略
- 已完成 HTTPS CONNECT 隧道支持
- 已完成与 ACL/Logger/Cache 集成调用
- 已补充 `tests/test_handler.py` 基础测试
- 已通过项目测试：`python -m pytest -q`

**交付负责人**：A 同学（请求处理与转发）

**日期**：2026-05-06
