import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.fixture
def server_params(data_dir: Path) -> StdioServerParameters:
    env = dict(os.environ)
    env["SEARCHHUB_DATA"] = str(data_dir)
    return StdioServerParameters(
        command=sys.executable, args=["-m", "searchhub.mcp"], env=env
    )


@asynccontextmanager
async def _session(server_params: StdioServerParameters):
    async with stdio_client(server_params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            yield s


async def test_initialize_and_list_tools(server_params):
    async with _session(server_params) as session:
        tools = await session.list_tools()
        names = [t.name for t in tools.tools]
        assert "web_search" in names
        assert "web_extract" in names


async def test_call_web_search_returns_json_string(server_params):
    async with _session(server_params) as session:
        result = await session.call_tool("web_search", {"query": "python"})
        # 无供应商配置 → success=false 的 JSON 字符串
        text = result.content[0].text
        data = json.loads(text)
        assert data["success"] is False
        assert "no search provider" in data["error"]


async def test_call_web_extract_returns_json_string(server_params):
    async with _session(server_params) as session:
        result = await session.call_tool("web_extract", {"urls": ["https://example.com"]})
        text = result.content[0].text
        data = json.loads(text)
        assert data["success"] is False  # 无 extract 供应商
