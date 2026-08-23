# searchhub-dsh-web

SearchHub 在 dsh（DeepSeek Harness，dev-preview）`ctx.web` seam 下的供应商插件，提供 **search** 与 **fetch** 双能力：

- **web search** → SearchHub REST `/v1/search`（命中历史记录）
- **web fetch / extract** → SearchHub REST `/v1/extract`（正文提取）

## 安装

dsh 处于 dev-preview，插件安装机制以其当前版本为准。本插件不发布 npm，随 SearchHub 仓库分发，两种安装方式：

- **本地包安装**：`npm install <repo>/integrations/dsh/searchhub-web`（先在本目录 `npm run build`，产物在 `lib/`）
- **插件目录复制/链接**：将本目录（或 `lib/` 产物）复制/链接到 dsh 的插件目录

依赖：`@deepseek-ai/cordis`、`@deepseek-ai/dsh-web`、`@deepseek-ai/dsh-settings`、`@deepseek-ai/dsh-credentials`、`@deepseek-ai/dsh-launch-environment`（rc 版本，见 `package.json` peerDependencies）。

## 配置

插件名 `searchhub-dsh-web`，注入 `web`。三种配置方式，按优先级：

1. **设置段 UI**：注册 `searchhub-dsh-web` 设置段，字段 `baseURL`、`token`、`tokenEnv`；改动即时生效
2. **环境变量**：`SEARCHHUB_URL`（默认 `http://127.0.0.1:8000`）、`SEARCHHUB_TOKEN`（通过 `tokenEnv` 引用，默认值即 `SEARCHHUB_TOKEN`）；经凭据引用（`credentialRef`）与 launch environment 解析
3. **字面 token（config）**：插件配置里直接写 `token`，优先于凭据引用

## 验证

- 在 dsh 中发起 web search，结果应命中 SearchHub 历史记录；fetch 返回页面正文（markdown）
- 未配置 token 时，操作抛 `WebError('WEB_PROVIDER_ERROR')`，错误提示提示配置（token 值绝不进入错误信息或日志）
- provider 就绪判断：`isAvailable()` 要求 baseURL 可解析且 token 可达（字面 token 或 resolveToken 路径）

## 开发

```bash
npx vitest run   # provider 单测 + apply 接线测试
npm run build    # tsc → lib/（main: lib/index.js, types: lib/types/index.d.ts）
npx tsc --noEmit # 类型检查
```

注意：`tsconfig.json` 的 `include` 仅限 `src/`——测试不经 tsc 编译（vitest 直接运行 TS），构建产物不含 `lib/tests`。