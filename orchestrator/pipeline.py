"""
旅行规划的主编排链路。

这里统一承接各个 Agent 的执行顺序，
并输出可复用的事件流给 API 和 Streamlit 界面。
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Awaitable, Callable, Optional

from agents import ActivityAgent, BudgetAgent, DestinationAgent, FlightAgent, HotelAgent, PreferenceAgent, WeatherAgent
from config.settings import settings
from models.schemas import PlanningEvent, PlanningEventType, PlanningState, TravelPlanState, UserPreferences
from services import JsonMemoryStore, PlanningEventEmitter, PlannerRuntime, QwenClient, TavilySearchClient, WeatherClient
from services.preferences import build_preferences

EventListener = Callable[[PlanningEvent], Awaitable[None]]


class TravelPlanner:
    """Planner entrypoint for normal and streaming execution."""

    def __init__(
        self,
        *,
        qwen: QwenClient | None = None,
        tavily: TavilySearchClient | None = None,
        weather: WeatherClient | None = None,
        memory: JsonMemoryStore | None = None,
    ):
        self.qwen = qwen or QwenClient()
        self.tavily = tavily or TavilySearchClient()
        self.weather = weather or WeatherClient()
        self.memory = memory or JsonMemoryStore()
        self.agents = [
            PreferenceAgent(),
            DestinationAgent(),
            WeatherAgent(),
            FlightAgent(),
            HotelAgent(),
            ActivityAgent(),
            BudgetAgent(),
        ]

    async def plan(self, preferences: UserPreferences) -> TravelPlanState:
        """Run the planner and return the final state."""

        state = TravelPlanState(preferences=preferences)
        emitter = PlanningEventEmitter(state)
        await self._run(state, emitter)
        return state

    async def stream(self, preferences: UserPreferences) -> AsyncIterator[PlanningEvent]:
        """Run the planner and yield incremental planning events."""

        state = TravelPlanState(preferences=preferences)
        queue: asyncio.Queue[PlanningEvent | None] = asyncio.Queue()

        async def listener(event: PlanningEvent) -> None:
            await queue.put(event)

        emitter = PlanningEventEmitter(state, listener=listener)

        async def runner() -> None:
            try:
                await self._run(state, emitter)
            finally:
                await queue.put(None)

        task = asyncio.create_task(runner())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            await task

    async def _run(self, state: TravelPlanState, emitter: PlanningEventEmitter) -> TravelPlanState:
        runtime = PlannerRuntime(
            settings=settings,
            qwen=self.qwen,
            tavily=self.tavily,
            weather=self.weather,
            memory=self.memory,
            emitter=emitter,
        )
        for agent in self.agents:
            state = await agent.run(state, runtime)
            if state.state == PlanningState.FAILED:
                break

        if state.state == PlanningState.COMPLETED:
            memory_entry = await self.memory.summarize_and_save(state=state, qwen=self.qwen)
            if memory_entry:
                state.memory_context.append(memory_entry)

        await emitter.emit(
            PlanningEventType.FINAL_PLAN,
            agent="TravelPlanner",
            message="Planning finished",
            payload={"state": state.model_dump(mode="json")},
        )
        return state


async def quick_plan(
    *,
    budget: float = 10000,
    departure: str = "Beijing",
    start: str = "2026-05-01",
    end: str = "2026-05-05",
    style: str = "comfort",
    travelers: int = 1,
    interests: list[str] | None = None,
    user_id: str = "default-user",
) -> TravelPlanState:
    """Convenience entrypoint for CLI and tests."""

    preferences = build_preferences(
        budget=budget,
        departure_city=departure,
        start_date=start,
        end_date=end,
        travel_style=style,
        num_travelers=travelers,
        interests=interests,
        user_id=user_id,
    )
    return await TravelPlanner().plan(preferences)
