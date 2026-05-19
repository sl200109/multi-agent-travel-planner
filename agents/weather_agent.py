"""
负责查询目的地天气的 Agent。

它很简单，但很重要：
后续酒店和活动规划都会参考这一步得到的天气信息。
"""

from __future__ import annotations

from models.schemas import PlanningEventType, PlanningState, TravelPlanState
from services.runtime import PlannerRuntime

from .base_agent import BaseAgent


class WeatherAgent(BaseAgent):
    """查询所选目的地的实时天气。"""

    name = "WeatherAgent"

    async def execute(self, state: TravelPlanState, runtime: PlannerRuntime) -> TravelPlanState:
        # 天气一定是针对“已经选中的目的地”来查的。
        destination = state.selected_destination
        if destination is None:
            raise ValueError("selected destination is required before weather lookup")

        await runtime.emitter.emit(
            PlanningEventType.TOOL_CALLED,
            agent=self.name,
            message="开始查询天气",
            payload={"city": destination.city},
        )

        # 这里调用的是 weather_client，对外部 wttr.in 发请求。
        weather = await runtime.weather.get_weather(destination.city)
        state.weather_result = weather

        await runtime.emitter.emit(
            PlanningEventType.TOOL_RESULT,
            agent=self.name,
            message=weather.raw_text,
            payload=weather.model_dump(),
        )

        # 天气有了，下一步就可以研究交通方案了。
        state.state = PlanningState.SEARCHING_TRANSPORT
        return state
