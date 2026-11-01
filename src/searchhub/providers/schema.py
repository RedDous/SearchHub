from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

KeyPoolParams = str  # "none" | "rps" | "full"

AuthMode = Literal["none", "bearer", "header", "query"]
FieldType = Literal[
    "string", "text", "int", "float", "bool",
    "enum", "string_list", "secret",
]
CapabilityName = Literal["search", "extract"]


@dataclass(frozen=True)
class AuthSpec:
    mode: AuthMode = "none"
    header_name: str | None = None
    query_param: str | None = None
    required: bool = False
    optional: bool = False
    key_prefix: str | None = None
    hint: str = ""


@dataclass(frozen=True)
class EndpointSpec:
    default: str | None = None
    overridable: bool = False
    required: bool = False
    label: str = "Base URL"
    placeholder: str = ""


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str  # i18n key, e.g. "providers.fields.exa.search_type"
    type: FieldType
    default: Any = None
    choices: tuple[str, ...] = ()
    required: bool = False
    capability: CapabilityName | None = None
    group: str = "general"
    help: str = ""  # i18n key, e.g. "providers.fields.exa.search_type.help"
    placeholder: str = ""
    min: float | None = None
    max: float | None = None
    step: float | None = None
    advanced: bool = False
    visible_when: dict[str, Any] | None = None


@dataclass(frozen=True)
class TestSpec:
    # Not a pytest test class, even though the name starts with "Test".
    __test__ = False

    capability: CapabilityName
    query: str | None = None
    urls: tuple[str, ...] = ()
    max_chars: int = 200
    min_results: int = 0
    expect_content: bool = False


@dataclass(frozen=True)
class ProviderSchema:
    type: str
    name: str
    capabilities: tuple[str, ...] = ()
    key_pool_params: KeyPoolParams = "none"
    auth: AuthSpec = AuthSpec()
    endpoint: EndpointSpec = EndpointSpec()
    fields: tuple[FieldSpec, ...] = ()
    tests: tuple[TestSpec, ...] = ()
    description_key: str | None = None
    docs_url: str | None = None

    # Legacy flag names kept as read-only properties for compatibility with
    # the admin API and existing call sites.
    @property
    def requires_key(self) -> bool:
        return self.auth.required

    @property
    def optional_key(self) -> bool:
        return self.auth.optional

    @property
    def requires_base_url(self) -> bool:
        return self.endpoint.required

    @property
    def key_prefix(self) -> str | None:
        return self.auth.key_prefix

    @property
    def show_max_results(self) -> bool:
        return "search" in self.capabilities

    @property
    def show_options(self) -> bool:
        return False


def validate_provider_config(provider_id: str, capabilities: list[str],
                             base_url: str | None, schema: ProviderSchema | None) -> list[str]:
    """返回错误列表（空 = 通过）。未知类型（schema=None）不校验。"""
    if schema is None:
        return []
    errors: list[str] = []
    if schema.endpoint.required and not (base_url or "").strip():
        errors.append(f"{provider_id} requires base_url")
    allowed = set(schema.capabilities)
    for c in capabilities:
        if c not in allowed:
            errors.append(f"{provider_id} does not support capability {c!r}")
    return errors
