# D模块（访问控制与测试覆盖）交付说明

本文档旨在指导组长及其他成员（特别是 A同学 Handler）如何集成和使用 D模块。

## 1. 功能说明与配置

D模块主要负责请求的访问控制（ACL），支持以下功能：
- **IP 级封禁**：优先检查客户端 IP 是否在黑名单中。
- **域名控制**：支持“黑名单”和“白名单”两种模式，通过 `access_control/acl.py` 中的全局变量 `MODE` 切换。

### 配置文件说明
所有配置文件位于项目根目录，采用纯文本格式，每行一个条目（自动忽略空行和首尾空格）：
- `ip_blacklist.txt`: 存放需要封禁的客户端 IP 地址。
- `acl.txt`: 黑名单模式下使用的域名列表。
- `whitelist.txt`: 白名单模式下使用的域名列表。

> **注意**：如果文件不存在，程序会自动创建包含示例数据的模板文件，并视为空列表处理，不会报错。

---

## 2. A同学（Handler）集成指南

在 `proxy/handler.py` 中接收到客户端连接并解析出请求头后，请按照以下步骤集成：

### 调用 `is_allowed()`
导入模块并进行判断：
```python
from access_control.acl import is_allowed
from logger.logger import log_request

# 假设解析出的变量如下：
# host: 请求的域名 (str)
# client_addr: 客户端地址元组 (ip, port)
# method: 请求方法 (str, 如 "GET")
# url: 完整请求 URL (str)

if not is_allowed(host, client_addr[0]):
    # 1. 构造 403 Forbidden 响应报文
    response = (
        "HTTP/1.1 403 Forbidden\r\n"
        "Content-Type: text/html\r\n"
        "Connection: close\r\n"
        "\r\n"
        "<html><body><h1>403 Forbidden</h1><p>Access Denied by Proxy ACL.</p></body></html>"
    ).encode("utf-8")
    
    # 2. 发送给客户端 (假设 client_socket 是已建立的连接)
    client_socket.sendall(response)
    
    # 3. 调用 C 模块记录日志 (状态码 403, 缓存命中为 False)
    log_request(client_addr, method, url, 403, False)
    
    # 4. 关闭连接并结束当前处理逻辑
    client_socket.close()
    return
```

---

## 3. 测试与覆盖率指南

本项目使用 `pytest` 进行单元测试，并使用 `pytest-cov` 统计覆盖率。

### 运行单元测试
在根目录下运行以下命令：
```bash
python -m pytest
```

### 查看 D 模块覆盖率
运行以下命令查看 `access_control` 目录的详细覆盖率报告：
```bash
python -m pytest --cov=access_control tests/test_acl.py
```

目前 D 模块的单元测试覆盖率已达到 **91%**，确保了核心逻辑（黑/白名单切换、IP 封禁、文件处理）的稳定性。

---
**交付负责人**：D同学 (保安)
**日期**：2026-04-28
