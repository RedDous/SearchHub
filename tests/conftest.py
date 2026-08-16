from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from searchhub.api.app import create_app


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def app(data_dir: Path):
    return create_app(data_dir)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c
