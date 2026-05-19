"""
传递给每个 Agent 的运行时依赖容器。

通过依赖注入统一收拢客户端和辅助对象，
既方便测试，也避免隐藏的全局状态。
"""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import Settings
from services.event_stream import PlanningEventEmitter
from services.memory_store import JsonMemoryStore
from services.qwen_client import QwenClient
from services.tavily_client import TavilySearchClient
from services.weather_client import WeatherClient


@dataclass
class PlannerRuntime:
    """Shared runtime dependencies for one planning run."""

    settings: Settings
    qwen: QwenClient
    tavily: TavilySearchClient
    weather: WeatherClient
    memory: JsonMemoryStore
    emitter: PlanningEventEmitter
