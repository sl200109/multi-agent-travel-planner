"""
基于 wttr.in 的异步天气客户端。

返回值会整理成统一的小型结构，
同时保留便于日志和界面展示的原始文本。
"""

from __future__ import annotations

import httpx

from config.settings import settings
from models.schemas import WeatherResult


class WeatherClient:
    """Minimal async weather client."""

    def __init__(self, base_url: str | None = None, timeout: int | None = None):
        self.base_url = (base_url or settings.WTTR_BASE_URL).rstrip("/")
        self.timeout = timeout or settings.HTTP_TIMEOUT

    async def get_weather(self, city: str) -> WeatherResult:
        """Fetch current weather using wttr.in JSON output."""

        url = f"{self.base_url}/{city}?format=j1"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        current = data["current_condition"][0]
        description = current["weatherDesc"][0]["value"]
        temp_c = current["temp_C"]
        raw_text = f"{city} current weather: {description}, {temp_c}C"
        return WeatherResult(
            city=city,
            description=description,
            temperature_c=str(temp_c),
            raw_text=raw_text,
        )
