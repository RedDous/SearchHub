# SearchHub M4A-followup：登录后强提示改密 + 零配置部署实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保留现有首次启动密码逻辑（ADMIN_PASSWORD 环境变量或默认 admin），登录后强提示修改默认密码；将 docker-compose 的 ADMIN_PASSWORD 守卫从必填改为可选，使 `.env` 对普通用户完全可选（零配置部署）。

**Architecture:** 后端 `GET /api/admin/config` 响应新增派生字段 `password_is_default`（`config.verify_admin_password("admin")`，即当前密码是否仍为默认值）；前端登录成功后检查该字段，为 true 时弹出不可跳过的改密弹窗（复用 change-password 接口）；compose 守卫 `:?` 改 `:-admin`；README 更新首次登录流程。

**Tech Stack:** 现有 FastAPI/Vue3 栈；无新依赖。

## Global Constraints

- 保留现有首次启动逻辑：`ADMIN_PASSWORD` env 优先，否则默认 `admin`（不改 lifespan、不删默认值）
- `password_is_default` 仅在后端计算（`verify_admin_password("admin")`），前端不自行比较哈希；响应 JSON 新增字段，已有字段不变
- 改密弹窗：老密码/新密码/确认；新密码 >= 8 位且两次一致；成功即关闭并刷新；不可跳过（无"稍后"按钮）；失败展示错误
- compose：`${ADMIN_PASSWORD:-admin}`（可选；未设 .env 也能 `up -d`）
- `.env.example` 改为注释说明（全部可选项）；README 部署章节更新首次登录流程
- 提交风格 `feat:`/`fix:`/`chore:`；pytest 164 + vitest 17 保持全绿（新增测试计入）

## File Structure

```
src/searchhub/api/admin/config_routes.py   # + password_is_default
frontend/src/api/admin.ts                  # + AppConfigView 类型扩展
frontend/src/views/LoginView.vue           # 登录成功后检查并跳转
frontend/src/views/SystemView.vue          # 首启改密弹窗（或独立组件）
frontend/src/i18n/index.ts                 # + setup.* 键（zh/en）
docker-compose.yml                         # 守卫改可选
.env.example                               # 注释化
README.md                                  # 首次登录流程
tests/api/admin/test_config_routes.py      # + password_is_default 断言
tests/test_compose.py                      # 守卫断言更新
frontend/tests/auth-store.test.ts          # + 登录后检查逻辑
```

---

### Task 1: 后端 password_is_default + compose 可选项

**Files:**
- Modify: `src/searchhub/api/admin/config_routes.py`（`GET /config` 响应加 `password_is_default`）
- Modify: `docker-compose.yml`（`${ADMIN_PASSWORD:-admin}`）
- Modify: `.env.example`（注释化）
- Test: `tests/api/admin/test_config_routes.py`、`tests/test_compose.py`

**Interfaces:**
- Produces：`GET /api/admin/config` 响应 `data` 新增顶层字段 `password_is_default: bool`（在 `config_version`/`updated_at` 同级），计算方式：`svc.verify_admin_password("admin")`（ConfigService 已有该方法；空 hash 返回 False，默认 admin 命中返回 True）
- Produces：compose 第 12 行环境值：`ADMIN_PASSWORD: ${ADMIN_PASSWORD:-admin}`（无 .env 时默认 admin，配合前端强改密提示）

- [ ] **Step 1: 写失败测试**

`tests/api/admin/test_config_routes.py` 追加：
```python
def test_config_reports_default_password(admin_client, data_dir):
    # admin_client fixture 预设了 testpass123（非默认）→ password_is_default=False
    data = admin_client.get("/api/admin/config").json()["data"]
    assert data["password_is_default"] is False


def test_config_reports_default_password_when_default(admin_client, data_dir):
    from searchhub.config import ConfigService

    # 手动把密码重置为默认 admin 模拟未改密用户
    cs = ConfigService(data_dir)
    cs.load()
    cs.set_admin_password("admin")
    data = admin_client.get("/api/admin/config").json()["data"]
    assert data["password_is_default"] is True
```

`tests/test_compose.py` 修改 `test_searchhub_service_shape` 中 ADMIN_PASSWORD 断言：
```python
    assert svc["environment"]["ADMIN_PASSWORD"] == "${ADMIN_PASSWORD:-admin}"
    assert ":?" not in svc["environment"]["ADMIN_PASSWORD"]  # 已改为可选，不再强制
```
（保留 `:?` 断言改为断言 `:-admin` 可选语义）

- [ ] **Step 2: 运行确认失败**

Run: `.venv/bin/pytest tests/api/admin/test_config_routes.py tests/test_compose.py -v`
Expected: FAIL（字段缺失 / 断言不匹配）

- [ ] **Step 3: 实现后端字段**

`src/searchhub/api/admin/config_routes.py` 的 `get_config` 响应构造处追加：
```python
    return {"success": True, "data": {"config": data,
                                      "config_version": svc.config_version,
                                      "updated_at": svc.updated_at,
                                      "password_is_default": svc.verify_admin_password("admin")}}
```

- [ ] **Step 4: 更新 compose 与 .env.example**

`docker-compose.yml` 环境值改为 `ADMIN_PASSWORD: ${ADMIN_PASSWORD:-admin}`。

