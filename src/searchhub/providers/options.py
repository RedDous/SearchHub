from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SafesearchDdg = Literal["on", "moderate", "off"]
TimelimitDdg = Literal["", "d", "w", "m", "y"]
SafesearchSearxng = Literal["0", "1", "2"]
TimeRangeSearxng = Literal["", "day", "week", "month", "year"]
SearchTypeExa = Literal["auto", "lite", "deep"]
SearchDepthTavily = Literal["basic", "advanced"]
TopicTavily = Literal["general", "news", "finance"]


class _Options(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DdgOptions(_Options):
    region: str | None = None
    safesearch: SafesearchDdg = "moderate"
    timelimit: TimelimitDdg = ""
    backend: str | None = None


class SearxngOptions(_Options):
    categories: list[str] = Field(default_factory=lambda: ["general"])
    language: str = "all"
    safesearch: SafesearchSearxng = "1"
    time_range: TimeRangeSearxng = ""
    engines: list[str] = Field(default_factory=list)


class ExaOptions(_Options):
    search_type: SearchTypeExa = "auto"
    category: str | None = None
    include_domains: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)
    start_published_date: str | None = None
    end_published_date: str | None = None
    include_text: bool = True
    include_highlights: bool = False
    include_summary: bool = False


class TavilyOptions(_Options):
    search_depth: SearchDepthTavily = "basic"
    topic: TopicTavily = "general"
    include_domains: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)
    include_raw_content: bool = False
    days: int | None = None
    extract_depth: SearchDepthTavily = "basic"
    include_images: bool = False


class JinaOptions(_Options):
    target_selector: str | None = None
    wait_for_selector: str | None = None
    timeout_s: int | None = Field(default=None, ge=1, le=120)
    no_cache: bool = False


class TrafilaturaOptions(_Options):
    favor_precision: bool = False
    favor_recall: bool = False
    include_comments: bool = True
    include_tables: bool = True
    deduplicate: bool = False
    target_language: str | None = None


OPTIONS_MODELS: dict[str, type[BaseModel]] = {
    "ddg": DdgOptions,
    "searxng": SearxngOptions,
    "exa": ExaOptions,
    "tavily": TavilyOptions,
    "jina": JinaOptions,
    "trafilatura": TrafilaturaOptions,
}


def options_model_for(provider_type: str) -> type[BaseModel] | None:
    return OPTIONS_MODELS.get(provider_type)


def validate_options(provider_type: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Validate provider options and return the full dict, defaults included.

    Unknown provider types are passed through unchanged; unknown keys on a
    known type raise ``pydantic.ValidationError``.
    """
    model = options_model_for(provider_type)
    if model is None:
        return dict(raw)
    return model.model_validate(raw).model_dump()
