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