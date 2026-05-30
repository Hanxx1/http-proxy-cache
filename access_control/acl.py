from pathlib import Path
from config import ACL_FILE, WHITELIST_FILE, IP_BLACKLIST_FILE, ACL_MODE

# Runtime modifiable mode
_MODE = ACL_MODE


def _read_config_file(file_path):
    """Read a config file, ignoring empty lines and comments."""
    path = Path(file_path)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    except Exception:
        return []


def _write_config_file(file_path, lines):
    """Write lines to a config file."""
    path = Path(file_path)
    with open(path, "w", encoding="utf-8") as f:
        for item in lines:
            f.write(f"{item}\n")


def domain_match(host, rule):
    """Check if host matches a domain rule with subdomain support.

    Examples:
        domain_match("www.baidu.com", "baidu.com") → True
        domain_match("map.baidu.com", "baidu.com") → True
        domain_match("fakebaidu.com", "baidu.com") → False
    """
    host = host.lower().strip(".")
    rule = rule.lower().strip(".")
    return host == rule or host.endswith("." + rule)


def init_templates():
    """Create template config files if they don't exist."""
    templates = {
        ACL_FILE: "# Domain blacklist\nbaidu.com\ntencent.com\n",
        WHITELIST_FILE: "# Domain whitelist\ngithub.com\ngoogle.com\n",
        IP_BLACKLIST_FILE: "# IP blacklist\n# 127.0.0.1\n192.168.1.100\n",
    }
    for file_path, content in templates.items():
        path = Path(file_path)
        if not path.exists():
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)


def get_mode():
    return _MODE


def set_mode(mode):
    global _MODE
    if mode not in ("blacklist", "whitelist", "off"):
        raise ValueError("mode must be 'blacklist', 'whitelist', or 'off'")
    _MODE = mode


def is_allowed(host, client_ip=None):
    if _MODE == "off":
        return True

    if client_ip:
        ip_blacklist = _read_config_file(IP_BLACKLIST_FILE)
        if client_ip in ip_blacklist:
            return False

    if _MODE == "whitelist":
        whitelist = _read_config_file(WHITELIST_FILE)
        return any(domain_match(host, rule) for rule in whitelist)

    blacklist = _read_config_file(ACL_FILE)
    if any(domain_match(host, rule) for rule in blacklist):
        return False
    return True


def load_acl_config():
    return {
        "mode": _MODE,
        "blacklist": _read_config_file(ACL_FILE),
        "whitelist": _read_config_file(WHITELIST_FILE),
        "ip_blacklist": _read_config_file(IP_BLACKLIST_FILE),
    }


def update_acl_config(data):
    global _MODE
    if "mode" in data:
        set_mode(data["mode"])
    if "blacklist" in data:
        _write_config_file(ACL_FILE, data["blacklist"])
    if "whitelist" in data:
        _write_config_file(WHITELIST_FILE, data["whitelist"])
    if "ip_blacklist" in data:
        _write_config_file(IP_BLACKLIST_FILE, data["ip_blacklist"])


# Auto-initialize templates on import
if __name__ == "__main__":
    init_templates()
else:
    init_templates()
