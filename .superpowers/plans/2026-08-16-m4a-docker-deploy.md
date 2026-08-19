# SearchHub M4A：Docker 打包与一键部署实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付 SearchHub 的 Docker 化部署：多阶段 Dockerfile（node 构建前端 → python slim 运行）、docker-compose.yml（主服务 + 可选 searxng/crawl4ai sidecar profiles）、.env.example、.dockerignore、README NAS 部署指南。NAS 上 `docker compose up -d` 即可运行，零环境依赖。

**Architecture:** 多阶段构建。阶段 1：`node:22-alpine` 执行 `npm ci && npm run build` 产出 `frontend/dist`；阶段 2：`python:3.13-slim` 安装包（`pip install .`，src 布局）+ `COPY --from=builder` 前端产物到 `/app/web/dist`，`ENV SEARCHHUB_WEB_DIST=/app/web/dist`（避免非 editable 安装后 `__file__` 路径推导失效），`HEALTHCHECK` 用 python urllib 探 `/healthz`，`CMD python -m searchhub`。compose：`searchhub` 服务映射 8000、挂载 `./data:/data`（备份即拷目录）、`ADMIN_PASSWORD` 从 `.env` 注入；`sidecars` profile 提供 searxng（8080）与 crawl4ai（11235），compose 网络内以服务名互访。本机无 docker——验证以结构测试（pytest 静态断言 compose/Dockerfile 关键内容）+ 人工审查为主，真构建在 NAS 上按 README 验收清单执行。

**Tech Stack:** Dockerfile 多阶段（node:22-alpine / python:3.13-slim）、docker compose v2、PyYAML（结构测试）。

## Global Constraints

- Dockerfile 阶段：builder = `node:22-alpine`，runtime = `python:3.13-slim`（固定 tag，不用 latest）
- runtime 必须设置 `ENV SEARCHHUB_WEB_DIST=/app/web/dist`；`WORKDIR /app`；`EXPOSE 8000`；`HEALTHCHECK`（python urllib 探 http://127.0.0.1:8000/healthz，timeout 3s，间隔 30s）；`CMD ["python", "-m", "searchhub"]`
- 构建：builder 内 `npm ci && npm run build`（`frontend/package-lock.json` 已提交）；runtime 内 `pip install . --no-cache-dir`（pyproject 的 src 布局；setuptools>=68 已满足）
- compose 服务 `searchhub`：`build: .`、`ports: "8000:8000"`、`volumes: ./data:/data`、`environment: ADMIN_PASSWORD=${ADMIN_PASSWORD:?set ADMIN_PASSWORD in .env}`（缺失即报错，防默认密码裸奔）、`restart: unless-stopped`
- sidecar 服务（`profiles: ["sidecars"]`）：`searxng`（image searxng/searxng:latest，ports 8080:8080，环境 SEARXNG_BASE_URL）、`crawl4ai`（image unclecode/crawl4ai:latest，ports 11235:11235）
- `.env.example` 含 `ADMIN_PASSWORD=` 与 `SEARXNG_SECRET=`（SEARCHHUB_PORT 由 compose 固定 8000:8000）
- `.dockerignore`：`.git`、`.venv`、`data`、`frontend/node_modules`、`frontend/dist`、`tests`、`tmp`、`.superpowers`、`docs`（docs 不进镜像）
- `.gitignore` 追加 `data/`（本地运行产生的数据目录不入库）
- 提交风格 `feat:`/`fix:`/`chore:`；现有 pytest 154 + vitest 17 必须保持全绿（本里程碑不改后端逻辑代码，仅新增部署文件与结构测试）

## File Structure

```
Dockerfile
.dockerignore
docker-compose.yml
.env.example
.gitignore                       # + data/
README.md                        # + 部署章节
tests/
  test_dockerfile.py             # Dockerfile 结构断言
  test_compose.py                # compose 结构断言
```

---

### Task 1: Dockerfile + .dockerignore

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Modify: `.gitignore`（追加 `data/`）
- Test: `tests/test_dockerfile.py`

