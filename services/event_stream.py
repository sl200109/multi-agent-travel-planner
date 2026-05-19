"""
规划事件流同时服务 SSE 接口和 Streamlit 进度展示。

事件会先写入全局 state，
也可以继续转发给监听器，避免重复实现流式逻辑。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from models.schemas import PlanningEvent, PlanningEventType, TravelPlanState

EventListener = Callable[[PlanningEvent], Awaitable[None]]


class PlanningEventEmitter:
    """Emit planning events in a single, reusable format."""

    def __init__(self, state: TravelPlanState, listener: Optional[EventListener] = None):
        self._state = state
        self._listener = listener

    async def emit(
        self,
        event_type: PlanningEventType,
        *,
        agent: str = "",
        message: str = "",
        payload: dict[str, object] | None = None,
    ) -> PlanningEvent:
        """Create an event, store it on state, and forward it if needed."""

        event = PlanningEvent(
            event_type=event_type,
            agent=agent,
            message=message,
            payload=payload or {},
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._state.event_log.append(event)
        if self._listener:
            await self._listener(event)
        return event
