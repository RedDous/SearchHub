import pytest
from pydantic import ValidationError

from searchhub.providers.options import (
    OPTIONS_MODELS,
    DdgOptions,
    ExaOptions,
    JinaOptions,
    SearxngOptions,
    TavilyOptions,
    TrafilaturaOptions,
    options_model_for,
    validate_options,
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


def test_options_models_cover_six_providers():
    assert set(OPTIONS_MODELS) == {
        "ddg", "searxng", "exa", "tavily", "jina", "trafilatura",
    }
    for provider_type, model in OPTIONS_MODELS.items():
        assert options_model_for(provider_type) is model


def test_validate_options_returns_full_dict():
    assert validate_options("exa", {"include_domains": ["example.com"]}) == {
        **ExaOptions(include_domains=["example.com"]).model_dump(),
    }


def test_list_defaults_are_independent():
    a = ExaOptions()
    b = ExaOptions()
    a.include_domains.append("example.com")
    assert b.include_domains == []


def test_unknown_type_validate_options_is_noop():
    assert validate_options("nope", {"anything": 1}) == {"anything": 1}


def test_ddg_defaults():
    d = DdgOptions().model_dump()
    assert d["region"] is None
    assert d["safesearch"] == "moderate"
    assert d["timelimit"] == ""
    assert d["backend"] is None


def test_searxng_defaults():
    d = SearxngOptions().model_dump()
    assert d["categories"] == ["general"]
    assert d["language"] == "all"
    assert d["safesearch"] == "1"
    assert d["time_range"] == ""
    assert d["engines"] == []


def test_tavily_defaults():
    d = TavilyOptions().model_dump()
    assert d["search_depth"] == "basic"
    assert d["topic"] == "general"
    assert d["include_domains"] == []
    assert d["exclude_domains"] == []
    assert "include_answer" not in d
    assert d["include_raw_content"] is False
    assert d["days"] is None
    assert d["extract_depth"] == "basic"
    assert d["include_images"] is False


def test_tavily_include_answer_is_not_accepted_in_v1():
    with pytest.raises(ValidationError):
        TavilyOptions(include_answer=True)


def test_jina_defaults():
    d = JinaOptions().model_dump()
    assert d["target_selector"] is None
    assert d["wait_for_selector"] is None
    assert d["timeout_s"] is None
    assert d["no_cache"] is False


def test_trafilatura_defaults():
    d = TrafilaturaOptions().model_dump()
    assert d["favor_precision"] is False
    assert d["favor_recall"] is False
    assert d["deduplicate"] is False
    assert d["target_language"] is None


def test_enum_values_validated():
    with pytest.raises(ValidationError):
        DdgOptions(safesearch="nope")
    with pytest.raises(ValidationError):
        SearxngOptions(safesearch="9")


def test_jina_timeout_range():
    with pytest.raises(ValidationError):
        JinaOptions(timeout_s=0)
    with pytest.raises(ValidationError):
        JinaOptions(timeout_s=121)
    assert JinaOptions(timeout_s=120).timeout_s == 120
