from __future__ import annotations

from dataclasses import dataclass

KeyPoolParams = str  # "none" | "rps" | "full"


@dataclass(frozen=True)
class ProviderSchema:
    type: str
    name: str
    capabilities: tuple[str, ...] = ()
    requires_key: bool = False
    optional_key: bool = False
    requires_base_url: bool = False
    key_pool_params: KeyPoolParams = "none"
    show_max_results: bool = False
    show_options: bool = False


def validate_provider_config(provider_id: str, capabilities: list[str],
                             base_url: str | None, schema: ProviderSchema | None) -> list[str]:
    """返回错误列表（空 = 通过）。未知类型（schema=None）不校验。"""
    if schema is None:
        return []
    errors: list[str] = []
    if schema.requires_base_url and not (base_url or "").strip():
        errors.append(f"{provider_id} requires base_url")
    allowed = set(schema.capabilities)
    for c in capabilities:
        if c not in allowed:
            errors.append(f"{provider_id} does not support capability {c!r}")
    return errors