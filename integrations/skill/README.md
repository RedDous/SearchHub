# SearchHub Agent Skill 安装

将 `searchhub-web/` 目录复制到对应 agent 的 skills 目录即可：

- **opencode**: `~/.config/opencode/skills/`（全局）或项目 `.opencode/skills/`（项目级）
- **Claude Code**: `~/.claude/skills/`
- **Codex**: `~/.codex/skills/`

```bash
cp -r searchhub-web ~/.config/opencode/skills/
# 或
cp -r searchhub-web ~/.claude/skills/
# 或
cp -r searchhub-web ~/.codex/skills/
```

使用前配置 `SEARCHHUB_URL`（如 `http://192.168.1.10:8000`）与 `SEARCHHUB_TOKEN`（管理后台「调用方 Token」页创建）。