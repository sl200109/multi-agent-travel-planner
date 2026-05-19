"""
提供同步和流式规划能力的 FastAPI 应用。

同一套规划主链路同时服务普通接口和 SSE 事件流，
便于前端和调试工具复用。
"""

from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config.settings import settings
from models.schemas import TravelPlanState
from orchestrator import TravelPlanner
from services import build_preferences

app = FastAPI(
    title="Travel Planner",
    description="Real-data multi-agent travel planner with streaming and memory",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

planner = TravelPlanner()


class PlanRequest(BaseModel):
    """Incoming API payload."""

    budget: float = Field(10000, gt=0)
    departure_city: str = Field("Beijing")
    start_date: str = Field("2026-05-01")
    end_date: str = Field("2026-05-05")
    travel_style: str = Field("comfort")
    num_travelers: int = Field(1, ge=1)
    interests: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    accessibility_needs: list[str] = Field(default_factory=list)
    notes: str = ""
    user_id: str = "api-user"
    session_id: str | None = None
    enable_long_term_memory: bool = True


class PlanSummary(BaseModel):
    """Compact response shape for the sync endpoint."""

    destination: str = ""
    country: str = ""
    weather: str = ""
    flight_cost: float = 0
    hotel_cost: float = 0
    activity_cost: float = 0
    total_cost: float = 0
    budget: float = 0
    within_budget: bool = True
    hotel_name: str = ""
    days: int = 0
    highlights: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _build_request_preferences(req: PlanRequest):
    try:
        return build_preferences(
            budget=req.budget,
            departure_city=req.departure_city,
            start_date=req.start_date,
            end_date=req.end_date,
            travel_style=req.travel_style,
            num_travelers=req.num_travelers,
            interests=req.interests,
            dietary_restrictions=req.dietary_restrictions,
            accessibility_needs=req.accessibility_needs,
            notes=req.notes,
            user_id=req.user_id,
            session_id=req.session_id,
            enable_long_term_memory=req.enable_long_term_memory,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "travel-planner", "mode": "real-data"}


@app.post("/api/plan", response_model=PlanSummary)
async def create_plan(req: PlanRequest):
    preferences = _build_request_preferences(req)
    state: TravelPlanState = await planner.plan(preferences)

    destination = state.selected_destination
    budget = state.budget_breakdown
    return PlanSummary(
        destination=destination.city if destination else "",
        country=destination.country if destination else "",
        weather=state.weather_result.raw_text if state.weather_result else "",
        flight_cost=budget.flight_cost if budget else 0,
        hotel_cost=budget.hotel_cost if budget else 0,
        activity_cost=budget.activity_cost if budget else 0,
        total_cost=budget.total_cost if budget else 0,
        budget=budget.budget if budget else req.budget,
        within_budget=budget.is_within_budget if budget else False,
        hotel_name=state.hotel_result.recommended.name if state.hotel_result and state.hotel_result.recommended else "",
        days=len(state.activity_result.day_plans) if state.activity_result else 0,
        highlights=destination.highlights if destination else [],
        warnings=state.error_messages,
    )


@app.post("/api/plan/full")
async def create_plan_full(req: PlanRequest):
    preferences = _build_request_preferences(req)
    state = await planner.plan(preferences)
    return state.model_dump(mode="json")


async def _event_stream(req: PlanRequest) -> AsyncIterator[str]:
    preferences = _build_request_preferences(req)
    async for event in planner.stream(preferences):
        payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
        yield f"event: {event.event_type.value}\ndata: {payload}\n\n"


@app.post("/api/plan/stream")
async def create_plan_stream(req: PlanRequest):
    return StreamingResponse(_event_stream(req), media_type="text/event-stream")


def start():
    import uvicorn

    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)


if __name__ == "__main__":
    start()
