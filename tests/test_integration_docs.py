import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_skill_has_frontmatter():
    skill = (ROOT / "integrations/skill/searchhub-web/SKILL.md").read_text()
    assert skill.startswith("---\n")
    assert "name: searchhub-web" in skill.split("---")[1]
    assert "description:" in skill.split("---")[1]


def test_skill_mentions_both_endpoints():
    skill = (ROOT / "integrations/skill/searchhub-web/SKILL.md").read_text()
    assert "/v1/search" in skill
    assert "/v1/extract" in skill
    assert "SEARCHHUB_URL" in skill and "SEARCHHUB_TOKEN" in skill


def test_tool_json_definitions_valid():
    for name in ("web_search", "web_extract"):
        path = ROOT / "integrations/tools" / f"{name}.json"
        doc = json.loads(path.read_text())
        assert doc["type"] == "function"
        fn = doc["function"]
        assert fn["name"] == name
        props = fn["parameters"]["properties"]
        assert "query" in props or "urls" in props
        assert fn["parameters"]["required"]


def test_tools_readme_covers_agents():
    readme = (ROOT / "integrations/tools/README.md").read_text()
    for agent in ("Claude Code", "Codex", "Cursor", "OpenCode", "Gemini CLI"):
        assert agent in readme
    assert "/mcp" in readme


def test_integrations_overview_readme():
    readme = (ROOT / "integrations/README.md").read_text()
    for section in ("hermes", "skill", "tools", "MCP"):
        assert section in readme