from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_workflow_exists_and_triggers():
    path = ROOT / ".github/workflows/docker-image.yml"
    assert path.exists()
    wf = yaml.safe_load(path.read_text())
    on = wf["on"]
    assert "main" in on["push"]["branches"]
    assert "v*" in on["push"]["tags"]


def test_workflow_builds_multiarh_and_pushes_ghcr():
    wf = yaml.safe_load((ROOT / ".github/workflows/docker-image.yml").read_text())
    steps = wf["jobs"]["build"]["steps"]
    actions = [s["uses"] for s in steps if "uses" in s]
    assert any("build-push-action" in a for a in actions)
    assert any("login-action" in a for a in actions)
    assert any("setup-qemu" in a for a in actions)
    build = next(s for s in steps if "build-push-action" in s["uses"])
    assert build["with"]["platforms"] == "linux/amd64,linux/arm64"
    assert build["with"]["push"] is True
    assert "ghcr.io" in build["with"]["tags"]


def test_workflow_compose_image_consistency():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    wf = yaml.safe_load((ROOT / ".github/workflows/docker-image.yml").read_text())
    image = compose["services"]["searchhub"]["image"]
    assert image.startswith("ghcr.io/") and image.endswith("/searchhub:latest")
    # 工作流最终输出 tags 含 :latest（main 与 tag 分支均含）
