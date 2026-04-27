import os
from collections import Counter

import logger.logger

_LOG_FILES = ["proxy.log"]


def _log_dir():
    return logger.logger._LOG_DIR


def _read_logs():
    lines = []
    if os.path.exists(_LOG_FILES[0]):
        with open(_LOG_FILES[0], "r", encoding="utf-8") as f:
            lines.extend(f.readlines())
    log_dir = _log_dir()
    if os.path.isdir(log_dir):
        for fname in sorted(os.listdir(log_dir)):
            path = os.path.join(log_dir, fname)
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
