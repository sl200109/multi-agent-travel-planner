"""
负责生成住宿建议的 Agent。

当前版本不是直接对接酒店预订 API，
而是基于真实搜索结果生成“可参考的住宿方案”。
"""

from __future__ import annotations

from datetime import datetime

from models.schemas import HotelOption, HotelSearchResult, PlanningEventType, PlanningState, TravelPlanState
from prompts import hotel_prompt
from services.qwen_client import to_langchain_messages
from services.runtime import PlannerRuntime

from .base_agent import BaseAgent


class HotelAgent(BaseAgent):
    """根据真实搜索结果构建酒店建议。"""

    name = "HotelAgent"

    async def execute(self, state: TravelPlanState, runtime: PlannerRuntime) -> TravelPlanState:
        if state.preferences is None or state.selected_destination is None:
            raise ValueError("preferences and destination are required")

        prefs = state.preferences
        destination = state.selected_destination

        # 先计算住几晚。
        # 这个结果后面既会用于提示词，也会用于总价估算。
        nights = self._calc_nights(prefs.start_date, prefs.end_date)

        # 再构造酒店搜索词。
        query = (
            f"{destination.city}酒店推荐，旅行风格为{prefs.travel_style.value}，"
            f"出行日期约为{prefs.start_date}到{prefs.end_date}，"
            f"{prefs.num_travelers}位出行，预算约{prefs.budget:.0f}元，"
            f"请给出适合入住的区域、价格区间和住宿建议"
        )

        await runtime.emitter.emit(
            PlanningEventType.TOOL_CALLED,
            agent=self.name,
            message="开始搜索酒店",
            payload={"query": query},
        )

        search = await runtime.tavily.search(query, topic="general")

        await runtime.emitter.emit(
            PlanningEventType.TOOL_RESULT,
            agent=self.name,
            message="酒店搜索完成",
            payload={"sources": [item.model_dump() for item in search.results]},
        )

        # 如果天气还没查到，就给一个占位文本。
        weather_text = state.weather_result.raw_text if state.weather_result else "暂无天气信息。"

        data = await runtime.qwen.complete_json(
            hotel_prompt(),
            {
                "preferences": prefs.model_dump_json(),
                "destination": destination.model_dump_json(),
                "weather": weather_text,
                "search_answer": search.answer,
                "search_sources": self._render_sources(search.results),
                "conversation_history": to_langchain_messages(state.conversation_history),
            },
        )

        # 把模型输出变成系统内部的酒店对象。
        hotels = [
            HotelOption(
                name=str(item.get("name", "")),
                area=str(item.get("area", "")),
                summary=str(item.get("summary", "")),
                nightly_price_text=str(item.get("nightly_price_text", "")),
                estimated_total_cost=float(item.get("estimated_total_cost", 0) or 0),
                amenities=[str(x) for x in item.get("amenities", [])],
                source_links=search.results,
                disclaimer=str(data.get("disclaimer", "")),
            )
            for item in data.get("hotels", [])
            if item.get("name")
        ]
        if not hotels:
            raise ValueError("Qwen did not return any hotel suggestions")

        recommended_name = str(data.get("recommended_name", hotels[0].name))
        recommended = next((item for item in hotels if item.name == recommended_name), hotels[0])

        state.hotel_result = HotelSearchResult(
            hotels=hotels,
            recommended=recommended,
            total_nights=nights,
            total_hotel_cost=recommended.estimated_total_cost,
            disclaimer=str(data.get("disclaimer", "")),
        )

        # 酒店建议完成后，下一步开始排每日行程。
        state.state = PlanningState.PLANNING_ACTIVITIES
        return state

    @staticmethod
    def _calc_nights(start: str, end: str) -> int:
        """根据开始日期和结束日期计算住宿晚数。"""

        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        return max((end_dt - start_dt).days, 1)

    @staticmethod
    def _render_sources(sources: list) -> str:
        """把搜索来源拼成适合放进提示词的文本。"""

        return "\n".join(f"- {item.title}: {item.snippet} ({item.url})" for item in sources)
