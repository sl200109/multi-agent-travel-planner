"""
供目的地、酒店、交通和活动搜索使用的异步 Tavily 封装。

客户端会把原始响应整理成统一的来源链接结构，
避免其他模块直接依赖 Tavily 的原始字段。
"""

from __future__ import annotations

import httpx

from config.settings import settings
from models.schemas import SearchResponse, SourceLink


class TavilySearchClient:
    """Minimal async Tavily client."""

    def __init__(self, api_key: str | None = None, timeout: int | None = None):
        self.api_key = api_key or settings.TAVILY_API_KEY
        self.timeout = timeout or settings.HTTP_TIMEOUT

    async def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        topic: str = "general",
        search_depth: str = "basic",
    ) -> SearchResponse:
        """Run a Tavily search and normalize the result payload."""

        if not self.api_key:
            raise ValueError("TAVILY_API_KEY is not set")

        payload = {
            "api_key": self.api_key,
            "query": query,
            "topic": topic,
            "search_depth": search_depth,
            "max_results": max_results or settings.SEARCH_MAX_RESULTS,
            "include_answer": True,
            "include_raw_content": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post("https://api.tavily.com/search", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        links = [
            SourceLink(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
            )
            for item in data.get("results", [])
        ]
        return SearchResponse(query=query, answer=data.get("answer", ""), results=links)
