# C 同学开发内容与计划

## 一、项目背景

本项目是一个 HTTP 代理缓存服务器。客户端通过本地代理访问目标网站，代理服务器负责接收请求、解析请求、转发请求、回传响应，并在过程中完成缓存、访问控制、日志记录和统计分析等功能。

C 同学的定位是“史官”，负责记录代理服务器运行过程中的访问行为，并基于日志生成统计报表。日志模块本身不直接处理网络转发，但会被 `proxy/server.py` 或 `proxy/handler.py` 在每次请求完成后调用。

## 二、C 同学负责模块

主要负责以下文件：

- `logger/logger.py`
- `stats.py`
- `proxy.log` 或按日期生成的日志文件
- 必要时补充 `tests/` 中与日志统计相关的测试

## 三、阶段一：基础日志功能

### 1. 目标

实现 `log_request()` 函数，将每次代理请求记录到日志文件中。

### 2. 必须实现的接口

```python
def log_request(addr, method, url, status, hit):
    ...
```

参数说明：

- `addr`：客户端地址元组，例如 `("127.0.0.1", 54321)`
- `method`：HTTP 方法，例如 `GET`、`POST`、`CONNECT`
- `url`：客户端访问的完整 URL 或目标地址
- `status`：响应状态码，例如 `200`、`403`、`502`
- `hit`：缓存是否命中，`True` 表示 HIT，`False` 表示 MISS

### 3. 日志格式

阶段一统一写入 `proxy.log`，每一行记录一次请求。

建议格式：

```text
2026-04-26 23:30:00 | 127.0.0.1 | GET | http://example.com/ | 200 | HIT
```

字段顺序：

1. 时间
2. 客户端 IP
3. 请求方法
4. URL
5. 状态码
6. 缓存结果：`HIT` 或 `MISS`

### 4. 实现要求

- 追加写入日志，不覆盖旧日志。
- 每次调用 `log_request()` 必须写入一行。
- 每行末尾必须有换行符。
- 多线程环境下写日志要加锁，避免日志内容交错。
- 日志目录或文件不存在时要自动创建。
- `status` 和 `hit` 即使传入的是整数或布尔值，也要格式化成稳定文本。

### 5. 阶段一验收标准

执行 10 条代理请求后：

- `proxy.log` 中至少有 10 行记录。
- 每一行都包含时间、IP、方法、URL、状态码、`HIT` 或 `MISS`。
- 日志内容没有多线程写入导致的错乱。

## 四、阶段二：日志滚动与统计 CLI

### 1. 目标

在基础日志功能上扩展：

- 日志按日期滚动，每天一个文件。
- 编写 `stats.py`，从日志文件中统计访问情况。

### 2. 日志滚动设计

阶段二建议将日志文件放在 `logs/` 目录下，按日期命名：

```text
logs/proxy-2026-04-26.log
logs/proxy-2026-04-27.log
```

滚动规则：

- `log_request()` 每次写入前获取当前日期。
- 根据日期自动选择当天日志文件。
- 日期变化后自动写入新的日志文件。
- 保留阶段一兼容性：如团队要求仍使用 `proxy.log`，可以同时写入或通过配置切换。

### 3. 统计 CLI 功能

新增项目根目录文件：

```text
stats.py
```

运行方式：

```bash
python stats.py
```

统计内容：

- 总请求数
- 缓存命中数
- 缓存未命中数
- 缓存命中率
- Top5 热门 URL

### 4. CLI 输出示例

```text
HTTP Proxy Cache Statistics
===========================
Total Requests : 120
Cache Hits     : 45
Cache Misses   : 75
Hit Rate       : 37.50%

Top 5 URLs
----------
1. http://example.com/              30
2. http://example.com/index.html    22
3. http://baidu.com/                18
4. http://github.com/               12
5. http://python.org/               9
```

### 5. 阶段二验收标准

- 日志文件能按日期自动分割。
- `python stats.py` 能输出格式化统计表。
- 统计结果能正确计算总请求数、命中率和 Top5 热门 URL。
- 日志为空或日志文件不存在时，程序能给出友好提示，不直接崩溃。

## 五、与其他同学的接口约定

### 1. 与组长 / Server 集成

组长在请求处理完成后调用：

```python
log_request(client_addr, method, url, status_code, cache_hit)
```

