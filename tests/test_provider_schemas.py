from searchhub.providers import PROVIDER_CLASSES
from searchhub.providers.schema import ProviderSchema, validate_provider_config


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