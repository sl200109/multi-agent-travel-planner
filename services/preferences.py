"""
CLI、API、UI 和测试共用的输入归一化工具。

统一的构建函数可以避免各入口重复校验，
本身只负责请求整形，不承载业务逻辑。
"""

from __future__ import annotations

from models.schemas import TravelStyle, UserPreferences


def build_preferences(
    *,
    budget: float,
    departure_city: str,
    start_date: str,
    end_date: str,
    travel_style: str | TravelStyle = TravelStyle.COMFORT,
    num_travelers: int = 1,
    interests: list[str] | None = None,
    dietary_restrictions: list[str] | None = None,
    accessibility_needs: list[str] | None = None,
    notes: str = "",
    user_id: str = "default-user",
    session_id: str | None = None,
    enable_long_term_memory: bool = True,
) -> UserPreferences:
    """Create a validated UserPreferences object from plain inputs."""

    style = travel_style if isinstance(travel_style, TravelStyle) else TravelStyle(travel_style)
    payload = dict(
        budget=budget,
        departure_city=departure_city,
        start_date=start_date,
        end_date=end_date,
        travel_style=style,
        num_travelers=num_travelers,
        interests=interests or [],
        dietary_restrictions=dietary_restrictions or [],
        accessibility_needs=accessibility_needs or [],
        notes=notes,
        user_id=user_id,
        enable_long_term_memory=enable_long_term_memory,
    )
    if session_id:
        payload["session_id"] = session_id
    return UserPreferences(**payload)
