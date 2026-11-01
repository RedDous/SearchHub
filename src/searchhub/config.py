from __future__ import annotations

import hashlib
import hmac as _hmac
import os
import re
import secrets as _secrets
import shutil
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

CAPABILITIES = ("search", "extract")
_KEY_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
_BACKUP_COUNT = 5


def key_prefix_for(provider_id: str) -> str:
    """Env-var-safe secret prefix for an instance id (``exa-work`` -> ``EXA_WORK_KEY_``)."""
    return re.sub(r"[^A-Z0-9]+", "_", provider_id.upper()) + "_KEY_"


def _scrypt_hash(password: str) -> str:
    salt = _secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"scrypt${2 ** 14}${8}${1}${salt.hex()}${digest.hex()}"


def _scrypt_verify(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, digest_hex = stored.split("$")
        if algo != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                                n=int(n), r=int(r), p=int(p))
        return _hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


class KeyPoolConfig(BaseModel):
    max_concurrency: int = Field(default=2, ge=1)
    rps_limit: float = Field(default=10, ge=0.1)
    cooldown_s: float = Field(default=60.0, ge=0)


class ProviderConfig(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    type: str = ""
    capabilities: list[str]
    enabled: bool = True
    weight: int = Field(default=10, ge=1, le=100)
    priority: int = Field(default=100, ge=1)
    max_results: int = Field(default=8, ge=1, le=50)
    base_url: str | None = None
    key_pool: KeyPoolConfig = KeyPoolConfig()
    options: dict[str, Any] = {}

    @model_validator(mode="after")
    def _default_type(self) -> "ProviderConfig":
        if not self.type:
            # 用 object.__setattr__ 赋值，保持 model_fields_set 准确：
            # 省略 type 时不能让它看起来像显式传入（admin API 依赖这一点判断类型不可变）。
            object.__setattr__(self, "type", self.id)
        return self


def _duplicate_provider_id(providers: list[ProviderConfig]) -> str | None:
    seen: set[str] = set()
    for p in providers:
        if p.id in seen:
            return p.id
        seen.add(p.id)
    return None


def _duplicate_provider_key_prefix(providers: list[ProviderConfig]) -> str | None:
    seen: set[str] = set()
    for p in providers:
        prefix = key_prefix_for(p.id)
        if prefix in seen:
            return prefix
        seen.add(prefix)
    return None


class StrategyConfig(BaseModel):
    default_mode: Literal["fanout", "rotation", "primary_fallback"] = "fanout"
    timeout_s: float = Field(default=15.0, ge=0.5, le=120)


class CacheConfig(BaseModel):
    enabled: bool = True
    search_ttl_s: int = Field(default=600, ge=0)
    extract_ttl_s: int = Field(default=86400, ge=0)


class TokenEntry(BaseModel):
    name: str
    token_hash: str
    id: str = ""
    created_at: float = 0.0
    revoked: bool = False


class AuthConfig(BaseModel):
    tokens: list[TokenEntry] = Field(default_factory=list)


class AdminConfig(BaseModel):
    username: str = "admin"
    password_hash: str = ""
    session_ttl_hours: int = Field(default=24, ge=1, le=720)


class HistoryConfig(BaseModel):
    retention_days: int = Field(default=30, ge=1, le=3650)
    redact_queries: bool = False


class AppConfig(BaseModel):
    strategy: StrategyConfig = StrategyConfig()
    cache: CacheConfig = CacheConfig()
    auth: AuthConfig = AuthConfig()
    admin: AdminConfig = AdminConfig()
    history: HistoryConfig = HistoryConfig()
    providers: list[ProviderConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_provider_ids(self) -> "AppConfig":
        duplicate = _duplicate_provider_id(self.providers)
        if duplicate is not None:
            raise ValueError(f"duplicate provider id: {duplicate!r}")
        duplicate_prefix = _duplicate_provider_key_prefix(self.providers)
        if duplicate_prefix is not None:
            raise ValueError(f"duplicate canonical key prefix: {duplicate_prefix!r}")
        return self

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

    def _key_prefix_alias(self, provider_id: str) -> str | None:
        prefix = key_prefix_for(provider_id)
        return next(
            (p.id for p in self.get().providers
             if p.id != provider_id and key_prefix_for(p.id) == prefix),
            None,
        )

    def provider_keys(self, provider_id: str) -> list[str]:
        if self._key_prefix_alias(provider_id) is not None:
            return []
        prefix = key_prefix_for(provider_id)
        pairs = [
            (int(k[len(prefix):]), v)
            for k, v in self._secrets.items()
            if k.startswith(prefix) and k[len(prefix):].isdigit()
        ]
        return [v for _, v in sorted(pairs)]

    def verify_admin_password(self, password: str) -> bool:
        stored = self.get().admin.password_hash
        return bool(stored) and _scrypt_verify(password, stored)

    def set_admin_password(self, password: str) -> None:
        cfg = self.get()
        cfg.admin.password_hash = _scrypt_hash(password)
        self.save_config(cfg)

    def session_secret(self) -> bytes:
        path = self.data_dir / "session_secret"
        if not path.exists():
            path.write_text(_secrets.token_hex(32))
            path.chmod(0o600)
        return bytes.fromhex(path.read_text().strip())

    def save_secrets(self, secrets_map: dict[str, str]) -> None:
        self._secrets = dict(secrets_map)
        tmp = self.secrets_path.with_name(self.secrets_path.name + ".tmp")
        try:
            with tmp.open("w") as f:
                tmp.chmod(0o600)
                for k, v in sorted(secrets_map.items()):
                    f.write(f"{k}={v}\n")
            os.replace(tmp, self.secrets_path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        self.secrets_path.chmod(0o600)
        self._mtime = self._stat()

    def add_provider_key(self, provider_id: str, key: str) -> None:
        key = key.strip()
        if not key:
            raise ValueError("key must not be empty")
        alias = self._key_prefix_alias(provider_id)
        if alias is not None:
            raise ValueError(
                f"provider id {provider_id!r} conflicts with configured provider {alias!r}"
            )
        prefix = key_prefix_for(provider_id)
        secrets_map = dict(self._secrets)
        existing = [k for k in secrets_map if k.startswith(prefix) and k[len(prefix):].isdigit()]
        next_idx = max([int(k[len(prefix):]) for k in existing], default=0) + 1
        secrets_map[f"{prefix}{next_idx}"] = key
        self.save_secrets(secrets_map)

    def remove_provider_key(self, provider_id: str, index: int) -> None:
        alias = self._key_prefix_alias(provider_id)
        if alias is not None:
            raise ValueError(
                f"provider id {provider_id!r} conflicts with configured provider {alias!r}"
            )
        prefix = key_prefix_for(provider_id)
        pairs = sorted(
            (int(k[len(prefix):]), k)
            for k in self._secrets
            if k.startswith(prefix) and k[len(prefix):].isdigit()
        )
        if index < 0 or index >= len(pairs):
            raise IndexError("key index out of range")
        removed_key = pairs[index][1]
        secrets_map = {k: v for k, v in self._secrets.items() if k != removed_key}
        self.save_secrets(secrets_map)

    @property
    def updated_at(self) -> float:
        try:
            return self.config_path.stat().st_mtime
        except FileNotFoundError:
            return 0.0

    def save_config(self, cfg: AppConfig) -> None:
        for p in cfg.providers:
            for c in p.capabilities:
                if c not in CAPABILITIES:
                    raise ValueError(f"invalid capability: {c!r}")
        duplicate = _duplicate_provider_id(cfg.providers)
        if duplicate is not None:
            raise ValueError(f"duplicate provider id: {duplicate!r}")
        duplicate_prefix = _duplicate_provider_key_prefix(cfg.providers)
        if duplicate_prefix is not None:
            raise ValueError(f"duplicate canonical key prefix: {duplicate_prefix!r}")
        self._write_yaml(cfg)
        self._cfg = cfg

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
        tmp = self.config_path.with_name(f"{self.config_path.name}.tmp")
        try:
            with tmp.open("w") as f:
                yaml.safe_dump(raw, f, allow_unicode=True, sort_keys=False)
            os.replace(tmp, self.config_path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
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