`.env.example` 改为（注释化，全部可选项）:
```
# 本文件全部为可选项——不创建 .env 也可直接 `docker compose up -d`。
# 首次登录默认账号 admin / admin，登录后系统会强制要求修改密码。
# 如希望首次密码即为指定值，取消下面注释并修改：
# ADMIN_PASSWORD=my_strong_password
# 启用 searxng sidecar 时可自定义其签名密钥（默认 please_change_me）：
# SEARXNG_SECRET=please_change_me
```

- [ ] **Step 5: 运行确认通过 + 全量回归**

Run: `.venv/bin/pytest tests/api/admin/test_config_routes.py tests/test_compose.py -v && .venv/bin/pytest -q`
Expected: 通过；全量 166 全绿（164 + 2 新增）

- [ ] **Step 6: 提交**

```bash
git add src/searchhub/api/admin/config_routes.py docker-compose.yml .env.example tests/api/admin/test_config_routes.py tests/test_compose.py
git commit -m "feat: report default-password state in config; make compose ADMIN_PASSWORD optional"
```

---

### Task 2: 前端强提示改密 + README

**Files:**
- Modify: `frontend/src/api/admin.ts`（`AppConfigView` 类型加 `password_is_default: boolean`）
- Modify: `frontend/src/views/LoginView.vue`（登录成功后备查 config；为默认密码时跳转系统设置页并弹强改弹窗）
- Modify: `frontend/src/views/SystemView.vue`（新增首启强改密码弹窗逻辑，或抽取为 `frontend/src/components/ForcePasswordDialog.vue`）
- Modify: `frontend/src/i18n/index.ts`（`setup.*` 键 zh/en）
- Modify: `README.md`（首次登录流程）
- Test: `frontend/tests/auth-store.test.ts`（登录后默认密码检查逻辑，若可测）

**Interfaces:**
- Produces：登录成功后：`await adminApi.getConfig()` → `data.password_is_default === true` → 跳转 `{ name: 'system' }` 并打开改密弹窗
- Produces 改密弹窗（`ForcePasswordDialog`）：modal 含 3 输入（老/新/确认）+ 确定/取消；新密码 <8 或两次不一致前端拦截；提交调 `changePassword` 成功后关闭并刷新 config（此时 password_is_default 应变 false）；无"稍后"跳过按钮
- Produces i18n 键：`setup.forceChangeTitle`（zh "请修改默认密码" / en "Change the default password"）、`setup.forceChangeDesc`（zh "您正在使用默认密码，出于安全考虑请立即修改。" / en "You are using the default password. Please change it now."）、复用现有 `system.oldPassword`/`system.newPassword`/`system.confirmPassword`/`system.passwordMismatch`/`system.passwordTooShort`/`system.passwordChanged`
- 说明：登录接口本身不含该字段，需登录后额外一次 `getConfig()`（已有该调用点可复用——若 LoginView 已有加载 config 的逻辑则在其结果上判断）

- [ ] **Step 1: 实现类型与弹窗组件**

按 Interfaces 实现；弹窗组件关键逻辑参考：
```ts
const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void; (e: 'changed'): void }>()
const auth = useAuthStore()
const message = useMessage()
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const submitting = ref(false)

async function submit() {
  if (newPassword.value.length < 8) { message.error(t('system.passwordTooShort')); return }
  if (newPassword.value !== confirmPassword.value) { message.error(t('system.passwordMismatch')); return }
  submitting.value = true
  try {
    await auth.changePassword(oldPassword.value, newPassword.value)
    message.success(t('system.passwordChanged'))
    oldPassword.value = newPassword.value = confirmPassword.value = ''
    emit('update:open', false)
    emit('changed')
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('common.failed'))
  } finally {
    submitting.value = false
  }
}
```

- [ ] **Step 2: 接入 LoginView 与 SystemView**

LoginView 登录成功后：`const cfg = await adminApi.getConfig(); if (cfg.password_is_default) { router.push({ name: 'system' }); await nextTick() }`（SystemView 挂载时根据 config 判断打开弹窗——避免依赖路由参数传递）。SystemView 在 config 加载后 `password_is_default===true` 且尚未显示过时打开弹窗（用模块级 flag 防止刷新循环：弹窗关闭后不再自动重开，除非手动触发）。

- [ ] **Step 3: README 更新**

README 部署章节步骤 4 修改为：
```
4. 打开 http://<NAS-IP>:8000，首次登录使用默认账号 admin / admin（或 .env 中设置的 ADMIN_PASSWORD），登录后系统会强制要求修改密码
```

- [ ] **Step 4: 验证**

Run: `cd frontend && npm run build && npm test`
Expected: 类型检查 + build 通过；vitest 全绿（17 + 新增）

- [ ] **Step 5: 提交**

```bash
git add frontend/src README.md frontend/tests
git commit -m "feat(web): force password change after login with default credentials; docs"
```

---

## Self-Review

- **Spec 覆盖**：保留现有密码逻辑 ✓；登录后提示改密（不可跳过）→ Task 2；compose 守卫可选项 → Task 1；.env 完全可选 → Task 1；README 首次登录流程 → Task 2。
- **占位符扫描**：无 TBD；Task 1 实现完整；Task 2 的关键弹窗逻辑代码完整。
- **类型一致性**：`password_is_default` 在后端响应、前端 `AppConfigView` 类型、测试断言三处一致；`verify_admin_password("admin")` 复现默认密码判断（与 lifespan 的默认 admin 逻辑一致）。
- 已知取舍：默认密码"admin"的检测假设用户名仍是 admin（若用户改了用户名则该字段恒为 False，不再提示——可接受）；强改弹窗关闭后不再自动重开（防止循环骚扰）。