**Interfaces:**
- Produces `Dockerfile`（完整内容）:
```dockerfile
# ---- builder: 构建前端 ----
FROM node:22-alpine AS builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- runtime: 运行后端 ----
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SEARCHHUB_WEB_DIST=/app/web/dist \
    SEARCHHUB_HOST=0.0.0.0 \
    SEARCHHUB_PORT=8000
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install . --no-cache-dir
COPY --from=builder /build/frontend/dist /app/web/dist
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"]
CMD ["python", "-m", "searchhub"]
```
> 说明：`pip install .` 在 src 布局下构建 wheel；`COPY pyproject.toml README.md ./` 是 setuptools 构建所需（README 作为长描述；若构建报缺文件，把缺失文件也 COPY 进去并记录偏差）。`SEARCHHUB_WEB_DIST` 指向镜像内前端产物（非 editable 安装后 `__file__` 推导的 parents[3] 不再等于仓库根，必须显式指定）。

- Produces `.dockerignore`:
```
.git
.venv
data
tmp
docs
.superpowers
frontend/node_modules
frontend/dist
tests
*.md.bak*
```

- `.gitignore` 追加：
```
# 本地运行数据
data/
```

- [ ] **Step 1: 写失败测试**

`tests/test_dockerfile.py`:
```python
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
    assert "COPY --from=builder /build/frontend/dist /app/web/dist" in dockerfile
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
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_dockerfile.py -v`
Expected: FAIL（Dockerfile/.dockerignore 不存在）

- [ ] **Step 3: 创建文件**

按 Interfaces 创建 `Dockerfile`、`.dockerignore`，修改 `.gitignore`。

- [ ] **Step 4: 运行确认通过 + 全量回归**

Run: `.venv/bin/pytest tests/test_dockerfile.py -v && .venv/bin/pytest -q`
Expected: 6 passed；全量 160 全绿（154 + 6）

- [ ] **Step 5: 提交**

```bash
git add Dockerfile .dockerignore .gitignore tests/test_dockerfile.py
git commit -m "feat: multi-stage Dockerfile with bundled frontend build"
```

---

### Task 2: docker-compose.yml + .env.example

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Test: `tests/test_compose.py`

**Interfaces:**
- Produces `docker-compose.yml`（完整内容）:
```yaml
services:
  searchhub:
    build: .
    image: searchhub:latest
    container_name: searchhub
    ports:
      - "8000:8000"
    volumes:
      - ./data:/data
    environment:
      ADMIN_PASSWORD: ${ADMIN_PASSWORD:?请在 .env 中设置 ADMIN_PASSWORD}
    restart: unless-stopped

  searxng:
    image: searxng/searxng:latest
    container_name: searchhub-searxng
    profiles: ["sidecars"]
    ports:
      - "8080:8080"
    environment:
      SEARXNG_BASE_URL: http://127.0.0.1:8080/
      SEARXNG_SECRET: ${SEARXNG_SECRET:-please_change_me}
    restart: unless-stopped

  crawl4ai:
    image: unclecode/crawl4ai:latest
    container_name: searchhub-crawl4ai
    profiles: ["sidecars"]
    ports:
      - "11235:11235"
    restart: unless-stopped
```
> 说明：`${ADMIN_PASSWORD:?...}` 未设置时 compose 直接报错退出（防默认密码）；sidecar 用 profile 默认不启动，`docker compose --profile sidecars up -d` 才拉起。compose 网络内主服务用 `http://searxng:8080` / `http://crawl4ai:11235` 访问 sidecar（README 说明）。

- Produces `.env.example`:
```
# 复制为 .env 并修改
ADMIN_PASSWORD=change_me_strong_password
SEARXNG_SECRET=please_change_me
```

- [ ] **Step 1: 写失败测试**

