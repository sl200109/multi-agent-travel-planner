"""
负责给出交通建议的 Agent。

这里虽然名字叫 FlightAgent，
但当前版本本质上是在做“交通方案建议”，
不一定真的只限于飞机。
"""

from __future__ import annotations

from models.schemas import FlightOption, FlightSearchResult, PlanningEventType, PlanningState, TravelPlanState
from prompts import flight_prompt
from services.qwen_client import to_langchain_messages
from services.runtime import PlannerRuntime

from .base_agent import BaseAgent


class FlightAgent(BaseAgent):
    """根据真实搜索结果生成交通建议。"""

    name = "FlightAgent"

    async def execute(self, state: TravelPlanState, runtime: PlannerRuntime) -> TravelPlanState:
        if state.preferences is None or state.selected_destination is None:
            raise ValueError("preferences and destination are required")

        prefs = state.preferences
        destination = state.selected_destination

        # 这里的 query 会明确告诉搜索工具：
        # 出发地是谁、目的地是谁、时间是什么、预算多少、想要什么样的交通建议。
        query = (
            f"从{prefs.departure_city}到{destination.city}的交通方案推荐，"
            f"出行时间约为{prefs.start_date}到{prefs.end_date}，"
            f"{prefs.num_travelers}位出行，预算约{prefs.budget:.0f}元，"
            f"请优先给出实用的购票建议和大致价格范围"
        )

        await runtime.emitter.emit(
            PlanningEventType.TOOL_CALLED,
            agent=self.name,
            message="开始搜索交通方案",
            payload={"query": query},
        )

        # 第一步：真实搜索。
        search = await runtime.tavily.search(query, topic="general")

        await runtime.emitter.emit(
            PlanningEventType.TOOL_RESULT,
            agent=self.name,
            message="交通搜索完成",
            payload={"sources": [item.model_dump() for item in search.results]},
        )

        # 第二步：让模型整理搜索结果。
        data = await runtime.qwen.complete_json(
            flight_prompt(),
            {
                "preferences": prefs.model_dump_json(),
                "destination": destination.model_dump_json(),
                "search_answer": search.answer,
                "search_sources": self._render_sources(search.results),
                "conversation_history": to_langchain_messages(state.conversation_history),
            },
        )

        # 把模型输出转成内部统一的 FlightOption。
        options = [
            FlightOption(
                label=str(item.get("label", "")),
                summary=str(item.get("summary", "")),
                route=str(item.get("route", "")),
                airline_hint=str(item.get("airline_hint", "")),
                estimated_roundtrip_cost=float(item.get("estimated_roundtrip_cost", 0) or 0),
                duration_hint=str(item.get("duration_hint", "")),
                booking_advice=str(item.get("booking_advice", "")),
                source_links=search.results,
                disclaimer=str(data.get("disclaimer", "")),
            )
            for item in data.get("options", [])
            if item.get("label")
        ]
        if not options:
            raise ValueError("Qwen did not return any transport options")

        # 如果模型点名推荐某个 label，就取它；
        # 否则默认用第一项。
        recommended_label = str(data.get("recommended_label", options[0].label))
        recommended = next((item for item in options if item.label == recommended_label), options[0])

        state.flight_result = FlightSearchResult(
            options=options,
            recommended=recommended,
            total_flight_cost=recommended.estimated_roundtrip_cost,
            disclaimer=str(data.get("disclaimer", "")),
        )

        # print(state.flight_result)

        # 交通建议结束后，下一步开始搜索酒店。
        state.state = PlanningState.SEARCHING_HOTELS
        return state

    @staticmethod
    def _render_sources(sources: list) -> str:
        """把搜索来源转成适合给模型看的长文本。"""

        return "\n".join(f"- {item.title}: {item.snippet} ({item.url})" for item in sources)
