"""
负责推荐目的地的 Agent。

这一层会先调用 Tavily 做真实检索，
再让 Qwen 把检索结果整理成结构化的目的地候选列表。
"""

from __future__ import annotations

from models.schemas import Destination, DestinationRecommendation, PlanningEventType, PlanningState, TravelPlanState
from prompts import destination_prompt
from services.qwen_client import to_langchain_messages
from services.runtime import PlannerRuntime

from .base_agent import BaseAgent


class DestinationAgent(BaseAgent):
    """根据用户偏好推荐目的地。"""

    name = "DestinationAgent"

    async def execute(self, state: TravelPlanState, runtime: PlannerRuntime) -> TravelPlanState:
        if state.preferences is None:
            raise ValueError("preferences are required")

        prefs = state.preferences

        # 把历史记忆压缩成一段文本，方便一起喂给模型。
        # 如果没有记忆，就给一个默认提示，避免字段为空。
        memory_summary = "\n".join(item.summary for item in state.memory_context) or "暂无历史记忆。"

        # 先构造检索词。
        # 这一段就是“我要去搜什么”的自然语言版本。
        query = (
            f"适合从{prefs.departure_city}出发、旅行风格为{prefs.travel_style.value}、"
            f"出行时间在{prefs.start_date}到{prefs.end_date}之间、预算约{prefs.budget:.0f}元、"
            f"兴趣包含{', '.join(prefs.interests)}的目的地推荐"
        )

        await runtime.emitter.emit(
            PlanningEventType.TOOL_CALLED,
            agent=self.name,
            message="开始搜索目的地候选",
            payload={"query": query},
        )
        print("开始进行目的地筛选")

        # 先走真实搜索，拿到事实材料。
        search = await runtime.tavily.search(query, topic="general")

        await runtime.emitter.emit(
            PlanningEventType.TOOL_RESULT,
            agent=self.name,
            message="目的地搜索完成",
            payload={"sources": [item.model_dump() for item in search.results]},
        )

        # 再把“用户偏好 + 历史记忆 + 搜索结果 + 会话历史”交给 Qwen，
        # 让模型输出结构化 JSON。
        data = await runtime.qwen.complete_json(
            destination_prompt(),
            {
                "preferences": prefs.model_dump_json(),
                "memory_context": memory_summary,
                "search_answer": search.answer,
                "search_sources": self._render_sources(search.results),
                "conversation_history": to_langchain_messages(state.conversation_history),
            },
        )

        # 把模型返回的 JSON 一条条转成系统内部的 Destination 对象。
        destinations = [
            Destination(
                city=str(item.get("city", "")),
                country=str(item.get("country", "")),
                description=str(item.get("description", "")),
                highlights=[str(x) for x in item.get("highlights", [])],
                reason=str(item.get("reason", "")),
                source_links=search.results,
            )
            for item in data.get("destinations", [])
            if item.get("city")
        ]
        if not destinations:
            raise ValueError("Qwen did not return any destination candidates")

        # 如果模型明确选了 selected_city，就优先用它；
        # 否则默认取第一名。
        selected_city = str(data.get("selected_city", destinations[0].city))
        selected = next((item for item in destinations if item.city == selected_city), destinations[0])

        state.destination_rec = DestinationRecommendation(
            destinations=destinations,
            selected=selected,
            reasoning=str(data.get("reasoning", "")),
            source_links=search.results,
        )

        # 目的地确定后，下一步就是查天气。
        state.state = PlanningState.FETCHING_WEATHER
        return state

    @staticmethod
    def _render_sources(sources: list) -> str:
        """把搜索来源拼成更适合提示词阅读的文本。"""

        return "\n".join(f"- {item.title}: {item.snippet} ({item.url})" for item in sources)