`tests/test_compose.py`:
```python
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def compose() -> dict:
    path = ROOT / "docker-compose.yml"
    assert path.exists(), "docker-compose.yml missing"
    return yaml.safe_load(path.read_text())


def test_searchhub_service_shape(compose: dict):
    svc = compose["services"]["searchhub"]
    assert svc["ports"] == ["8000:8000"]
    assert svc["volumes"] == ["./data:/data"]
    assert "ADMIN_PASSWORD" in svc["environment"]["ADMIN_PASSWORD"]
    assert svc["restart"] == "unless-stopped"
    assert "build" in svc


def test_sidecar_profiles(compose: dict):
    assert compose["services"]["searxng"]["profiles"] == ["sidecars"]
    assert compose["services"]["crawl4ai"]["profiles"] == ["sidecars"]
    assert "8080:8080" in compose["services"]["searxng"]["ports"]
    assert "11235:11235" in compose["services"]["crawl4ai"]["ports"]


def test_sidecars_are_opt_in(compose: dict):
    # 默认 up 不应拉起 sidecar：它们必须都在 profile 里
    for name in ("searxng", "crawl4ai"):
        assert compose["services"][name].get("profiles"), f"{name} missing profiles"


def test_env_example_exists_and_has_required_keys():
    env = (ROOT / ".env.example").read_text()
    assert "ADMIN_PASSWORD=" in env
    assert "SEARXNG_SECRET=" in env
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/test_compose.py -v`
Expected: FAIL（文件不存在）

- [ ] **Step 3: 创建文件**

按 Interfaces 创建 `docker-compose.yml`、`.env.example`。

- [ ] **Step 4: 运行确认通过 + 全量回归**

Run: `.venv/bin/pytest tests/test_compose.py -v && .venv/bin/pytest -q`
Expected: 4 passed；全量 164 全绿

- [ ] **Step 5: 提交**

```bash
git add docker-compose.yml .env.example tests/test_compose.py
git commit -m "feat: docker compose with optional sidecar profiles"
```

---

### Task 3: README 部署章节

**Files:**
- Modify: `README.md`

**Interfaces:**
- Produces README「Docker 部署（M4）」章节（插在「快速开始」之后）：
  - NAS 前提：Docker + Docker Compose v2
  - 步骤：
    1. `git clone https://github.com/RedDous/SearchHub.git && cd SearchHub`
    2. `cp .env.example .env` 并设置 `ADMIN_PASSWORD`
    3. `docker compose up -d --build`（首次构建含前端编译，约几分钟）
    4. 打开 `http://<NAS-IP>:8000`，用 `.env` 里的 ADMIN_PASSWORD 登录（用户名 admin）
    5. 可选 sidecar：`docker compose --profile sidecars up -d`，然后在管理后台添加 searxng 供应商（base_url `http://searxng:8080`）与 crawl4ai（base_url `http://crawl4ai:11235`）
  - 数据与备份：全部数据在 `./data/`（config.yaml、secrets.env、history.db、cache.db、session_secret），备份 = 拷贝整个目录；恢复 = 拷贝回去重启
  - 更新：`git pull && docker compose up -d --build`
  - 说明：镜像内以 root 运行（NAS 家用场景简化；如需非 root 可在 compose 加 `user:`）；`SEARCHHUB_WEB_DIST` 已内置于镜像
- 冒烟（本机无 docker 时的替代验证）：`python -c "import yaml; yaml.safe_load(open('docker-compose.yml'))"` 通过 + 结构测试已覆盖

- [ ] **Step 1: 写 README 章节**

按 Interfaces 追加。

- [ ] **Step 2: 全量回归**

Run: `.venv/bin/pytest -q && cd frontend && npm test`
Expected: 164 全绿 + vitest 17 全绿

- [ ] **Step 3: 提交**

```bash
git add README.md
git commit -m "docs: NAS Docker deployment guide"
```

---

## Self-Review

- **Spec 覆盖**（设计文档 §六 部署）：多阶段 Dockerfile（node 构建 + python slim）→ Task 1；docker-compose + /data 卷 → Task 2；sidecar profiles（searxng/crawl4ai）→ Task 2；ADMIN_PASSWORD env → Task 2；README NAS 部署 → Task 3。PUBLIC_BASE_URL 目前无代码消费，不在本里程碑实现（记录为后续项）。
- **占位符扫描**：无 TBD；Dockerfile/compose/.env.example 全文给出。
- **类型一致性**：compose 服务名（searchhub/searxng/crawl4ai）在测试与 README 中一致；`SEARCHHUB_WEB_DIST` 与 M2B 的 env 读取一致；`ADMIN_PASSWORD` 与 M2A 的 lifespan 首启逻辑一致。
- 已知取舍：本机无 docker，真构建验证放到 NAS（README 验收步骤）；镜像内 root 运行（家用 NAS 简化，compose 可覆盖）；sidecar 镜像 tag 用 latest（README 注明可自行固定版本）。