调用位置通常在：

- 请求正常转发完成后
- 缓存命中直接返回后
- 被 ACL 拦截返回 403 后
- 代理内部错误返回 500 或 502 后

### 2. 与 A 同学 / Handler 集成

A 同学负责解析请求和转发响应，需要提供：

- `method`
- `url`
- `status_code`

对于 HTTPS CONNECT：

- `method` 为 `CONNECT`
- `url` 可以记录为 `host:port`
- 成功建立隧道后状态码记录为 `200`

### 3. 与 B 同学 / Cache 集成

B 同学负责缓存模块，需要在请求处理时提供缓存命中结果：

- 命中缓存：`hit=True`
- 未命中缓存：`hit=False`

C 同学不直接判断缓存是否命中，只负责记录传入结果。

### 4. 与 D 同学 / ACL 集成

D 同学负责访问控制：

- 允许访问：继续后续请求流程。
- 禁止访问：返回 `403`，并调用日志记录。

被黑名单或白名单拦截时，日志示例：

```text
2026-04-26 23:30:00 | 127.0.0.1 | GET | http://blocked.com/ | 403 | MISS
```

## 六、开发计划

### 第 1 步：完成基础日志函数

- 创建或完善 `logger/logger.py`。
- 实现 `log_request()`。
- 使用 `threading.Lock` 保证并发写入安全。
- 默认写入 `proxy.log`。

### 第 2 步：本地自测日志格式

- 手动调用 `log_request()` 写入 10 条测试记录。
- 检查 `proxy.log` 行数和格式。
- 验证 `HIT` / `MISS` 输出是否正确。

### 第 3 步：等待组长集成

- 确认组长在请求完成后调用 `log_request()`。
- 检查正常请求、缓存命中、ACL 拦截、异常请求是否都能写日志。

### 第 4 步：实现日志按日期滚动

- 新增 `logs/` 目录。
- 日志文件命名为 `proxy-YYYY-MM-DD.log`。
- 保证每天自动写到不同文件。

### 第 5 步：实现统计 CLI

- 新增 `stats.py`。
- 读取 `logs/` 下所有日志文件，必要时兼容读取 `proxy.log`。
- 解析日志字段。
- 计算总请求数、命中率、Top5 热门 URL。

### 第 6 步：补充测试

建议测试点：

- `log_request()` 能创建日志文件。
- 连续调用 10 次能写入 10 行。
- `hit=True` 输出 `HIT`，`hit=False` 输出 `MISS`。
- `stats.py` 能正确统计命中率和热门 URL。
- 日志文件不存在时 `stats.py` 不崩溃。

### 第 7 步：联调与验收

- 启动代理服务器。
- 使用 curl 或浏览器发起多次请求。
- 检查日志是否实时增加。
- 检查统计 CLI 输出是否正确。
- 保存截图或终端输出，供实验报告使用。

## 七、风险点与解决方案

### 1. 多线程写日志错乱

风险：多个请求同时写日志，导致一行内容混在一起。

解决：在 `logger/logger.py` 中使用全局 `threading.Lock`。

### 2. URL 中包含空格或特殊字符

风险：统计 CLI 解析日志时字段错位。

解决：日志字段使用固定分隔符 ` | `，解析时按该分隔符拆分。

### 3. 阶段一和阶段二日志路径不一致

风险：阶段一要求 `proxy.log`，阶段二要求按日期滚动。

解决：先实现 `proxy.log`；阶段二再扩展 `logs/proxy-YYYY-MM-DD.log`，`stats.py` 同时兼容两种路径。

### 4. 状态码来源不稳定

风险：请求失败时没有真实 HTTP 状态码。

解决：由 handler 或 server 传入内部状态码，例如连接失败使用 `502`，程序异常使用 `500`。

## 八、推荐提交顺序

1. `docs: add C logger development plan`
2. `feat: implement request logging`
3. `test: add logger tests`
4. `feat: add daily log rotation`
5. `feat: add stats CLI`
6. `test: add stats tests`

## 九、最终交付物

C 同学最终需要交付：

- 可用的 `logger/logger.py`
- 可运行的 `stats.py`
- 正确生成的日志文件
- 日志模块相关测试
- 能展示 `python stats.py` 输出结果
- 实验报告中日志与统计模块的实现说明
