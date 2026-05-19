"""
面向真实架构形态的集成风格测试。

测试会使用假的服务客户端，
在不访问外网的前提下验证主链路、记忆和流式行为。
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from models.schemas import PlanningEventType, SearchResponse, SourceLink, TravelPlanState, WeatherResult
from orchestrator import TravelPlanner
from services import JsonMemoryStore, build_preferences


class FakeTavilySearchClient:
    async def search(self, query: str, **kwargs) -> SearchResponse:
        return SearchResponse(
            query=query,
            answer=query,
            results=[
                SourceLink(
                    title="Example source",
                    url="https://example.com",
                    snippet=f"Snippet for {query}",
                )
            ],
        )


class FakeWeatherClient:
    async def get_weather(self, city: str) -> WeatherResult:
        return WeatherResult(city=city, description="Sunny", temperature_c="24", raw_text=f"{city} current weather: Sunny, 24C")


class FakeQwenClient:
    async def complete_json(self, prompt, variables):
        if "memory_context" in variables:
            return {
                "destinations": [
                    {
                        "city": "Seoul",
                        "country": "South Korea",
                        "description": "Easy city trip with food and culture.",
                        "highlights": ["Palace", "Street food", "Design district"],
                        "reason": "Fits the budget and interests.",
                    }
                ],
                "selected_city": "Seoul",
                "reasoning": "Best match for this test request.",
            }
        if "budget" in variables and "destination" in variables and "preferences" in variables and "search_answer" not in variables:
            return {"summary": "User likes comfort trips with food and culture."}
        search_answer = str(variables.get("search_answer", ""))
        if "交通方案" in search_answer or "高铁" in search_answer or "航班" in search_answer:
            return {
                "options": [
                    {
                        "label": "Direct flight",
                        "summary": "Fastest option with one airline recommendation.",
                        "route": "Shanghai -> Seoul",
                        "airline_hint": "Example Air",
                        "estimated_roundtrip_cost": 2800,
                        "duration_hint": "2h",
                        "booking_advice": "Book 2-3 weeks ahead.",
                    }
                ],
                "recommended_label": "Direct flight",
                "disclaimer": "Estimated from search results.",
            }
        if "酒店" in search_answer or "住宿" in search_answer:
            return {
                "hotels": [
                    {
                        "name": "Central Stay",
                        "area": "Jongno",
                        "summary": "Good access to sights and food.",
                        "nightly_price_text": "700-900 CNY per night",
                        "estimated_total_cost": 3200,
                        "amenities": ["WiFi", "Breakfast"],
                    }
                ],
                "recommended_name": "Central Stay",
                "disclaimer": "Reference pricing only.",
            }
        return {
            "day_plans": [
                {
                    "date": "2026-05-01",
                    "summary": "Historic core and food crawl.",
                    "day_cost": 350,
                    "activities": [
                        {
                            "name": "Palace visit",
                            "category": "sightseeing",
                            "location": "Seoul",
                            "duration_hours": 2,
                            "price": 60,
                            "description": "Morning palace visit.",
                            "time_slot": "morning",
                        },
                        {
                            "name": "Market lunch",
                            "category": "food",
                            "location": "Seoul",
                            "duration_hours": 1.5,
                            "price": 90,
                            "description": "Local lunch.",
                            "time_slot": "afternoon",
                        },
                    ],
                }
            ],
            "disclaimer": "Activities are planning suggestions.",
        }


@pytest.fixture
def planner():
    memory_dir = Path("tests_runtime_memory") / uuid4().hex
    memory_dir.mkdir(parents=True, exist_ok=True)
    return TravelPlanner(
        qwen=FakeQwenClient(),
        tavily=FakeTavilySearchClient(),
        weather=FakeWeatherClient(),
        memory=JsonMemoryStore(memory_dir),
    )


def test_build_preferences_sets_defaults():
    prefs = build_preferences(
        budget=10000,
        departure_city="Shanghai",
        start_date="2026-05-01",
        end_date="2026-05-05",
        travel_style="comfort",
    )
    assert prefs.travel_style.value == "comfort"
    assert prefs.user_id == "default-user"
    assert prefs.session_id


@pytest.mark.asyncio
async def test_planner_produces_full_state(planner):
    prefs = build_preferences(
        budget=12000,
        departure_city="Shanghai",
        start_date="2026-05-01",
        end_date="2026-05-05",
        travel_style="comfort",
        interests=["food", "culture"],
        user_id="tester",
    )
    state = await planner.plan(prefs)
    assert state.selected_destination is not None
    assert state.weather_result is not None
    assert state.flight_result is not None
    assert state.hotel_result is not None
    assert state.activity_result is not None
    assert state.budget_breakdown is not None
    assert state.budget_breakdown.total_cost > 0


@pytest.mark.asyncio
async def test_stream_emits_final_plan(planner):
    prefs = build_preferences(
        budget=12000,
        departure_city="Shanghai",
        start_date="2026-05-01",
        end_date="2026-05-05",
        travel_style="comfort",
        user_id="stream-user",
    )
    events = [event async for event in planner.stream(prefs)]
    assert any(event.event_type == PlanningEventType.AGENT_STARTED for event in events)
    final_event = next(event for event in events if event.event_type == PlanningEventType.FINAL_PLAN)
    state = TravelPlanState(**final_event.payload["state"])
    assert state.selected_destination is not None
    assert state.budget_breakdown is not None


@pytest.mark.asyncio
async def test_long_term_memory_is_saved_and_loaded(planner):
    first = build_preferences(
        budget=10000,
        departure_city="Shanghai",
        start_date="2026-05-01",
        end_date="2026-05-05",
        travel_style="comfort",
        user_id="memory-user",
    )
    await planner.plan(first)

    second = build_preferences(
        budget=9000,
        departure_city="Shanghai",
        start_date="2026-06-01",
        end_date="2026-06-04",
        travel_style="comfort",
        user_id="memory-user",
    )
    state = await planner.plan(second)
    assert len(state.memory_context) >= 1
