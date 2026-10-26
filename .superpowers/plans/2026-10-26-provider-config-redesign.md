# Provider Configuration Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat provider schema and raw `options` JSON with a typed, schema-driven configuration model that supports per-provider fields, Jina self-hosting, per-capability testing, and a multi-instance-capable `type` / `id` model while keeping the v1 UI at one instance per type.

**Architecture:** `ProviderConfig` gains `type`; `ProviderSchema` gains `AuthSpec` / `EndpointSpec` / `FieldSpec` / `TestSpec`; each adapter declares a Pydantic options model and consumes it. Admin APIs validate options and test each capability; the frontend renders a dynamic form from FieldSpec and keeps one instance per type in v1.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, pytest / pytest-asyncio / respx; Vue 3, TypeScript, Naive UI, Pinia, Vitest.

**Spec:** `.superpowers/specs/2026-10-25-provider-config-redesign.md`

## Global Constraints

- Python >= 3.11; no new runtime dependencies.
- Existing `config.yaml` / `secrets.env` must keep working; missing `type` migrates to `type = id`.
- `options` models use `ConfigDict(extra="forbid")`; secrets never go in `config.yaml`.
- v1 UI: one instance per type; the backend must still support multiple instances.
- FieldSpec `label` / `help` are i18n keys; add both zh and en entries.
- Public `/v1/search` and `/v1/extract` response shapes stay unchanged.
- Run backend `pytest` and frontend `npm test`, `npm run typecheck`, `npm run build`.
- Commit after every task.

## Review Focus

1. **Legacy config without `type`**: an old `config.yaml` with only built-in IDs must load, migrate, and run without manual edits.
2. **Invalid options / unknown type on disk**: the app must still start; the affected provider is skipped or marked `invalid_config`, never crashing the process.
3. **Same-type multiple instances**: keys, test status, filtering, and fanout must use instance IDs correctly.
4. **Extract item-level errors**: a per-capability extract test must fail when `ExtractItem.error` is set, even if the list length is 1.
5. **Jina self-host base URL**: trailing slash and path joining must work; default remains `https://r.jina.ai/`.

Each line has a test in the owning task.

---

### Task 1: Provider type/id model and legacy migration

**Files:**
- Modify: `src/searchhub/config.py:44-53` (`ProviderConfig`)
- Modify: `src/searchhub/config.py:90-99` (`AppConfig`)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: existing `ProviderConfig`, `AppConfig`, `ConfigService`.
- Produces: `ProviderConfig.type: str`; missing `type` defaults to `id`; `AppConfig` rejects duplicate provider IDs.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
from pydantic import ValidationError

def test_provider_config_defaults_type_to_id():
    p = ProviderConfig(id="exa", capabilities=["search"])
    assert p.type == "exa"

def test_provider_config_allows_type_different_from_id():
    p = ProviderConfig(id="exa-work", type="exa", capabilities=["search"])
    assert p.type == "exa"

def test_legacy_config_without_type_loads(data_dir):
    (data_dir / "config.yaml").write_text(
        "providers:\n- id: ddg\n  capabilities: [search]\n"
    )
    cs = ConfigService(data_dir)
    cs.load()
    assert cs.get().providers[0].type == "ddg"

def test_duplicate_provider_ids_rejected():
    with pytest.raises(ValidationError):
        AppConfig(providers=[
            ProviderConfig(id="exa", type="exa", capabilities=["search"]),
            ProviderConfig(id="exa", type="exa", capabilities=["extract"]),
        ])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL because `ProviderConfig` has no `type`.

- [ ] **Step 3: Implement the model changes**

Add `type: str = ""` to `ProviderConfig` and a `model_validator(mode="after")` that sets `self.type = self.type or self.id`. Add an `AppConfig` `model_validator(mode="after")` that rejects duplicate `provider.id` values, and mirror that check in `ConfigService.save_config` because callers mutate the provider list after construction. Keep `model_dump()` output containing `type`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/searchhub/config.py tests/test_config.py
git commit -m "feat: add provider type/id model and legacy migration"
```

---

### Task 2: Schema primitives

**Files:**
- Modify: `src/searchhub/providers/schema.py`
- Test: `tests/test_provider_schemas.py`

**Interfaces:**
- Produces: `AuthSpec`, `EndpointSpec`, `FieldSpec`, `TestSpec`, `ProviderSchema`.
- `ProviderSchema` keeps the legacy fields (`requires_key`, `optional_key`, `requires_base_url`, `key_prefix`, `show_max_results`, `show_options`) temporarily, and adds `auth: AuthSpec | None = None`, `endpoint: EndpointSpec | None = None`, `fields`, `tests`. `__post_init__` syncs the legacy flags only when `auth` / `endpoint` are not `None`; this keeps un-migrated providers working.
- `validate_provider_config(provider_id, capabilities, base_url, schema)` keeps its current signature; it prefers `schema.auth` / `schema.endpoint` and falls back to legacy fields.
- The legacy fields are removed in Task 6 after all six providers migrate.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_provider_schemas.py
from dataclasses import asdict

from searchhub.providers.schema import (
    AuthSpec, EndpointSpec, FieldSpec, ProviderSchema, TestSpec,
)

def test_schema_derived_flags_and_asdict():
    s = ProviderSchema(
        type="demo",
        name="Demo",
        capabilities=("search",),
        auth=AuthSpec(mode="header", header_name="x-api-key", required=True, key_prefix="demo_"),
        endpoint=EndpointSpec(default="https://api.demo", overridable=True, required=True),
        fields=(FieldSpec(key="mode", label="providers.fields.demo.mode",
                          type="enum", choices=("a", "b"), default="a"),),
        tests=(TestSpec(capability="search", query="q"),),
    )
    assert s.requires_key is True
    assert s.requires_base_url is True
    assert s.key_prefix == "demo_"
    assert s.show_max_results is True
    assert asdict(s)["fields"][0]["key"] == "mode"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_provider_schemas.py::test_schema_derived_flags_and_asdict -v`
