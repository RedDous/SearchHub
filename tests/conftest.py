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


@pytest.fixture
def admin_client(data_dir):
    from fastapi.testclient import TestClient

    from searchhub.api.app import create_app
    from searchhub.config import ConfigService

    cs = ConfigService(data_dir)
    cs.load()
    cs.set_admin_password("testpass123")
    app = create_app(data_dir)
    with TestClient(app) as c:
        r = c.post("/api/admin/login", json={"username": "admin", "password": "testpass123"})
        assert r.status_code == 200, r.text
        yield c
