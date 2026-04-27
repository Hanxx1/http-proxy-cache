import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from stats import parse_logs, print_stats
from logger.logger import log_request, _LOG_DIR
import logger.logger as mod


def test_parse_basic_hits_and_misses():
    lines = [
        "2026-04-27 12:00:00 | 127.0.0.1 | GET | http://a.com/ | 200 | HIT\n",
        "2026-04-27 12:00:01 | 127.0.0.1 | GET | http://b.com/ | 200 | MISS\n",
        "2026-04-27 12:00:02 | 127.0.0.1 | GET | http://a.com/ | 200 | HIT\n",
    ]
    total, hits, url_counter = parse_logs(lines)
    assert total == 3
    assert hits == 2
    assert url_counter["http://a.com/"] == 2
    assert url_counter["http://b.com/"] == 1


def test_parse_empty_lines():
    lines = ["", "   ", "\n"]
    total, hits, url_counter = parse_logs(lines)
    assert total == 0
    assert hits == 0
    assert len(url_counter) == 0


def test_parse_malformed_line():
    lines = ["garbage line without delimiters\n"]
    total, hits, url_counter = parse_logs(lines)
    assert total == 0
    assert hits == 0


def test_parse_top5():
    lines = [
        f"2026-04-27 12:00:00 | 127.0.0.1 | GET | http://url{i}.com/ | 200 | HIT\n"
        for i in range(10)
    ]
    total, hits, url_counter = parse_logs(lines)
    assert total == 10
    # All URLs are unique, so top5 should have 5 entries
    assert len(url_counter) == 10
    top5 = url_counter.most_common(5)
    assert len(top5) == 5


def test_stats_does_not_crash_with_no_files():
    """stats.main() should handle missing files gracefully."""
    from stats import main
    # Temporarily redirect stdout to avoid output noise
    import io
    from contextlib import redirect_stdout

    # Backup original paths
    orig_log_files = mod._LOG_DIR
    mod._LOG_DIR = "/tmp/nonexistent_dir_for_test_xyz"

    f = io.StringIO()
    with redirect_stdout(f):
        try:
            main()
        except SystemExit:
            pass
    output = f.getvalue()
    assert "No log files" in output or "nothing" in output

    mod._LOG_DIR = orig_log_files


def test_stats_from_real_logs():
    """Write real logs then parse them with stats."""
    orig_dir = mod._LOG_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        mod._LOG_DIR = tmpdir
        log_request(("127.0.0.1", 1), "GET", "http://popular.com/", 200, True)
        log_request(("127.0.0.1", 2), "GET", "http://popular.com/", 200, True)
        log_request(("127.0.0.1", 3), "GET", "http://other.com/", 200, False)

        from stats import _read_logs
        lines = _read_logs()
        total, hits, url_counter = parse_logs(lines)
        assert total == 3
        assert hits == 2
        assert url_counter["http://popular.com/"] == 2
        assert url_counter["http://other.com/"] == 1
    mod._LOG_DIR = orig_dir