Expected: FAIL because the new dataclasses do not exist.

- [ ] **Step 3: Implement the dataclasses and compatibility properties**

Add the dataclasses from the spec. Extend `ProviderSchema` with `auth: AuthSpec | None = None`, `endpoint: EndpointSpec | None = None`, `fields`, and `tests` while keeping the legacy fields for compatibility. In `__post_init__`, when `auth` is not `None` set `requires_key`, `optional_key`, and `key_prefix`; when `endpoint` is not `None` set `requires_base_url`. `validate_provider_config` should prefer the new specs and fall back to the legacy fields. Do not remove the legacy fields in this task; Tasks 4-5 migrate the providers first.

- [ ] **Step 4: Run the schema tests**

Run: `pytest tests/test_provider_schemas.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/searchhub/providers/schema.py tests/test_provider_schemas.py
git commit -m "feat: add provider schema primitives"
```

---

### Task 3: Typed options models

**Files:**
- Create: `src/searchhub/providers/options.py`
- Test: `tests/providers/test_options.py`

**Interfaces:**
- Produces: `DdgOptions`, `SearxngOptions`, `ExaOptions`, `TavilyOptions`, `JinaOptions`, `TrafilaturaOptions`.
- Produces: `OPTIONS_MODELS: dict[str, type[BaseModel]]`.
- Produces: `options_model_for(provider_type: str) -> type[BaseModel] | None`.
- Produces: `validate_options(provider_type: str, raw: dict[str, Any]) -> dict[str, Any]`; unknown keys raise `pydantic.ValidationError`; returns a normalized full dict with defaults.

- [ ] **Step 1: Write the failing tests**

```python
# tests/providers/test_options.py
import pytest
from pydantic import ValidationError

from searchhub.providers.options import (
    ExaOptions, TrafilaturaOptions, options_model_for, validate_options,
)

def test_exa_options_defaults():
    assert ExaOptions().model_dump()["search_type"] == "auto"

def test_trafilatura_defaults_match_library():
    d = TrafilaturaOptions().model_dump()
    assert d["include_comments"] is True
    assert d["include_tables"] is True

def test_unknown_option_rejected():
    with pytest.raises(ValidationError):
        validate_options("exa", {"bogus": 1})

def test_validate_options_returns_defaults():
    assert validate_options("trafilatura", {})["include_comments"] is True

def test_unknown_type_returns_none():
    assert options_model_for("nope") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/providers/test_options.py -v`
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement the options models**

Use `ConfigDict(extra="forbid")` and the field/default table in the spec. Use `Field(default_factory=list)` for list fields. `validate_options` should return `model.model_dump()` so defaults are persisted and visible in the UI.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/providers/test_options.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/searchhub/providers/options.py tests/providers/test_options.py
git commit -m "feat: add typed provider options models"
```

---

### Task 4: Exa and Tavily schemas

**Files:**
- Modify: `src/searchhub/providers/exa.py`
- Modify: `src/searchhub/providers/tavily.py`
- Test: `tests/test_provider_schemas.py`

**Interfaces:**
- Produces: `ExaProvider.options_model = ExaOptions`, `TavilyProvider.options_model = TavilyOptions`.
- Produces: `schema.auth`, `schema.endpoint`, `schema.fields`, `schema.tests` per the spec.
- Field `label` / `help` values are i18n keys: `providers.fields.<type>.<key>` and `providers.fields.<type>.<key>.help`.

- [ ] **Step 1: Write the failing tests**

```python
def test_exa_schema():
    s = PROVIDER_CLASSES["exa"].schema
    assert s.auth.mode == "header"
    assert s.auth.header_name == "x-api-key"
    assert s.auth.required is True
    assert s.endpoint.default == "https://api.exa.ai"
    assert s.endpoint.overridable is False
    assert {f.key for f in s.fields} >= {
        "search_type", "category", "include_domains", "exclude_domains",
        "include_text", "include_highlights", "include_summary",
    }
    assert {t.capability for t in s.tests} == {"search", "extract"}

