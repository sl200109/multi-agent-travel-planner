"""
负责生成按天行程的活动 Agent。

这个 Agent 的核心任务是：
把零散的景点、餐厅、体验信息，
整理成用户真正能看的每日 itinerary。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from models.schemas import Activity, ActivitySearchResult, DayPlan, PlanningEventType, PlanningState, TravelPlanState
from prompts import activity_prompt
from services.qwen_client import to_langchain_messages
from services.runtime import PlannerRuntime

from .base_agent import BaseAgent


class ActivityAgent(BaseAgent):
    """根据真实搜索结果生成逐日行程。"""

    name = "ActivityAgent"

    async def execute(self, state: TravelPlanState, runtime: PlannerRuntime) -> TravelPlanState:
        if state.preferences is None or state.selected_destination is None:
            raise ValueError("preferences and destination are required")

        prefs = state.preferences
        destination = state.selected_destination

        # 这里搜索的不只是景点，也包括吃饭和体验类活动。
        query = (
            f"{destination.city}适合{prefs.travel_style.value}旅行风格的景点、美食和体验推荐，"
            f"重点关注{', '.join(prefs.interests)}，"
            f"适合{prefs.start_date}到{prefs.end_date}期间安排行程"
        )

        await runtime.emitter.emit(
            PlanningEventType.TOOL_CALLED,
            agent=self.name,
            message="开始搜索活动",
            payload={"query": query},
        )

        search = await runtime.tavily.search(query, topic="general")

        await runtime.emitter.emit(
            PlanningEventType.TOOL_RESULT,
            agent=self.name,
            message="活动搜索完成",
            payload={"sources": [item.model_dump() for item in search.results]},
        )

        weather_text = state.weather_result.raw_text if state.weather_result else "暂无天气信息。"

        data = await runtime.qwen.complete_json(
            activity_prompt(),
            {
                "preferences": prefs.model_dump_json(),
                "destination": destination.model_dump_json(),
                "weather": weather_text,
                "search_answer": search.answer,
                "search_sources": self._render_sources(search.results),
                "conversation_history": to_langchain_messages(state.conversation_history),
            },
        )

        # 根据用户日期范围，先算出合法日期列表。
        # 如果模型没返回日期，我们就用这里的结果兜底。
        valid_dates = self._travel_dates(prefs.start_date, prefs.end_date)
        day_plans: list[DayPlan] = []

        for index, item in enumerate(data.get("day_plans", [])):
            day_date = item.get("date") or valid_dates[min(index, len(valid_dates) - 1)]

            # 把一天中的各个活动转成内部 Activity 对象。
            activities = [
                Activity(
                    name=str(activity.get("name", "")),
                    category=str(activity.get("category", "sightseeing")),
                    location=str(activity.get("location", destination.city)),
                    duration_hours=float(activity.get("duration_hours", 2.0) or 2.0),
                    price=float(activity.get("price", 0) or 0),
                    description=str(activity.get("description", "")),
                    time_slot=str(activity.get("time_slot", "")),
                    source_links=search.results,
                )
                for activity in item.get("activities", [])
                if activity.get("name")
            ]

            # 每个 DayPlan 表示“某一天的完整安排”。
            day_plans.append(
                DayPlan(
                    date=str(day_date),
                    summary=str(item.get("summary", "")),
                    day_cost=float(item.get("day_cost", sum(a.price for a in activities)) or 0),
                    activities=activities,
                )
            )

        if not day_plans:
            raise ValueError("Qwen did not return any itinerary days")

        # 汇总整个行程的活动总成本。
        total_cost = sum(day.day_cost for day in day_plans)

        state.activity_result = ActivitySearchResult(
            day_plans=day_plans,
            total_activity_cost=total_cost,
            source_links=search.results,
            disclaimer=str(data.get("disclaimer", "")),
        )

        # 行程生成完成后，就可以进入预算评估阶段。
        state.state = PlanningState.BUDGET_CHECKING
        return state

    @staticmethod
    def _travel_dates(start: str, end: str) -> list[str]:
        """把开始日期到结束日期展开成每天的日期列表。"""

        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        days = max((end_dt - start_dt).days, 1)
        return [(start_dt + timedelta(days=index)).strftime("%Y-%m-%d") for index in range(days)]

    @staticmethod
    def _render_sources(sources: list) -> str:
        """把搜索来源格式化成提示词文本。"""

        return "\n".join(f"- {item.title}: {item.snippet} ({item.url})" for item in sources)
