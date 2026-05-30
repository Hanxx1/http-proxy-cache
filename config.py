from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8080

CACHE_TTL_SECONDS = 60
CACHE_MAX_ITEMS = 128

ACL_MODE = "blacklist"

ACL_FILE = BASE_DIR / "acl.txt"
WHITELIST_FILE = BASE_DIR / "whitelist.txt"
IP_BLACKLIST_FILE = BASE_DIR / "ip_blacklist.txt"

LOG_DIR = str(BASE_DIR / "logs")