def test_tavily_schema():
    s = PROVIDER_CLASSES["tavily"].schema
    assert s.auth.mode == "bearer"
    assert s.auth.key_prefix == "tvly-"
    assert s.endpoint.default == "https://api.tavily.com"
    assert {f.key for f in s.fields} >= {
        "search_depth", "topic", "include_domains", "exclude_domains",
        "include_answer", "include_raw_content", "extract_depth",
    }
    assert {t.capability for t in s.tests} == {"search", "extract"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_provider_schemas.py::test_exa_schema tests/test_provider_schemas.py::test_tavily_schema -v`
Expected: FAIL because the old schema fields are still present.

- [ ] **Step 3: Implement both schemas**

Replace the old `ProviderSchema(...)` calls with `auth`, `endpoint`, `fields`, and `tests` per the spec. Set `description_key=f"providers.desc.{type}"` and a `docs_url` where useful. Keep the existing `capabilities` values. Do not change request behavior in this task.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_provider_schemas.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/searchhub/providers/exa.py src/searchhub/providers/tavily.py tests/test_provider_schemas.py
git commit -m "feat: declare Exa and Tavily provider schemas"
```

---

### Task 5: DDG, SearXNG, Jina, and Trafilatura schemas

**Files:**
- Modify: `src/searchhub/providers/ddg.py`
- Modify: `src/searchhub/providers/searxng.py`
- Modify: `src/searchhub/providers/jina.py`
- Modify: `src/searchhub/providers/trafilatura_py.py`
- Test: `tests/test_provider_schemas.py`

**Interfaces:**
- Produces: `options_model` on all four classes.
- Produces: schema `auth` / `endpoint` / `fields` / `tests` per the spec.
- Jina endpoint: `EndpointSpec(default="https://r.jina.ai/", overridable=True, required=False)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_ddg_schema():
    s = PROVIDER_CLASSES["ddg"].schema
    assert s.auth.mode == "none"
    assert {f.key for f in s.fields} >= {"region", "safesearch", "timelimit"}
    assert {t.capability for t in s.tests} == {"search"}

def test_searxng_schema():
    s = PROVIDER_CLASSES["searxng"].schema
    assert s.endpoint.required is True
    assert s.endpoint.overridable is True
    assert {f.key for f in s.fields} >= {"categories", "language", "safesearch", "time_range"}

def test_jina_schema():
    s = PROVIDER_CLASSES["jina"].schema
    assert s.auth.mode == "bearer"
    assert s.auth.optional is True
    assert s.endpoint.default == "https://r.jina.ai/"
    assert s.endpoint.overridable is True
    assert {f.key for f in s.fields} >= {"target_selector", "timeout_s", "no_cache"}

def test_trafilatura_schema():
    s = PROVIDER_CLASSES["trafilatura"].schema
    assert s.auth.mode == "none"
    assert {f.key for f in s.fields} >= {
        "favor_precision", "favor_recall",
        "include_comments", "include_tables",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_provider_schemas.py -v`
Expected: FAIL for the four new schemas.

- [ ] **Step 3: Implement the four schemas**

Use the field/default table in the spec. Set `description_key=f"providers.desc.{type}"` and a `docs_url` where useful. Keep `capabilities` unchanged. Do not change adapter behavior in this task.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_provider_schemas.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/searchhub/providers/ddg.py src/searchhub/providers/searxng.py \
  src/searchhub/providers/jina.py src/searchhub/providers/trafilatura_py.py \
  tests/test_provider_schemas.py
git commit -m "feat: declare local and Jina provider schemas"
```

---

### Task 6: Runtime type/id, instance capabilities, typed options

**Files:**
- Modify: `src/searchhub/providers/base.py:23-43`
- Modify: `src/searchhub/providers/__init__.py:15-39`
- Modify: `src/searchhub/providers/{ddg,exa,jina,searxng,tavily,trafilatura_py}.py` (remove `REQUIRES_KEY`)
- Test: `tests/providers/test_registry.py`

**Interfaces:**
- Produces: `Provider.options_model: type[BaseModel] | None = None`; `Provider.options` is the validated model instance.
- Produces: `Provider.supports(cap)` uses `self.cfg.capabilities`.
- Produces: `build_registry` looks up `PROVIDER_CLASSES[pc.type]`, checks `cls.schema.auth.required`, and skips providers whose options fail validation.
- Consumes: `options_model_for` / `validate_options` from Task 3.

- [ ] **Step 1: Write the failing tests**

```python
# tests/providers/test_registry.py
def test_build_registry_uses_type_not_id(cfg):
    cfg.providers = [
        ProviderConfig(id="exa-work", type="exa", capabilities=["search"]),
    ]
    registry = build_registry(cfg, {"EXA_WORK_KEY_1": "k1"}, httpx.AsyncClient())
    assert set(registry) == {"exa-work"}
    assert registry["exa-work"].cfg.type == "exa"

def test_registry_for_capability_respects_instance_capabilities(cfg):
    cfg.providers = [
        ProviderConfig(id="exa", type="exa", capabilities=["search"]),
    ]
    registry = build_registry(cfg, {"EXA_KEY_1": "k1"}, httpx.AsyncClient())
    assert [p.id for p in registry_for_capability(registry, "search")] == ["exa"]
    assert registry_for_capability(registry, "extract") == []

def test_invalid_options_skips_provider(cfg):
    cfg.providers = [
        ProviderConfig(id="exa", type="exa", capabilities=["search"],
                       options={"bogus": 1}),
    ]
    registry = build_registry(cfg, {"EXA_KEY_1": "k1"}, httpx.AsyncClient())
    assert registry == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/providers/test_registry.py -v`
Expected: FAIL because the registry still keys by `id` and uses class capabilities.

- [ ] **Step 3: Implement runtime changes**

- Add `options_model` and `options` to `Provider`.
- Validate `cfg.options` in `Provider.__init__`.
- Change `supports` to use `cfg.capabilities`.
- Change `build_registry` to use `pc.type`.
- Replace `cls.REQUIRES_KEY` with `cls.schema.auth.required`.
- Catch `ValidationError` from provider construction and log a warning, then skip.
- Remove `REQUIRES_KEY` from all six provider classes.
- Make `auth` / `endpoint` non-optional with `AuthSpec()` / `EndpointSpec()` defaults, then replace the legacy `ProviderSchema` fields with read-only properties derived from them; keep `show_options` as a property returning `False` for compatibility. All providers now construct the new fields, so no old constructor call sites remain.

- [ ] **Step 4: Run provider and registry tests**

Run: `pytest tests/providers -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/searchhub/providers tests/providers
git commit -m "feat: support provider type/id and instance capabilities at runtime"
```

---

### Task 7: Per-capability test status in the engine

**Files:**
- Modify: `src/searchhub/orchestrator.py:35-46`
- Modify: `src/searchhub/orchestrator.py:108-110`
- Modify: `src/searchhub/orchestrator.py:179-181`
- Modify: `src/searchhub/orchestrator.py:255-273`
- Test: `tests/test_orchestrator.py`

**Interfaces:**
- Produces: `record_test(provider_id: str, capability: str, *, success: bool, count: int, took_ms: float, error: str | None = None) -> None`.
- Produces: `provider_tests: dict[str, dict[str, dict[str, Any]]]`.
- `provider_status()` entries gain `"tests": {capability: test}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orchestrator.py
def test_record_test_keeps_capabilities_separate(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    eng = SearchHubEngine(cs, None, httpx.AsyncClient())
    eng.record_test("exa", "search", success=True, count=1, took_ms=10)
    eng.record_test("exa", "extract", success=False, count=0, took_ms=20, error="boom")
    assert eng.provider_tests["exa"]["search"]["success"] is True
    assert eng.provider_tests["exa"]["extract"]["success"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_orchestrator.py::test_record_test_keeps_capabilities_separate -v`
Expected: FAIL because `record_test` still takes `capability` as a keyword and overwrites one slot.

- [ ] **Step 3: Implement the new status shape**

Update the two real-call sites to pass `capability` positionally. Update `provider_status()` to include `tests`. Keep the existing `stats` block unchanged.

- [ ] **Step 4: Run orchestrator tests**

Run: `pytest tests/test_orchestrator.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/searchhub/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: record provider test status per capability"
```

---

### Task 8: Admin provider CRUD with type, id, and options validation

**Files:**
- Modify: `src/searchhub/api/admin/config_routes.py:53-108`
- Modify: `src/searchhub/api/admin/config_routes.py:137-181` (`_provider_status_map`, `_auto_retest` type lookup)
- Modify: `src/searchhub/api/admin/keys_routes.py:26-38`
- Test: `tests/api/admin/test_config_routes.py`
- Test: `tests/api/admin/test_keys_tokens.py`

**Interfaces:**
- Consumes: `ProviderConfig.type`, `validate_options` from Task 3.
- Produces: `POST /api/admin/providers` accepts `type`; unknown type returns 400; duplicate `id` returns 409.
- Produces: `PUT /api/admin/providers/{id}` rejects a `type` change.
- Produces: `_validate_key_for_provider(provider_id, provider_type, key)`; prefix validation uses `provider_type`.
- Produces: `_provider_status_map` and `_auto_retest` resolve the schema by `pc.type`, not `pc.id`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/admin/test_config_routes.py
def test_create_provider_with_type_and_custom_id(admin_client):
    r = admin_client.post("/api/admin/providers", json={
        "id": "exa-work", "type": "exa", "capabilities": ["search"],
    })
    assert r.status_code == 200
    cfg = admin_client.get("/api/admin/config").json()["data"]["config"]
    assert cfg["providers"][0]["type"] == "exa"
    assert cfg["providers"][0]["id"] == "exa-work"

def test_create_provider_unknown_type_rejected(admin_client):
    r = admin_client.post("/api/admin/providers", json={
        "id": "nope", "type": "nope", "capabilities": ["search"],
    })
    assert r.status_code == 400

def test_update_provider_type_immutable(admin_client):
    admin_client.post("/api/admin/providers", json={
        "id": "exa", "type": "exa", "capabilities": ["search"],
    })
    r = admin_client.put("/api/admin/providers/exa", json={
        "id": "exa", "type": "tavily", "capabilities": ["search"],
    })
    assert r.status_code == 400

def test_create_provider_invalid_options_rejected(admin_client):
    r = admin_client.post("/api/admin/providers", json={
        "id": "exa", "type": "exa", "capabilities": ["search"],
        "options": {"bogus": 1},
    })
    assert r.status_code == 400
```

```python
# tests/api/admin/test_keys_tokens.py
def test_key_prefix_validation_uses_type_for_custom_id(admin_client):
    admin_client.post("/api/admin/providers", json={
        "id": "tavily-work", "type": "tavily", "capabilities": ["search"],
    })
    r = admin_client.post("/api/admin/providers/tavily-work/keys",
                          json={"key": "not-a-tavily-key"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/admin/test_config_routes.py tests/api/admin/test_keys_tokens.py -v`
Expected: FAIL because create/update still look up by `id` and ignore `type`.

- [ ] **Step 3: Implement the admin changes**

Add a `_schema_for_type(type)` helper. In create: reject unknown type, validate capabilities/base_url, validate options, append. In update: if `type` was omitted from the request body, keep the existing type; reject an explicit type change; validate options; replace. In keys: resolve schema by `provider_type` and validate prefix. Update `_provider_status_map` and `_auto_retest` to use `pc.type` for schema lookup and `pc.id` for key/status identity. Keep old create bodies without `type` working for built-in IDs via the `type = id` default.

- [ ] **Step 4: Run admin tests**

Run: `pytest tests/api/admin/test_config_routes.py tests/api/admin/test_keys_tokens.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/searchhub/api/admin/config_routes.py src/searchhub/api/admin/keys_routes.py \
  tests/api/admin/test_config_routes.py tests/api/admin/test_keys_tokens.py
git commit -m "feat: validate provider type and options in admin API"
```

---

### Task 9: Per-capability admin test endpoint and status map

**Files:**
- Modify: `src/searchhub/api/admin/config_routes.py:111-217`
- Test: `tests/api/admin/test_config_routes.py`

**Interfaces:**
- Consumes: `TestSpec` from Task 2; `record_test(provider_id, capability, ...)` from Task 7.
- Produces: `POST /api/admin/providers/{id}/test` and `POST /api/admin/providers/test` return:
  ```json
  {"success": true, "data": {"results": [
    {"capability": "search", "success": true, "count": 1, "took_ms": 12.3},
    {"capability": "extract", "success": false, "count": 1, "took_ms": 20.1, "error": "item error"}
  ]}}
  ```
- Produces: `_provider_status_map` returns `{status, test, tests}`; `status` is `failed` if any capability test failed, `ok` if any passed, `untested` otherwise.

- [ ] **Step 1: Write the failing tests**

```python
def test_provider_test_runs_all_capabilities(admin_client, monkeypatch):
    from searchhub.models import ExtractItem, SearchItem
    from searchhub.providers.exa import ExaProvider

    async def fake_search(self, query, limit):
        return [SearchItem(title="t", url="https://x.com", provider=self.id)]

    async def fake_extract(self, urls, **kw):
        return [ExtractItem(url=urls[0], content="ok", provider=self.id)]

    monkeypatch.setattr(ExaProvider, "search", fake_search)
    monkeypatch.setattr(ExaProvider, "extract", fake_extract)
    admin_client.post("/api/admin/providers", json={
        "id": "exa", "type": "exa", "capabilities": ["search", "extract"],
    })
    r = admin_client.post("/api/admin/providers/exa/test")
    assert r.status_code == 200
    caps = {x["capability"] for x in r.json()["data"]["results"]}
    assert caps == {"search", "extract"}

def test_extract_item_error_marks_test_failed(admin_client, monkeypatch):
    from searchhub.models import ExtractItem
    from searchhub.providers.trafilatura_py import TrafilaturaProvider

    async def fake_extract(self, urls, **kw):
        return [ExtractItem(url=urls[0], error="blocked", provider=self.id)]

    monkeypatch.setattr(TrafilaturaProvider, "extract", fake_extract)
    admin_client.post("/api/admin/providers", json={
        "id": "trafilatura", "type": "trafilatura", "capabilities": ["extract"],
    })
    r = admin_client.post("/api/admin/providers/trafilatura/test")
    assert r.json()["data"]["results"][0]["success"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/api/admin/test_config_routes.py -v`
Expected: FAIL because the endpoint only tests one capability and ignores item errors.

- [ ] **Step 3: Implement `_probe` and the endpoint**

- `_probe(provider, capability, spec)` uses `spec.query` / `spec.urls`; for extract, fail if any item has `error` or, when `expect_content`, empty content.
- `test_provider` and `test_provider_draft` loop over `pc.capabilities` and their `TestSpec`s.
- `_record_test` calls `engine.record_test(provider_id, capability, ...)` for each result.
- `_provider_status_map` builds `tests` from `engine.provider_tests.get(pc.id, {})`.
- `_auto_retest` uses the same loop.

- [ ] **Step 4: Run admin tests**

Run: `pytest tests/api/admin/test_config_routes.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/searchhub/api/admin/config_routes.py tests/api/admin/test_config_routes.py
git commit -m "feat: test provider capabilities independently"
```

---

### Task 10: Frontend API types and FieldSpec utilities

**Files:**
- Modify: `frontend/src/api/admin.ts`
- Modify: `frontend/src/stores/providerTypes.ts`
- Create: `frontend/src/utils/providerFields.ts`
- Test: `frontend/tests/provider-types-store.test.ts`
- Test: `frontend/tests/provider-fields.test.ts`

**Interfaces:**
- Produces TypeScript types `FieldSpec`, `AuthSpec`, `EndpointSpec`, `TestSpec`, updated `ProviderType`, `ProviderCfg`, and `ProviderStatus` with `tests: Record<string, ProviderTest>`.
- Produces `groupFields(fields, capability?)`, `isFieldVisible(field, values)`, `defaultFieldValue(field)`, `defaultOptions(fields)`.
- `normalizeProviderTypes` validates the new shape; malformed entries are filtered.

- [ ] **Step 1: Write the failing tests**

```ts
// frontend/tests/provider-fields.test.ts
import { describe, expect, it } from 'vitest'
import { groupFields, isFieldVisible, defaultFieldValue } from '@/utils/providerFields'

const fields = [
  { key: 'search_type', label: 'x', type: 'enum' as const, choices: ['auto', 'deep'], default: 'auto', capability: 'search' as const, group: 'search' },
  { key: 'timeout_s', label: 'y', type: 'int' as const, default: null, capability: 'extract' as const, group: 'advanced' },
]

describe('provider fields', () => {
  it('groups by group and capability', () => {
    expect(groupFields(fields, 'search')).toEqual({ search: [fields[0]] })
  })
  it('honors visible_when', () => {
    expect(isFieldVisible({ ...fields[0], visible_when: { search_type: 'deep' } }, { search_type: 'auto' })).toBe(false)
  })
  it('returns defaults', () => {
    expect(defaultFieldValue(fields[0])).toBe('auto')
    expect(defaultFieldValue(fields[1])).toBeNull()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- provider-fields`
Expected: FAIL because the utility does not exist.

- [ ] **Step 3: Implement the types and utilities**

Update `admin.ts` interfaces. Update `normalizeProviderTypes` to require `auth`, `endpoint`, `fields`, `tests`, and valid capabilities. Implement the pure utility functions. Keep `visible_when` simple: all key/value pairs must match the current options.

- [ ] **Step 4: Run frontend tests and typecheck**

Run: `cd frontend && npm test -- provider-fields provider-types-store && npm run typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/admin.ts frontend/src/stores/providerTypes.ts \
  frontend/src/utils/providerFields.ts frontend/tests/provider-types-store.test.ts \
  frontend/tests/provider-fields.test.ts
git commit -m "feat: add frontend provider field types and utilities"
```

---

### Task 11: Dynamic provider form and detail view

**Files:**
- Create: `frontend/src/components/ProviderField.vue`
- Create: `frontend/src/components/ProviderOptionsForm.vue`
- Modify: `frontend/src/views/ProviderDetailView.vue`
- Modify: `frontend/src/i18n/index.ts`
- Test: `frontend/tests/provider-payload.test.ts`

**Interfaces:**
- `ProviderField` props: `{ field: FieldSpec; modelValue: unknown }`; emits `update:modelValue`.
- `ProviderOptionsForm` props: `{ fields: FieldSpec[]; options: Record<string, unknown>; capabilities: string[] }`; emits `update:options`.
- `ProviderDetailView` uses `form.type`, `form.id`, `form.options` (object), renders `ProviderOptionsForm`, and keeps `base_url` / key pool / common fields.
- `FieldSpec.label` and `.help` are passed through `t()`.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/tests/provider-payload.test.ts
import { describe, expect, it } from 'vitest'
import { buildProviderPayload, defaultOptions } from '@/utils/providerPayload'

describe('provider payload', () => {
  it('includes type, id, and options', () => {
    const payload = buildProviderPayload({
      id: 'exa-work', type: 'exa', capabilities: ['search'],
      enabled: true, weight: 10, priority: 100, max_results: 8,
      base_url: '', key_pool: { max_concurrency: 2, rps_limit: 10, cooldown_s: 60 },
      options: { search_type: 'deep' },
    })
    expect(payload.type).toBe('exa')
    expect(payload.id).toBe('exa-work')
    expect(payload.options.search_type).toBe('deep')
  })

  it('builds defaults from field specs', () => {
    expect(defaultOptions([
      { key: 'search_type', label: 'x', type: 'enum', default: 'auto' },
    ])).toEqual({ search_type: 'auto' })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- provider-payload`
Expected: FAIL because the payload utility does not exist.

- [ ] **Step 3: Implement the components and view**

Create `providerPayload.ts` with `buildProviderPayload` and `defaultOptions`. Implement `ProviderField.vue` for `string`, `text`, `int`, `float`, `bool`, `enum`, `string_list`, and `secret` (secret renders a password input; v1 only Key pool uses it). Implement `ProviderOptionsForm.vue` with groups and advanced collapse. Update `ProviderDetailView.vue`:

- `form.id` defaults to `form.type` for new providers.
- `type` is read-only after creation.
- `base_url` is shown when `entry.endpoint.overridable`; required when `entry.endpoint.required`.
- Key pool is shown when `entry.auth.required || entry.auth.optional`.
- Capabilities are limited to `entry.capabilities`.
- The test button calls `POST /api/admin/providers/{id}/test` once and renders `data.results` per capability; failures show the item-level error.
- The provider description and `docs_url` link are shown in the detail header.
- The raw JSON textarea is removed or moved under an advanced fallback that validates before save.

Add i18n keys for all `providers.fields.<type>.<key>` labels/help and group names in both zh and en.

- [ ] **Step 4: Run frontend tests, typecheck, and build**

Run: `cd frontend && npm test -- provider-payload && npm run typecheck && npm run build`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ProviderField.vue \
  frontend/src/components/ProviderOptionsForm.vue \
  frontend/src/views/ProviderDetailView.vue frontend/src/utils/providerPayload.ts \
  frontend/src/i18n/index.ts frontend/tests/provider-payload.test.ts
git commit -m "feat: render provider options dynamically"
```

---

### Task 12: Provider list with type, instance, and descriptions

**Files:**
- Modify: `frontend/src/views/ProvidersView.vue`
- Create: `frontend/src/utils/providerRows.ts`
- Test: `frontend/tests/provider-rows.test.ts`

**Interfaces:**
- Produces `buildProviderRows(types, providers, keyCounts, status)` returning rows with `{ type, id, name, descriptionKey, capabilities, configured, weight, priority }`.
- v1: show one row per configured instance; if multiple instances of a type exist, group them under the type name. The “add” action is shown only when a type has no configured instance.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/tests/provider-rows.test.ts
import { describe, expect, it } from 'vitest'
import { buildProviderRows } from '@/utils/providerRows'

describe('provider rows', () => {
  it('merges catalog and configured instances by id', () => {
    const rows = buildProviderRows(
      [{ type: 'exa', name: 'Exa', capabilities: ['search'], description_key: 'providers.desc.exa' }],
      [{ id: 'exa-work', type: 'exa', capabilities: ['search'], enabled: true, weight: 10, priority: 100 }],
      {}, {},
    )
    expect(rows[0].id).toBe('exa-work')
    expect(rows[0].type).toBe('exa')
    expect(rows[0].descriptionKey).toBe('providers.desc.exa')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- provider-rows`
Expected: FAIL because the utility does not exist.

- [ ] **Step 3: Implement the rows and update the view**

Implement `buildProviderRows`. Update `ProvidersView.vue` to use it, show `t(descriptionKey)`, show instance ID and type, and use `row.id` for routes/actions. Keep the existing card/table toggle.

- [ ] **Step 4: Run frontend tests, typecheck, and build**

Run: `cd frontend && npm test -- provider-rows && npm run typecheck && npm run build`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/ProvidersView.vue frontend/src/utils/providerRows.ts \
  frontend/tests/provider-rows.test.ts
git commit -m "feat: show provider types and instances with descriptions"
```

---

### Task 13: Exa and Tavily adapters consume options

**Files:**
- Modify: `src/searchhub/providers/exa.py`
- Modify: `src/searchhub/providers/tavily.py`
- Test: `tests/providers/test_exa.py`
- Test: `tests/providers/test_tavily.py`

**Interfaces:**
- Consumes: `self.options` from Task 6.
- Exa search body uses `type`, `category`, `includeDomains`, `excludeDomains`, `startPublishedDate`, `endPublishedDate`, and `contents` flags.
- Exa contents body uses `text`, `highlights`, `summary`.
- Tavily search body uses `search_depth`, `topic`, `include_domains`, `exclude_domains`, `include_answer`, `include_raw_content`, and `days`.
- Tavily extract body uses `extract_depth` and `include_images`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/providers/test_exa.py
import json

@pytest.mark.asyncio
@respx.mock
async def test_search_uses_configured_options():
    route = respx.post(f"{EXA}/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    cfg = ProviderConfig(id="exa", type="exa", capabilities=["search"],
                         options={"search_type": "deep", "include_domains": ["a.com"]})
    await ExaProvider(cfg, ["k1"], httpx.AsyncClient()).search("python", 3)
    body = json.loads(route.calls[0].request.content)
    assert body["type"] == "deep"
    assert body["includeDomains"] == ["a.com"]
```

```python
# tests/providers/test_tavily.py
import json

@pytest.mark.asyncio
@respx.mock
async def test_search_uses_configured_options():
    route = respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    cfg = ProviderConfig(id="tavily", type="tavily", capabilities=["search"],
                         options={"search_depth": "advanced", "topic": "news"})
    await TavilyProvider(cfg, ["k1"], httpx.AsyncClient()).search("python", 3)
    body = json.loads(route.calls[0].request.content)
    assert body["search_depth"] == "advanced"
    assert body["topic"] == "news"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/providers/test_exa.py tests/providers/test_tavily.py -v`
Expected: FAIL because the adapters still hardcode the old bodies.

- [ ] **Step 3: Implement the adapter option mapping**

Use `self.options` and only include optional keys when they are not `None` / empty where the API expects omission. Preserve current defaults when options are default.

- [ ] **Step 4: Run tests**

Run: `pytest tests/providers/test_exa.py tests/providers/test_tavily.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/searchhub/providers/exa.py src/searchhub/providers/tavily.py \
  tests/providers/test_exa.py tests/providers/test_tavily.py
git commit -m "feat: map Exa and Tavily options to requests"
```

---

### Task 14: DDG and SearXNG adapters consume options

**Files:**
- Modify: `src/searchhub/providers/ddg.py`
- Modify: `src/searchhub/providers/searxng.py`
- Test: `tests/providers/test_ddg.py`
- Test: `tests/providers/test_searxng.py`

**Interfaces:**
- DDG passes `region`, `safesearch`, `timelimit`, and `backend` to `DDGS().text()` when set.
- SearXNG passes `categories` (comma-joined), `language`, `safesearch`, `time_range`, and `engines` (comma-joined) as query params.

- [ ] **Step 1: Write the failing tests**

```python
# tests/providers/test_ddg.py
def test_search_passes_configured_kwargs(monkeypatch):
    captured = {}
    class FakeDDGS:
        def text(self, query, **kwargs):
            captured.update(kwargs)
            return []
    monkeypatch.setattr("ddgs.DDGS", lambda *a, **kw: FakeDDGS())
    cfg = ProviderConfig(id="ddg", type="ddg", capabilities=["search"],
                         options={"region": "cn-zh", "safesearch": "off"})
    DdgProvider(cfg, [], None)._search_sync("q", 5)
    assert captured["region"] == "cn-zh"
    assert captured["safesearch"] == "off"
```

```python
# tests/providers/test_searxng.py
@pytest.mark.asyncio
@respx.mock
async def test_search_passes_configured_params():
    route = respx.get("http://searxng:8080/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    cfg = ProviderConfig(id="searxng", type="searxng", capabilities=["search"],
                         base_url="http://searxng:8080",
                         options={"categories": ["general", "news"], "language": "zh-CN"})
    await SearxngProvider(cfg, [], httpx.AsyncClient()).search("q", 5)
    params = route.calls[0].request.url.params
    assert params["categories"] == "general,news"
    assert params["language"] == "zh-CN"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/providers/test_ddg.py tests/providers/test_searxng.py -v`
Expected: FAIL because the adapters ignore options.

- [ ] **Step 3: Implement the mappings**

Build kwargs/params only for non-empty values. Keep the existing `format=json` and `safesearch` defaults when options are default.

- [ ] **Step 4: Run tests**

Run: `pytest tests/providers/test_ddg.py tests/providers/test_searxng.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/searchhub/providers/ddg.py src/searchhub/providers/searxng.py \
  tests/providers/test_ddg.py tests/providers/test_searxng.py
git commit -m "feat: map DDG and SearXNG options to requests"
```

---

### Task 15: Jina and Trafilatura adapters consume options

**Files:**
- Modify: `src/searchhub/providers/jina.py`
- Modify: `src/searchhub/providers/trafilatura_py.py`
- Test: `tests/providers/test_jina.py`
- Test: `tests/providers/test_trafilatura.py`

**Interfaces:**
- Jina base URL: `self.cfg.base_url or "https://r.jina.ai/"`; join with the target URL without double slashes.
- Jina headers: `X-Return-Format` from the request `fmt`; `X-Target-Selector`, `X-Wait-For-Selector`, `X-Timeout`, `X-No-Cache` when set.
- Trafilatura passes `output_format` derived from the request `fmt` (`markdown` -> `markdown`, otherwise `txt`), plus `favor_precision`, `favor_recall`, `include_comments`, `include_tables`, `deduplicate`, and `target_language`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/providers/test_jina.py
@pytest.mark.asyncio
@respx.mock
async def test_extract_uses_custom_base_url_and_headers():
    route = respx.get("http://reader.local/https://a.com").mock(
        return_value=httpx.Response(200, text="# A\nbody")
    )
    cfg = ProviderConfig(id="jina", type="jina", capabilities=["extract"],
                         base_url="http://reader.local/",
                         options={"target_selector": "main",
                                  "timeout_s": 30, "no_cache": True})
    await JinaProvider(cfg, [], httpx.AsyncClient()).extract(["https://a.com"])
    req = route.calls[0].request
    assert req.headers["X-Return-Format"] == "markdown"  # request fmt default wins
    assert req.headers["X-Target-Selector"] == "main"
    assert req.headers["X-Timeout"] == "30"
    assert req.headers["X-No-Cache"] == "true"
```

```python
# tests/providers/test_trafilatura.py
def test_extract_passes_options(monkeypatch):
    captured = {}
    monkeypatch.setattr("trafilatura.fetch_url", lambda url: "<html><title>T</title><p>x</p></html>")
    def fake_extract(html, **kwargs):
        captured.update(kwargs)
        return "body"
    monkeypatch.setattr("trafilatura.extract", fake_extract)
    cfg = ProviderConfig(id="trafilatura", type="trafilatura", capabilities=["extract"],
                         options={"favor_precision": True, "target_language": "zh"})
    TrafilaturaProvider(cfg, [], None)._extract_sync("https://a.com", "markdown")
    assert captured["favor_precision"] is True
    assert captured["target_language"] == "zh"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/providers/test_jina.py tests/providers/test_trafilatura.py -v`
Expected: FAIL because Jina hardcodes the cloud URL and Trafilatura ignores options.

- [ ] **Step 3: Implement the mappings**

For Jina, do **not** use `urljoin(base, target)` with the target URL: the target is absolute and `urljoin` would discard the base. Concatenate `base.rstrip("/") + "/" + target.lstrip("/")` (or an equivalent helper) so `http://reader.local/` + `https://a.com` becomes `http://reader.local/https://a.com`. Only set headers when values are not `None`/empty. For Trafilatura, map the request `fmt` to `output_format` (`markdown` -> `markdown`, otherwise `txt`) and pass the rest of the options.

- [ ] **Step 4: Run tests**

Run: `pytest tests/providers/test_jina.py tests/providers/test_trafilatura.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/searchhub/providers/jina.py src/searchhub/providers/trafilatura_py.py \
  tests/providers/test_jina.py tests/providers/test_trafilatura.py
git commit -m "feat: map Jina and Trafilatura options to requests"
```

---

### Task 16: Cache keys include config version

**Files:**
- Modify: `src/searchhub/engine/cache_keys.py`
- Modify: `src/searchhub/orchestrator.py` (search/extract cache key calls)
- Modify: `tests/storage/test_cache.py`

**Interfaces:**
- `search_cache_key(query, limit, providers, strategy, config_version)`.
- `extract_cache_key(url, fmt, max_chars, config_version)`.
- The engine passes `self.config.config_version`.

- [ ] **Step 1: Write the failing test**

```python
# tests/storage/test_cache.py
from searchhub.engine.cache_keys import extract_cache_key, search_cache_key

def test_config_version_changes_keys():
    a = search_cache_key("q", 5, "all", "fanout", 1)
    b = search_cache_key("q", 5, "all", "fanout", 2)
    assert a != b
    assert extract_cache_key("https://a.com", "markdown", 1000, 1) != \
        extract_cache_key("https://a.com", "markdown", 1000, 2)
```

Update the existing calls in `tests/storage/test_cache.py:40-42` to pass a version argument.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/storage/test_cache.py -v`
Expected: FAIL because the functions do not accept `config_version`.

- [ ] **Step 3: Implement the key change**

Add the parameter to both functions and update the two engine call sites. Document that external config edits that do not bump `config_version` may not invalidate cache; the normal save path does bump it.

- [ ] **Step 4: Run tests**

Run: `pytest tests/storage/test_cache.py tests/test_orchestrator.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/searchhub/engine/cache_keys.py src/searchhub/orchestrator.py \
  tests/storage/test_cache.py
git commit -m "feat: include config version in cache keys"
```

---

### Task 17: Documentation and full verification

**Files:**
- Modify: `README.md`
- Modify: `.superpowers/specs/2026-10-25-provider-config-redesign.md` only if implementation reveals a factual correction

**Interfaces:**
- No new runtime interfaces.

- [ ] **Step 1: Update README**

Update the provider table with the v1 fields, document Jina self-host `base_url`, and add a note: “v1 UI 默认每种类型一个实例；后端模型支持多实例，UI 入口后续开放。” Add a short migration note for `type`.

- [ ] **Step 2: Run the full backend suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 3: Run the full frontend suite**

Run: `cd frontend && npm test && npm run typecheck && npm run build`
Expected: all tests pass and the build succeeds.

- [ ] **Step 4: Check the working tree**

Run: `git status --short`
Expected: only intended files changed.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: document provider configuration redesign"
```

---

## Self-Review Notes

- **Spec coverage:** Tasks 1-2 cover the data model/schema; 3-5 cover options and provider fields; 6-9 cover runtime/admin; 10-12 cover frontend; 13-15 cover adapter behavior; 16 covers cache; 17 covers docs/verification.
- **Type consistency:** `type` is the adapter type, `id` is the instance ID. `record_test(provider_id, capability, ...)` is used consistently in Tasks 7 and 9. `FieldSpec.label` / `.help` are i18n keys.
- **Review Focus tests:** Task 1 covers legacy `type`; Tasks 3/6 cover invalid options; Task 6 covers multiple instances; Task 9 covers item-level extract errors; Task 15 covers Jina base URL joining.
- **Deferred:** per-request options, arbitrary secret fields, and the multi-instance “add another” UI are intentionally not implemented.
