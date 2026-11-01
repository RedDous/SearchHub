from dataclasses import asdict

from searchhub.providers import PROVIDER_CLASSES
from searchhub.providers.options import (
    DdgOptions,
    ExaOptions,
    JinaOptions,
    SearxngOptions,
    TavilyOptions,
    TrafilaturaOptions,
)
from searchhub.providers.schema import (
    AuthSpec,
    EndpointSpec,
    FieldSpec,
    ProviderSchema,
    TestSpec,
    validate_provider_config,
)


def test_all_six_providers_declare_schema():
    assert set(PROVIDER_CLASSES) == {"exa", "tavily", "ddg", "searxng", "jina", "trafilatura"}
    for pid, cls in PROVIDER_CLASSES.items():
        s = cls.schema
        assert isinstance(s, ProviderSchema)
        assert s.type == pid
        assert s.name
        assert set(s.capabilities) == cls.capabilities


def test_schema_flags():
    assert PROVIDER_CLASSES["exa"].schema.requires_key is True
    assert PROVIDER_CLASSES["exa"].schema.key_pool_params == "full"
    assert PROVIDER_CLASSES["ddg"].schema.requires_key is False
    assert PROVIDER_CLASSES["ddg"].schema.key_pool_params == "none"
    assert PROVIDER_CLASSES["searxng"].schema.requires_base_url is True
    assert PROVIDER_CLASSES["searxng"].schema.key_pool_params == "rps"
    assert PROVIDER_CLASSES["jina"].schema.key_pool_params == "full"
    assert PROVIDER_CLASSES["trafilatura"].schema.key_pool_params == "rps"
    assert PROVIDER_CLASSES["jina"].schema.optional_key is True
    assert PROVIDER_CLASSES["exa"].schema.optional_key is False
    assert PROVIDER_CLASSES["ddg"].schema.optional_key is False
    for pid, cls in PROVIDER_CLASSES.items():
        assert cls.schema.show_options is False
        assert cls.schema.show_max_results == ("search" in cls.capabilities)


def test_validate_requires_base_url():
    s = PROVIDER_CLASSES["searxng"].schema
    errors = validate_provider_config("searxng", ["search"], "", s)
    assert errors and "base_url" in errors[0]
    assert validate_provider_config("searxng", ["search"], "http://searxng:8080", s) == []


def test_validate_capability_bounds():
    s = PROVIDER_CLASSES["searxng"].schema
    errors = validate_provider_config("searxng", ["search", "extract"], "http://x", s)
    assert any("extract" in e for e in errors)


def test_validate_unknown_type_is_lenient():
    assert validate_provider_config("custom-thing", ["search"], "", None) == []


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
    assert PROVIDER_CLASSES["exa"].options_model is ExaOptions


def test_tavily_schema():
    s = PROVIDER_CLASSES["tavily"].schema
    assert s.auth.mode == "bearer"
    assert s.auth.key_prefix == "tvly-"
    assert s.endpoint.default == "https://api.tavily.com"
    assert {f.key for f in s.fields} >= {
        "search_depth", "topic", "include_domains", "exclude_domains",
        "include_raw_content", "extract_depth",
    }
    assert "include_answer" not in {f.key for f in s.fields}
    assert {t.capability for t in s.tests} == {"search", "extract"}
    assert PROVIDER_CLASSES["tavily"].options_model is TavilyOptions


def test_ddg_schema():
    s = PROVIDER_CLASSES["ddg"].schema
    assert s.auth.mode == "none"
    assert {f.key for f in s.fields} >= {"region", "safesearch", "timelimit"}
    assert {t.capability for t in s.tests} == {"search"}
    assert PROVIDER_CLASSES["ddg"].options_model is DdgOptions


def test_searxng_schema():
    s = PROVIDER_CLASSES["searxng"].schema
    assert s.endpoint.required is True
    assert s.endpoint.overridable is True
    assert {f.key for f in s.fields} >= {"categories", "language", "safesearch", "time_range"}
    assert PROVIDER_CLASSES["searxng"].options_model is SearxngOptions


def test_jina_schema():
    s = PROVIDER_CLASSES["jina"].schema
    assert s.auth.mode == "bearer"
    assert s.auth.optional is True
    assert s.endpoint.default == "https://r.jina.ai/"
    assert s.endpoint.overridable is True
    assert {f.key for f in s.fields} >= {"target_selector", "timeout_s", "no_cache"}
    assert PROVIDER_CLASSES["jina"].options_model is JinaOptions


def test_trafilatura_schema():
    s = PROVIDER_CLASSES["trafilatura"].schema
    assert s.auth.mode == "none"
    assert {f.key for f in s.fields} >= {
        "favor_precision", "favor_recall",
        "include_comments", "include_tables",
    }
    assert PROVIDER_CLASSES["trafilatura"].options_model is TrafilaturaOptions