"""SearchHub aggregator backend for hermes-agent.

Thin passthrough client for a self-hosted SearchHub instance
(REST endpoints /v1/search and /v1/extract).
"""

from agent.web_search_provider import WebSearchProvider, get_provider_env


class SearchHubProvider(WebSearchProvider):
    name = "searchhub"

    def __init__(self) -> None:
        self._base = (get_provider_env("SEARCHHUB_URL") or "").rstrip("/")
        self._token = get_provider_env("SEARCHHUB_TOKEN") or ""

    @property
    def display_name(self) -> str:
        return "SearchHub (self-hosted aggregator)"

    def is_available(self) -> bool:
        return bool(self._base and self._token)

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    def _call(self, method: str, path: str, params: dict | None = None,
              json_body: dict | None = None, timeout: float = 30.0) -> dict:
        import httpx

        url = f"{self._base}{path}"
        try:
            if method == "GET":
                resp = httpx.get(url, params=params, headers=self._headers(), timeout=timeout)
            else:
                resp = httpx.post(url, json=json_body or {}, headers=self._headers(), timeout=timeout)
            body = resp.json()
        except Exception as e:
            return {"success": False, "error": str(e)}
        if resp.status_code != 200 or not isinstance(body, dict):
            return {"success": False, "error": body.get("error") if isinstance(body, dict) else f"http {resp.status_code}"}
        return body

    def search(self, query: str, limit: int = 5) -> dict:
        return self._call("GET", "/v1/search", params={"q": query, "limit": limit})

    def extract(self, urls, **kwargs) -> list:
        # Hermes 契约：extract 必须返回"每条 URL 一个 dict"的列表（见
        # agent/web_search_provider.py 的 ABC docstring），不是
        # {success, data} 信封——信封会被当成列表迭代，元素是字符串键，
        # 逐项 .get() 即抛 'str' object has no attribute 'get'。
        body = {"urls": list(urls)}
        for key in ("format", "include_raw", "max_chars"):
            if key in kwargs and kwargs[key] is not None:
                body[key] = kwargs[key]
        resp = self._call("POST", "/v1/extract", json_body=body, timeout=90.0)
        if not isinstance(resp, dict) or not resp.get("success"):
            error = resp.get("error", "extract failed") if isinstance(resp, dict) else str(resp)
            return [{"url": u, "title": "", "content": "", "raw_content": "",
                     "metadata": {}, "error": error} for u in urls]
        items = resp.get("data") or []
        out = []
        for it in items:
            if not isinstance(it, dict):
                out.append({"url": "", "title": "", "content": "", "raw_content": "",
                            "metadata": {}, "error": "malformed extract item"})
                continue
            out.append({
                "url": it.get("url", ""),
                "title": it.get("title", ""),
                "content": it.get("content", ""),
                "raw_content": it.get("raw_content", ""),
                "metadata": it.get("metadata") or {},
                "error": it.get("error"),
            })
        return out


def register(ctx) -> None:
    ctx.register_web_search_provider(SearchHubProvider())