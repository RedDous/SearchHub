from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SearchItem(BaseModel):
    title: str
    url: str
    description: str = ""
    position: int = 0
    provider: str = ""
    score: float = 0.0
    published_at: str | None = None


class ExtractItem(BaseModel):
    url: str
    title: str = ""
    content: str = ""
    raw_content: str = ""
    metadata: dict[str, Any] = {}
    provider: str = ""
    error: str | None = None


class SearchData(BaseModel):
    web: list[SearchItem]


class SearchResponse(BaseModel):
    success: bool = True
    data: SearchData
    meta: dict[str, Any] = {}
    error: str | None = None


class ExtractResponse(BaseModel):
    success: bool = True
    data: list[ExtractItem]
    meta: dict[str, Any] = {}
    error: str | None = None
