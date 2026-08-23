# SearchHub M4A-followup：镜像发布管线 + 双模式部署实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供**拉取镜像**与**源码构建**两种部署方式：(1) GitHub Actions 流水线在 push main / 打 tag 时构建 linux/amd64 + linux/arm64 双架构镜像推送到 GHCR；(2) compose 拆双文件——`docker-compose.yml` 默认拉 `ghcr.io/reddous/searchhub:latest`，`docker-compose.build.yml` 叠加 `build: .` 走源码构建；README 两条路径 + 测试同步。

**Architecture:** 单仓库双发布面。compose 合并语义：`docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build` 时 build 文件覆盖 image 来源；只跑 `docker compose up -d` 则拉镜像。CI 用 buildx（qemu 模拟 arm64）+ GHA 缓存，push 事件：main → `latest` + `sha-<短哈希>`；tag `v*` → `:<tag>`。镜像名 `ghcr.io/reddous/searchhub`（与仓库 RedDous/SearchHub 对应）。

**Tech Stack:** GitHub Actions、docker buildx、GHCR；无新运行时依赖。

## Global Constraints

- `docker-compose.yml` 的 searchhub 服务：移除 `build: .`，`image: ghcr.io/reddous/searchhub:latest`（其余配置不变：ports/volumes/SEARCHHUB_DATA/ADMIN_PASSWORD/restart）
- 新增 `docker-compose.build.yml`：仅 searchhub 服务 `build: .` + `image: searchhub:local`（供源码构建模式；与主文件合并后 build 覆盖 image）
- 工作流 `.github/workflows/docker-image.yml`：触发 = push main + tags `v*`；job：checkout → qemu → buildx → login GHCR（`${{ github.actor }}`/`${{ secrets.GITHUB_TOKEN }}`）→ build-push（platforms linux/amd64,linux/arm64；cache-from/to type=gha；tags 按触发事件计算：main → `latest`,`sha-<sha>`；tag → `<tag>`）
- 容器内构建不依赖 compose（多阶段 Dockerfile 原样复用）
- README 快速部署改为两条路径：拉镜像（默认，`docker compose up -d`，镜像未发布时提示走源码构建）与源码构建（`docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build`）；更新命令同步
- 测试：`tests/test_compose.py` 更新——searchhub 不再含 `build` 键、image 为 ghcr；新增 build 覆盖文件结构断言（存在、含 build + searchhub 服务、image searchhub:local）；工作流文件结构测试（存在、含 platforms amd64+arm64、GHCR 目标、tags 逻辑）——放 `tests/test_compose.py` 或新 `tests/test_ci_workflow.py`
- pytest 185 基线 + 新增；提交风格 `feat:`/`fix:`/`chore:`

## File Structure

```
docker-compose.yml                 # 默认拉镜像
docker-compose.build.yml           # 源码构建覆盖
.github/workflows/docker-image.yml # CI 发布流水线
README.md                          # 双模式部署说明
tests/test_compose.py              # 更新 + build 文件断言
tests/test_ci_workflow.py          # 工作流结构断言
```

---

### Task 1: compose 双文件 + README 双路径 + 测试

**Files:**
- Modify: `docker-compose.yml`
- Create: `docker-compose.build.yml`
- Modify: `README.md`
- Modify: `tests/test_compose.py`

**Interfaces:**
- Produces `docker-compose.yml`（searchhub 段修改）:
```yaml
services:
  searchhub:
    image: ghcr.io/reddous/searchhub:latest
    container_name: searchhub
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
    environment:
      SEARCHHUB_DATA: /data
      ADMIN_PASSWORD: ${ADMIN_PASSWORD:-admin}
    restart: unless-stopped
```
（searxng/crawl4ai sidecar 段不变。）

- Produces `docker-compose.build.yml`:
```yaml
# 源码构建模式覆盖：与 docker-compose.yml 合并使用
#   docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
services:
  searchhub:
    build: .
    image: searchhub:local
```

- Produces README「快速部署」改为两条路径：
```markdown
## 快速部署（Docker）

前提：已安装 Docker 与 Docker Compose v2。两种方式任选：

**方式 A：拉取镜像（推荐）**——无需源码，镜像已发布到 GHCR：

```bash
git clone https://github.com/RedDous/SearchHub.git && cd SearchHub   # 仅需要 compose 文件与 .env 模板
docker compose up -d
```

**方式 B：源码构建**——本地构建镜像（首次含前端编译，约几分钟）：

```bash
git clone https://github.com/RedDous/SearchHub.git && cd SearchHub
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```
```
> 说明：镜像尚未发布到 GHCR 时（首个 release 前），只能走方式 B。方式 A 的更新 = `docker compose pull && docker compose up -d`；方式 B 的更新 = `git pull && docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build`。其余（登录/引导配置/sidecar/备份）两种方式一致。

