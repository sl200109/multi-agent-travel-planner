"""
负责整理用户输入的偏好 Agent。

这个 Agent 不直接做搜索，
它的作用更像是“把用户需求整理干净，再交给后面的 Agent”。
"""

from __future__ import annotations

from models.schemas import MessageRecord, PlanningEventType, PlanningState, TravelPlanState
from services.runtime import PlannerRuntime

from .base_agent import BaseAgent


class PreferenceAgent(BaseAgent):
    """负责输入归一化和记忆加载。"""

    name = "PreferenceAgent"

    async def execute(self, state: TravelPlanState, runtime: PlannerRuntime) -> TravelPlanState:
        # 整个规划流程必须先有用户偏好，没有就没法继续。
        if state.preferences is None:
            raise ValueError("preferences are required")

        preferences = state.preferences

        # 如果用户没有明确写兴趣标签，这里按旅行风格补一个默认值，
        # 这样后面的检索词不会太空。
        if not preferences.interests:
            preferences.interests = self._default_interests(preferences.travel_style.value)

        # 如果开启了长期记忆，就读取这个用户以前的出行偏好摘要。
        # 这一步的意义是：下一次规划时，模型不需要完全从零理解用户。
        if preferences.enable_long_term_memory:
            state.memory_context = await runtime.memory.load_user_context(preferences.user_id)

        # 把本次请求转成一条会话消息。
        # 后面通过 MessagesPlaceholder 传给大模型时，就能带上历史上下文。
        state.conversation_history.append(
            MessageRecord(
                role="user",
                content=(
                    f"请为用户规划一次从 {preferences.departure_city} 出发、"
                    f"预算 {preferences.budget:.0f} 元、风格为 {preferences.travel_style.value} 的旅行。"
                ),
            )
        )

        # 当前 Agent 结束后，状态流转到“推荐目的地”阶段。
        state.state = PlanningState.RECOMMENDING_DESTINATIONS

        # 发一个状态更新事件，便于界面看到这里做了什么。
        await runtime.emitter.emit(
            PlanningEventType.STATE_UPDATED,
            agent=self.name,
            message="用户偏好已整理完成",
            payload={"interests": preferences.interests, "memory_entries": len(state.memory_context)},
        )
        return state

    @staticmethod
    def _default_interests(style: str) -> list[str]:
        """根据旅行风格给出默认兴趣标签。

        这个映射非常适合初学者理解：
        它本质上就是“风格 -> 常见兴趣”的经验表。
        """

        mapping = {
            "budget": ["平价美食", "免费景点", "步行友好街区"],
            "comfort": ["经典景点", "本地美食", "文化体验"],
            "luxury": ["高端餐厅", "设计酒店", "精品体验"],
            "adventure": ["徒步", "户外活动", "自然风光"],
            "cultural": ["博物馆", "历史遗迹", "本地街区"],
            "relaxation": ["温泉", "风景", "慢旅行"],
        }
        return mapping.get(style, ["经典景点", "本地美食"])
