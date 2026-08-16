from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

CAPABILITIES = ("search", "extract")
_KEY_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
_BACKUP_COUNT = 5


class KeyPoolConfig(BaseModel):
    max_concurrency: int = Field(default=2, ge=1)
    rps_limit: float = Field(default=10, ge=0.1)
    cooldown_s: float = Field(default=60.0, ge=0)


class ProviderConfig(BaseModel):
    id: str
    capabilities: list[str]
    enabled: bool = True
    weight: int = Field(default=10, ge=1, le=100)
    priority: int = Field(default=100, ge=1)
    max_results: int = Field(default=8, ge=1, le=50)
    base_url: str | None = None
    key_pool: KeyPoolConfig = KeyPoolConfig()
    options: dict[str, Any] = {}


class StrategyConfig(BaseModel):
    default_mode: Literal["fanout", "rotation", "primary_fallback"] = "fanout"
    timeout_s: float = Field(default=15.0, ge=0.5, le=120)


class CacheConfig(BaseModel):
    enabled: bool = True
    search_ttl_s: int = Field(default=600, ge=0)
    extract_ttl_s: int = Field(default=86400, ge=0)


class AppConfig(BaseModel):
    strategy: StrategyConfig = StrategyConfig()
    cache: CacheConfig = CacheConfig()
    providers: list[ProviderConfig] = Field(default_factory=list)

    def provider(self, provider_id: str) -> ProviderConfig | None:
        return next((p for p in self.providers if p.id == provider_id), None)


class ConfigService:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.config_path = self.data_dir / "config.yaml"
        self.secrets_path = self.data_dir / "secrets.env"
        self._cfg = AppConfig()
        self._secrets: dict[str, str] = {}
        self._loaded = False
        self._mtime: tuple[float, float] = (-1.0, -1.0)
        self.config_version = 0

    def load(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            self._cfg = AppConfig()
            self._write_yaml(self._cfg)
        else:
            self._cfg = AppConfig.model_validate(
                yaml.safe_load(self.config_path.read_text()) or {}
            )
        self._secrets = self._parse_secrets()
        self._mtime = self._stat()
        self._loaded = True

    def get(self) -> AppConfig:
        if not self._loaded:
            self.load()
        return self._cfg

    def secrets(self) -> dict[str, str]:
        return self._secrets

    def provider_keys(self, provider_id: str) -> list[str]:
        prefix = f"{provider_id.upper()}_KEY_"
        pairs = [
            (int(k[len(prefix):]), v)
            for k, v in self._secrets.items()
            if k.startswith(prefix) and k[len(prefix):].isdigit()
        ]
        return [v for _, v in sorted(pairs)]

    def save_config(self, cfg: AppConfig) -> None:
        for p in cfg.providers:
            for c in p.capabilities:
                if c not in CAPABILITIES:
                    raise ValueError(f"invalid capability: {c!r}")
        self._cfg = cfg
        self._write_yaml(cfg)

    def maybe_reload(self) -> bool:
        if not self._loaded:
            self.load()
            return True
        if self._stat() != self._mtime:
            self.load()
            return True
        return False

    def _stat(self) -> tuple[float, float]:
        def m(p: Path) -> float:
            try:
                return p.stat().st_mtime_ns
            except FileNotFoundError:
                return -1.0

        return (m(self.config_path), m(self.secrets_path))

    def _write_yaml(self, cfg: AppConfig) -> None:
        if self.config_path.exists():
            for i in range(_BACKUP_COUNT - 1, 0, -1):
                src = self.config_path.with_name(f"{self.config_path.name}.bak{i}")
                dst = self.config_path.with_name(f"{self.config_path.name}.bak{i + 1}")
                if src.exists():
                    shutil.move(str(src), str(dst))
            shutil.copy2(
                self.config_path, self.config_path.with_name(f"{self.config_path.name}.bak1")
            )
        raw = cfg.model_dump(mode="json")
        yaml.safe_dump(raw, self.config_path.open("w"), allow_unicode=True, sort_keys=False)
        self.config_version += 1
        self._mtime = self._stat()

    def _parse_secrets(self) -> dict[str, str]:
        if not self.secrets_path.exists():
            self.secrets_path.touch(mode=0o600)
            return {}
        result: dict[str, str] = {}
        for line in self.secrets_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = _KEY_LINE.match(line)
            if m:
                result[m.group(1)] = m.group(2)
        return result
