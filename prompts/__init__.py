"""
集中管理真实规划 Agent 使用的提示词模板。

把提示词统一放在这里，
后续调优时就不需要改动 Agent 控制流程。
"""

from .planner_prompts import (
    activity_prompt,
    destination_prompt,
    flight_prompt,
    hotel_prompt,
)

__all__ = [
    "activity_prompt",
    "destination_prompt",
    "flight_prompt",
    "hotel_prompt",
]
