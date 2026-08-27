# SearchHub hermes 插件

SearchHub 聚合服务的 hermes-agent 原生后端（Route A：顶替内置 web_search / web_extract）。

## 安装

```bash
mkdir -p ~/.hermes/plugins/web/searchhub
cp plugin.yaml provider.py __init__.py ~/.hermes/plugins/web/searchhub/
# 或在仓库内直接软链：ln -s $(pwd) ~/.hermes/plugins/web/searchhub
hermes plugins list        # 应看到 web-searchhub
hermes plugins enable web-searchhub   # 用户插件默认不加载，需显式启用
# 等价做法：hermes config set plugins.enabled '["web-searchhub"]'
```

> 注意：插件目录必须有 `__init__.py`（含 `register(ctx)` 导出），
> 缺失会导致加载器直接抛 `FileNotFoundError`（hermes_cli/plugins.py）。

## 配置

凭据放 `~/.hermes/.env`（插件用 get_provider_env 读取，进程 env 优先）：

```
SEARCHHUB_URL=http://<nas>:8000
SEARCHHUB_TOKEN=<管理后台「调用方 Token」页创建的 token>
```

指向 SearchHub 并启用：

```bash
hermes config set web.backend searchhub
hermes config set web.search_backend searchhub
hermes config set web.extract_backend searchhub
# 修改后 /reset 或重启生效
```

## 验证

- `hermes tools` 的 Web Search/Extract 选择器应出现 SearchHub
- 直接调用 `web_search` 与 `web_extract` 各一次，确认返回契约形状
- 拔掉 SearchHub 服务 → 错误信息应指明连接失败

## 说明

- `is_available()` 不联网（仅查 URL/TOKEN 是否配置）
- 响应由 SearchHub 位对位透传（`data.web[].title/url/description/position`；extract 的 `data[].url/title/content/raw_content/metadata`）
