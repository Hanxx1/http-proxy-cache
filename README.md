# HTTP Proxy Cache (Team Project)

This repository contains a classroom project for building an HTTP proxy cache server.

Current repository scope mainly includes the `C` member deliverables:

- Request logging module: `logger/logger.py`
- Statistics CLI: `stats.py`
- Unit tests: `tests/test_logger.py`, `tests/test_stats.py`
- Development/plan doc: `docx/C同学_logger开发内容与计划.md`

## Environment

- Python: `3.11.9`
- Recommended env name: `http-proxy-cache`

```bash
conda create -n http-proxy-cache python=3.11.9 -y
conda activate http-proxy-cache
```

## C Module Features

### 1) Logger

`log_request(addr, method, url, status, hit)` writes one line per request:

```text
YYYY-MM-DD HH:MM:SS | client_ip | METHOD | URL | STATUS | HIT/MISS
```

Implementation notes:

- Thread-safe write (`threading.Lock`)
- Auto-create log directory
- Daily log file rotation under `logs/`

### 2) Stats CLI

Run:

```bash
python stats.py
```

Output includes:

- Total requests
- Cache hits / misses
- Hit rate
- Top 5 URLs

When no logs exist, CLI exits gracefully with a clear message.

## Tests

Run all tests:

```bash
python -m pytest -q
```

Current status: all tests pass (`14 passed`).

## Notes

- `*.log` is ignored by `.gitignore`.
- This repo is ready for integration with `A/B/D` modules and final server wiring.
