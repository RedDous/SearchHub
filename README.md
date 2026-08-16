# SearchHub

自托管统一 Web 搜索 / 网页提取聚合服务（M1：核心引擎 + REST API）。

## 快速开始

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
SEARCHHUB_DATA=./data .venv/bin/python -m searchhub
```

首次启动自动生成 `data/config.yaml` 与 `data/secrets.env`。

## 配置示例

`data/secrets.env`（密钥，权限 600）：
```
EXA_KEY_1=xxx
TAVILY_KEY_1=yyy
```

`data/config.yaml` 添加供应商：
```yaml
providers:
  - id: exa
    capabilities: [search, extract]
    enabled: true
    weight: 10
  - id: ddg
    capabilities: [search]
    enabled: true
  - id: trafilatura
    capabilities: [extract]
    enabled: true
```

## API

所有 `/v1/*` 接口需 `Authorization: Bearer <token>`；token 以 sha256 哈希加入 config.yaml：

```yaml
auth:
  tokens:
    - name: my-agent
      token_hash: <sha256(token)>
```

- `GET /v1/search?q=...&limit=5` 或 `POST /v1/search {"q": ...}`
- `GET /v1/extract?urls=a,b` 或 `POST /v1/extract {"urls": [...]}`
- `GET /v1/providers`
- `GET /healthz` / `GET /readyz`

生成 token 哈希：`python -c "import hashlib; print(hashlib.sha256(b'YOUR_TOKEN').hexdigest())"`

## 测试

```bash
.venv/bin/pytest
```
