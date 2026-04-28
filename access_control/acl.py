import os
from pathlib import Path

# 默认控制模式: "blacklist" 或 "whitelist"
MODE = "blacklist"

# 配置文件路径
ACL_FILE = "acl.txt"
WHITELIST_FILE = "whitelist.txt"
IP_BLACKLIST_FILE = "ip_blacklist.txt"


def _read_config_file(file_path: str) -> list[str]:
    """读取配置文件，忽略空行和首尾空格"""
    path = Path(file_path)
    if not path.exists():
        return []
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    except Exception:
        return []


def init_templates():
    """在根目录生成三个控制列表的示例模板"""
    templates = {
        ACL_FILE: "# 域名黑名单示例\nbaidu.com\ntencent.com\n",
        WHITELIST_FILE: "# 域名白名单示例\ngithub.com\ngoogle.com\n",
        IP_BLACKLIST_FILE: "# IP黑名单示例\n# 127.0.0.1 (本地测试时请勿开启，否则会拦截所有本地请求)\n192.168.1.100\n"
    }
    
    for file_name, content in templates.items():
        path = Path(file_name)
        if not path.exists():
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)


def is_allowed(host: str, client_ip: str = None) -> bool:
    """
    核心接口：判断请求是否允许访问
    1. 优先检查 IP 黑名单
    2. 根据 MODE 检查域名黑名单或白名单
    """
    # 1. 检查 IP 黑名单
    if client_ip:
        ip_blacklist = _read_config_file(IP_BLACKLIST_FILE)
        if client_ip in ip_blacklist:
            return False

    # 2. 根据模式检查域名
    if MODE == "whitelist":
        whitelist = _read_config_file(WHITELIST_FILE)
        # 如果域名不在白名单中，拒绝访问
        return host in whitelist
    else:
        # 默认黑名单模式
        blacklist = _read_config_file(ACL_FILE)
        # 如果域名在黑名单中，拒绝访问
        return host not in blacklist


# 初始化模板文件
if __name__ == "__main__":
    init_templates()
else:
    # 模块被导入时也尝试初始化（如果文件不存在）
    init_templates()
