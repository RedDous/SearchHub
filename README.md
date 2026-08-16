# SearchHub

Self-hosted web search & extract aggregation service.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

## Run

```bash
.venv/bin/python -m searchhub
```

Environment variables: `SEARCHHUB_HOST` (default `0.0.0.0`), `SEARCHHUB_PORT` (default `8000`), `SEARCHHUB_DATA` (default `./data`).