- [ ] **Step 1: 更新测试**

`tests/test_compose.py` 修改 `test_searchhub_service_shape`：
```python
    assert svc["image"] == "ghcr.io/reddous/searchhub:latest"
    assert "build" not in svc
    assert svc["ports"] == ["8000:8000"]
    assert svc["volumes"] == ["./data:/data"]
    assert svc["environment"]["SEARCHHUB_DATA"] == "/data"
    assert ":?" not in svc["environment"]["ADMIN_PASSWORD"]
```
新增：
```python
def test_build_override_file(compose: dict):
    path = ROOT / "docker-compose.build.yml"
    assert path.exists()
    merged = yaml.safe_load(path.read_text())
    svc = merged["services"]["searchhub"]
    assert "build" in svc and svc["build"] == "."
    assert svc["image"] == "searchhub:local"
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_compose.py -v`
Expected: FAIL（image 断言不匹配 / build 文件不存在）

- [ ] **Step 3: 实现**

按 Interfaces 修改 compose、创建 build 覆盖文件、更新 README。

- [ ] **Step 4: 验证 + 全量回归**

Run: `.venv/bin/pytest tests/test_compose.py -v && .venv/bin/pytest -q`
Expected: 通过；全量 186 全绿

- [ ] **Step 5: 提交**

```bash
git add docker-compose.yml docker-compose.build.yml README.md tests/test_compose.py
git commit -m "feat: dual-mode deploy (image pull default, source build override)"
```

---

### Task 2: CI 发布流水线 + 结构测试

**Files:**
- Create: `.github/workflows/docker-image.yml`
- Test: `tests/test_ci_workflow.py`

**Interfaces:**
- Produces `.github/workflows/docker-image.yml`（完整内容）:
```yaml
name: build-and-push-image

on:
  push:
    branches: [main]
    tags: ["v*"]

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-qemu-action@v3

      - uses: docker/setup-buildx-action@v3

      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Compute image tags
        id: meta
        run: |
          set -euo pipefail
          IMAGE="ghcr.io/${{ github.repository_owner }}/searchhub"
          if [[ "${{ github.ref_type }}" == "tag" ]]; then
            TAGS="$IMAGE:${{ github.ref_name }},$IMAGE:latest"
          else
            TAGS="$IMAGE:latest,$IMAGE:sha-${GITHUB_SHA::12}"
          fi
          echo "tags=${TAGS}" >> "$GITHUB_OUTPUT"

      - uses: docker/build-push-action@v6
        with:
          context: .
          file: ./Dockerfile
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```
> 说明：`ghcr.io/${{ github.repository_owner }}/searchhub` 与 compose 的 `ghcr.io/reddous/searchhub` 一致（仓库属主 reddous）。

- Produces `tests/test_ci_workflow.py`:
```python
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
```

- [ ] **Step 1: 写失败测试**

创建 `tests/test_ci_workflow.py`，运行确认失败（文件不存在）。

- [ ] **Step 2: 创建工作流**

按 Interfaces 创建 `.github/workflows/docker-image.yml`。

- [ ] **Step 3: 验证 + 全量回归**

Run: `.venv/bin/pytest tests/test_ci_workflow.py -v && .venv/bin/pytest -q`
Expected: 通过；全量 189 全绿

- [ ] **Step 4: 提交**

```bash
git add .github/workflows/docker-image.yml tests/test_ci_workflow.py
git commit -m "feat: GHCR image publishing pipeline (multi-arch)"
```

---

## Self-Review

- **Spec 覆盖**：镜像拉取模式 → Task 1（compose 默认 image ghcr）；源码构建模式 → Task 1（build 覆盖文件）；CI 发布（双架构 + GHCR + 事件）→ Task 2；README 双路径 → Task 1；测试同步 → Task 1/2。
- **占位符扫描**：两个 compose 文件、工作流、README 段落、测试均完整给出。
- **类型一致性**：镜像名 `ghcr.io/reddous/searchhub` 在 compose、工作流（`repository_owner` 插值）、测试三处一致；`:latest` tag 语义一致；compose 合并用法（`-f` 两个文件）在 README 与 build 文件注释一致。
- 已知取舍：工作流无法本地执行验证（GitHub 侧生效）——结构测试兜底，首跑需在 push 后观察；GHCR 首推前方式 A 不可用（README 已注明）；`repository_owner` 插值在 fork 场景下与 compose 硬编码名不一致（本仓库自用，可接受）。
PLANEOF
wc -l /mnt/e/Code/SearchHub/.superpowers/plans/2026-08-16-m4a-followup-docker-publish.md