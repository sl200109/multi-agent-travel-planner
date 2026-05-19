"""
负责做预算评估的 Agent。

这个 Agent 不负责搜索，它只负责“算账”和“提建议”。
也就是把前面各个 Agent 的结果收拢起来做最后判断。
"""

from __future__ import annotations

from models.schemas import BudgetBreakdown, PlanningState, TravelPlanState
from services.runtime import PlannerRuntime

from .base_agent import BaseAgent


class BudgetAgent(BaseAgent):
    """汇总费用并给出预算建议。"""

    name = "BudgetAgent"

    async def execute(self, state: TravelPlanState, runtime: PlannerRuntime) -> TravelPlanState:
        if state.preferences is None:
            raise ValueError("preferences are required")

        budget = state.preferences.budget

        # 这里分别取出交通、酒店、活动三块的费用。
        # 如果某块结果还不存在，就按 0 处理。
        flight_cost = state.flight_result.total_flight_cost if state.flight_result else 0.0
        hotel_cost = state.hotel_result.total_hotel_cost if state.hotel_result else 0.0
        activity_cost = state.activity_result.total_activity_cost if state.activity_result else 0.0

        # 总价 = 三块费用相加。
        total = flight_cost + hotel_cost + activity_cost

        # remaining > 0 说明预算还有剩余，< 0 说明超支。
        remaining = budget - total
        within_budget = remaining >= 0
        over_amount = max(0.0, -remaining)

        suggestions = []
        if not within_budget:
            # 如果超支，就按“活动 -> 酒店 -> 交通”的顺序给削减建议。
            if activity_cost > 0:
                suggestions.append("减少高价体验项目，每天保留一个核心活动即可。")
            if hotel_cost > 0:
                suggestions.append("可以改住稍远一点的区域，或者下调酒店档次。")
            if flight_cost > 0:
                suggestions.append("可以比较不同站点、不同日期，或选择中转/替代交通。")
        else:
            suggestions.append("当前预算基本可行，但下单前仍建议再次确认实时价格。")

        state.budget_breakdown = BudgetBreakdown(
            flight_cost=flight_cost,
            hotel_cost=hotel_cost,
            activity_cost=activity_cost,
            total_cost=total,
            budget=budget,
            remaining=remaining,
            is_within_budget=within_budget,
            over_budget_amount=over_amount,
            suggestions=suggestions,
            disclaimer="预算结果基于真实搜索线索和模型估算，下单前请再次核对实时价格。",
        )

        # 预算阶段结束后，整个流程就算完成了。
        state.state = PlanningState.COMPLETED
        return state
