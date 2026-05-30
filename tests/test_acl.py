import pytest
from unittest.mock import patch, mock_open
from access_control import acl


def _as_str(p):
    """Convert path-like to string for mock lambdas."""
    return str(p)


def test_is_allowed_ip_blacklisted():
    with patch("access_control.acl._read_config_file") as mock_read:
        mock_read.side_effect = lambda p: ["127.0.0.1"] if "ip_blacklist" in _as_str(p) else []
        assert acl.is_allowed("google.com", "127.0.0.1") is False


def test_is_allowed_blacklist_mode_blocked():
    acl.set_mode("blacklist")
    with patch("access_control.acl._read_config_file") as mock_read:
        mock_read.side_effect = lambda p: ["baidu.com"] if "acl.txt" in _as_str(p) else []
        assert acl.is_allowed("baidu.com", "1.1.1.1") is False
        assert acl.is_allowed("google.com", "1.1.1.1") is True
    acl.set_mode("blacklist")


def test_is_allowed_whitelist_mode():
    acl.set_mode("whitelist")
    with patch("access_control.acl._read_config_file") as mock_read:
        mock_read.side_effect = lambda p: ["github.com"] if "whitelist" in _as_str(p) else []
        assert acl.is_allowed("github.com", "1.1.1.1") is True
        assert acl.is_allowed("baidu.com", "1.1.1.1") is False
    acl.set_mode("blacklist")


def test_subdomain_matching():
    """子域名匹配：baidu.com 应匹配 www.baidu.com 但不匹配 fakebaidu.com"""
    assert acl.domain_match("www.baidu.com", "baidu.com") is True
    assert acl.domain_match("map.baidu.com", "baidu.com") is True
    assert acl.domain_match("baidu.com", "baidu.com") is True
    assert acl.domain_match("fakebaidu.com", "baidu.com") is False
    assert acl.domain_match("baidu.com.cn", "baidu.com") is False


def test_subdomain_matching_case_insensitive():
    assert acl.domain_match("WWW.Baidu.COM", "baidu.com") is True
    assert acl.domain_match("www.BAIDU.com", "BAIDU.COM") is True


def test_domain_matching_with_trailing_dot():
    assert acl.domain_match("www.baidu.com.", "baidu.com") is True


def test_is_allowed_with_subdomain_blacklist():
    acl.set_mode("blacklist")
    with patch("access_control.acl._read_config_file") as mock_read:
        mock_read.side_effect = lambda p: ["baidu.com"] if "acl.txt" in _as_str(p) else []
        assert acl.is_allowed("www.baidu.com", "1.1.1.1") is False
        assert acl.is_allowed("map.baidu.com", "1.1.1.1") is False
        assert acl.is_allowed("fakebaidu.com", "1.1.1.1") is True
    acl.set_mode("blacklist")


def test_is_allowed_with_subdomain_whitelist():
    acl.set_mode("whitelist")
    with patch("access_control.acl._read_config_file") as mock_read:
        mock_read.side_effect = (
            lambda p: ["github.com"] if "whitelist" in _as_str(p) else []
        )
        assert acl.is_allowed("api.github.com", "1.1.1.1") is True
        assert acl.is_allowed("github.com", "1.1.1.1") is True
        assert acl.is_allowed("google.com", "1.1.1.1") is False
    acl.set_mode("blacklist")


def test_acl_mode_off():
    acl.set_mode("off")
    assert acl.is_allowed("blocked.com", "127.0.0.1") is True
    acl.set_mode("blacklist")


def test_read_config_file_filtering():
    mock_content = "  baidu.com  \n\n  google.com  \n# comment\n"
    with patch("builtins.open", mock_open(read_data=mock_content)):
        with patch("pathlib.Path.exists", return_value=True):
            lines = acl._read_config_file("fake_path")
            assert lines == ["baidu.com", "google.com"]


def test_read_config_file_not_exists():
    with patch("pathlib.Path.exists", return_value=False):
        lines = acl._read_config_file("non_existent.txt")
        assert lines == []


def test_init_templates_creates_files():
    with patch("pathlib.Path.exists", return_value=False):
        with patch("builtins.open", mock_open()) as mocked_file:
            acl.init_templates()
            assert mocked_file.call_count == 3


def test_load_acl_config():
    acl.set_mode("blacklist")
    with patch("access_control.acl._read_config_file") as mock_read:
        mock_read.side_effect = lambda p: []
        config = acl.load_acl_config()
        assert config["mode"] == "blacklist"
        assert isinstance(config["blacklist"], list)
        assert isinstance(config["whitelist"], list)
        assert isinstance(config["ip_blacklist"], list)


def test_set_mode_rejects_invalid():
    with pytest.raises(ValueError):
        acl.set_mode("invalid")
