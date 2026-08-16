from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient

from searchhub.api.app import create_app


def make_dist(data_dir: Path) -> Path:
    dist = data_dir / "webdist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>spa</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    return dist


def test_static_serving_and_spa_fallback(data_dir, monkeypatch):
    dist = make_dist(data_dir)
    monkeypatch.setenv("SEARCHHUB_WEB_DIST", str(dist))
    with TestClient(create_app(data_dir)) as c:
        assert c.get("/").status_code == 200
        assert c.get("/").text == "<html>spa</html>"
        assert c.get("/providers").text == "<html>spa</html>"  # SPA fallback
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/history?x=1").status_code == 200  # SPA fallback 带 query


def test_api_404_stays_json(data_dir, monkeypatch):
    dist = make_dist(data_dir)
    monkeypatch.setenv("SEARCHHUB_WEB_DIST", str(dist))
    with TestClient(create_app(data_dir)) as c:
        r = c.get("/v1/nonexistent")
        assert r.status_code == 404
        assert r.json()["success"] is False
        r = c.get("/api/admin/nonexistent")
        assert r.status_code == 404
        assert r.json()["success"] is False


def test_no_dist_no_mount(data_dir, monkeypatch):
    monkeypatch.setenv("SEARCHHUB_WEB_DIST", str(data_dir / "missing-dist"))
    with TestClient(create_app(data_dir)) as c:
        assert c.get("/").status_code == 404


def test_path_traversal_blocked(data_dir, monkeypatch):
    dist = make_dist(data_dir)
    monkeypatch.setenv("SEARCHHUB_WEB_DIST", str(dist))
    with TestClient(create_app(data_dir)) as c:
        r = c.get(quote("../../etc/passwd", safe=""))
        assert r.status_code == 404, r.text
        assert "root:" not in r.text
        r = c.get(quote("/etc/passwd", safe=""))
        assert r.status_code == 404, r.text
        assert "root:" not in r.text
        r = c.get(quote("..\\..\\etc\\passwd", safe=""))
        assert r.status_code == 404, r.text
        assert "root:" not in r.text


def test_spa_fallback_deep_path(data_dir, monkeypatch):
    dist = make_dist(data_dir)
    monkeypatch.setenv("SEARCHHUB_WEB_DIST", str(dist))
    with TestClient(create_app(data_dir)) as c:
        r = c.get("/providers/new")
        assert r.status_code == 200
        assert r.text == "<html>spa</html>"
