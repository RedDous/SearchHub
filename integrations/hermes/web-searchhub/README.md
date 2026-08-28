# SearchHub hermes 插件

SearchHub 聚合服务的 hermes-agent 原生后端（Route A：顶替内置 web_search / web_extract）。

## 安装

获取三个文件（`plugin.yaml` / `provider.py` / `__init__.py`），二选一：

- **hermes 与 SearchHub 仓库在同一台机器**：直接用仓库内文件
  ```bash
  cp integrations/hermes/web-searchhub/{plugin.yaml,provider.py,__init__.py} ~/.hermes/plugins/web/searchhub/
  # 或软链整个目录：ln -s $(pwd)/integrations/hermes/web-searchhub ~/.hermes/plugins/web/searchhub
  ```
- **hermes 在别的机器（如 NAS 之外的电脑）**：从 GitHub 下载
  ```bash
  mkdir -p ~/.hermes/plugins/web/searchhub && cd ~/.hermes/plugins/web/searchhub
  curl -fsSLO https://raw.githubusercontent.com/RedDous/SearchHub/main/integrations/hermes/web-searchhub/plugin.yaml
  curl -fsSLO https://raw.githubusercontent.com/RedDous/SearchHub/main/integrations/hermes/web-searchhub/provider.py
  curl -fsSLO https://raw.githubusercontent.com/RedDous/SearchHub/main/integrations/hermes/web-searchhub/__init__.py
  ```

然后启用：

```bash
hermes plugins list        # 应看到 web-searchhub
hermes plugins enable web-searchhub   # 用户插件默认不加载，需显式启用
# 等价做法：hermes config set plugins.enabled '["web-searchhub"]'
```

> 注意：插件目录必须有 `__init__.py`（含 `register(ctx)` 导出），
> 缺失会导致加载器直接抛 `FileNotFoundError`（hermes_cli/plugins.py）。
>
> `hermes plugins enable` 时会询问 "Allow this plugin to replace built-in
> tools (e.g. shell_exec, write_file)?"——请选 **No**。该弹窗针对的是
> 替换内置工具的插件（如 shell_exec/write_file 覆盖）；本插件只注册
> web 搜索后端，不替换任何内置工具，授权纯属多余特权。

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
- **search**：SearchHub 的 `{success, data:{web:[…]}}` 信封位对位透传
- **extract**：按 hermes 契约拆包为"每条 URL 一个 dict"的列表
  （`{url, title, content, raw_content, metadata, error}`）；服务端整体
  失败或不可达时同样返回逐条 error 项，避免 hermes 把信封当列表迭代
  （曾导致 `'str' object has no attribute 'get'`）
