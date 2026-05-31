from collections import Counter
from pathlib import Path

from logger.logger import get_log_dir

_LOG_FILES = ["proxy.log"]


def _iter_log_paths():
    seen = set()

    for fname in _LOG_FILES:
        path = Path(fname)
        if path.is_file():
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield path

    log_dir = Path(get_log_dir())
    if not log_dir.is_dir():
        return

    for path in sorted(log_dir.glob("*.log")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        yield path


def _read_logs():
    lines = []
    for path in _iter_log_paths():
        with open(path, "r", encoding="utf-8") as f:
            lines.extend(f.readlines())
    return lines


def parse_logs(lines):
    total = 0
    hits = 0
    url_counter = Counter()

    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split(" | ")
        if len(parts) != 6:
            continue
        _, _, _, url, _, hit_str = parts
        total += 1
        if hit_str == "HIT":
            hits += 1
        url_counter[url] += 1

    return total, hits, url_counter


def print_stats(total, hits, url_counter):
    misses = total - hits
    hit_rate = (hits / total * 100) if total > 0 else 0.0
    top5 = url_counter.most_common(5)

    print("HTTP Proxy Cache Statistics")
    print("=" * 27)
    print(f"{'Total Requests':<16}: {total}")
    print(f"{'Cache Hits':<16}: {hits}")
    print(f"{'Cache Misses':<16}: {misses}")
    print(f"{'Hit Rate':<16}: {hit_rate:.2f}%")
    print()
    print("Top 5 URLs")
    print("-" * 10)
    if not top5:
        print("(no data)")
    else:
        for i, (url, count) in enumerate(top5, 1):
            print(f"{i}. {url:<40} {count}")


def main():
    lines = _read_logs()
    if not lines:
        print("No log files found. Nothing to show.")
        return
    total, hits, url_counter = parse_logs(lines)
    print_stats(total, hits, url_counter)


if __name__ == "__main__":
    main()
