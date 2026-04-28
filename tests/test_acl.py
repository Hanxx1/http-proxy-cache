import pytest
from unittest.mock import patch, mock_open
from access_control import acl

def test_is_allowed_ip_blacklisted():
    """测试 IP 在黑名单中时被拒绝"""
    with patch("access_control.acl._read_config_file") as mock_read:
        # 模拟 IP 黑名单包含该 IP
        mock_read.side_effect = lambda path: ["127.0.0.1"] if "ip_blacklist" in path else []
        
        # 即使域名合法，IP 在黑名单也应该返回 False
        assert acl.is_allowed("google.com", "127.0.0.1") is False

def test_is_allowed_blacklist_mode_blocked():
    """测试黑名单模式下域名被拦截"""
    acl.MODE = "blacklist"
    with patch("access_control.acl._read_config_file") as mock_read:
        # 模拟域名在黑名单中
        mock_read.side_effect = lambda path: ["baidu.com"] if "acl.txt" in path else []
        
        assert acl.is_allowed("baidu.com", "1.1.1.1") is False
        assert acl.is_allowed("google.com", "1.1.1.1") is True

def test_is_allowed_whitelist_mode():
    """测试白名单模式"""
    acl.MODE = "whitelist"
    with patch("access_control.acl._read_config_file") as mock_read:
        # 模拟域名在白名单中
        mock_read.side_effect = lambda path: ["github.com"] if "whitelist" in path else []
        
        assert acl.is_allowed("github.com", "1.1.1.1") is True
        assert acl.is_allowed("baidu.com", "1.1.1.1") is False
    # 恢复默认模式
    acl.MODE = "blacklist"

def test_read_config_file_filtering():
    """测试配置文件读取逻辑（过滤空行和空格）"""
    mock_content = "  baidu.com  \n\n  google.com  \n# comment\n"
    with patch("builtins.open", mock_open(read_data=mock_content)):
        with patch("pathlib.Path.exists", return_value=True):
            lines = acl._read_config_file("fake_path")
            assert lines == ["baidu.com", "google.com"]

def test_read_config_file_not_exists():
    """测试文件不存在时返回空列表"""
    with patch("pathlib.Path.exists", return_value=False):
        lines = acl._read_config_file("non_existent.txt")
        assert lines == []

def test_init_templates_creates_files():
    """测试模板初始化（文件不存在时创建）"""
    with patch("pathlib.Path.exists", return_value=False):
        with patch("builtins.open", mock_open()) as mocked_file:
            acl.init_templates()
            # 应该尝试打开并写入三个文件
            assert mocked_file.call_count == 3
