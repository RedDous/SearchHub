from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"


@pytest.fixture(scope="module")
def dockerfile() -> str:
    assert DOCKERFILE.exists(), "Dockerfile missing"
    return DOCKERFILE.read_text()


def test_two_stages_in_order(dockerfile: str):
    froms = [l for l in dockerfile.splitlines() if l.startswith("FROM ")]
    assert len(froms) == 2
    assert "node:22-alpine" in froms[0] and "AS builder" in froms[0]
    assert "python:3.13-slim" in froms[1]


def test_builder_builds_frontend(dockerfile: str):
    assert "RUN npm ci" in dockerfile
    assert "RUN npm run build" in dockerfile


def test_runtime_env_and_copy(dockerfile: str):
    assert "SEARCHHUB_WEB_DIST=/app/web/dist" in dockerfile
    assert "COPY --from=builder /build/dist /app/web/dist" in dockerfile
    assert "RUN pip install . --no-cache-dir" in dockerfile


def test_runtime_healthcheck_and_cmd(dockerfile: str):
    assert "HEALTHCHECK" in dockerfile
    assert "/healthz" in dockerfile
    assert "EXPOSE 8000" in dockerfile
    assert 'CMD ["python", "-m", "searchhub"]' in dockerfile


def test_dockerignore_exists_and_covers_essentials():
    di = (ROOT / ".dockerignore").read_text()
    for entry in [".git", ".venv", "data", "frontend/node_modules", "frontend/dist", "tests"]:
        assert entry in di, f".dockerignore missing {entry}"


def test_gitignore_covers_data_dir():
    gi = (ROOT / ".gitignore").read_text()
    assert "data/" in gi
