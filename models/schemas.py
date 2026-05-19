"""
真实旅行规划器的核心数据模型。

这些 schema 用来对齐 API、UI、Agent、记忆层和事件流，
注释保持简短，方便快速浏览。
"""

from __future__ import annotations

from enum import Enum
from datetime import datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class TravelStyle(str, Enum):
    """Supported planning styles."""

    BUDGET = "budget"
    COMFORT = "comfort"
    LUXURY = "luxury"
    ADVENTURE = "adventure"
    CULTURAL = "cultural"
    RELAXATION = "relaxation"


class PlanningState(str, Enum):
    """High-level pipeline stages."""

    COLLECTING_PREFERENCES = "collecting_preferences"
    RECOMMENDING_DESTINATIONS = "recommending_destinations"
    FETCHING_WEATHER = "fetching_weather"
    SEARCHING_TRANSPORT = "searching_transport"
    SEARCHING_HOTELS = "searching_hotels"
    PLANNING_ACTIVITIES = "planning_activities"
    BUDGET_CHECKING = "budget_checking"
    COMPLETED = "completed"
    FAILED = "failed"


class PlanningEventType(str, Enum):
    """Streaming event types used by API and UI."""

    AGENT_STARTED = "agent_started"
    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"
    AGENT_COMPLETED = "agent_completed"
    STATE_UPDATED = "state_updated"
    FINAL_PLAN = "final_plan"
    ERROR = "error"


class UserPreferences(BaseModel):
    """Normalized user input for one planning request."""

    budget: float = Field(..., gt=0)
    travel_style: TravelStyle = Field(default=TravelStyle.COMFORT)
    departure_city: str
    start_date: str
    end_date: str
    num_travelers: int = Field(default=1, ge=1)
    interests: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    accessibility_needs: list[str] = Field(default_factory=list)
    notes: str = ""
    user_id: str = "default-user"
    session_id: str = Field(default_factory=lambda: uuid4().hex)
    enable_long_term_memory: bool = True

    @model_validator(mode="after")
    def validate_dates(self) -> "UserPreferences":
        start_dt = datetime.strptime(self.start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(self.end_date, "%Y-%m-%d")
        if end_dt < start_dt:
            raise ValueError("end_date must be on or after start_date")
        return self


class SourceLink(BaseModel):
    """Simple source reference returned by search tools."""

    title: str
    url: str
    snippet: str = ""


class SearchResponse(BaseModel):
    """Normalized Tavily search payload."""

    query: str
    answer: str = ""
    results: list[SourceLink] = Field(default_factory=list)


class MessageRecord(BaseModel):
    """Serializable short-term memory record."""

    role: str
    content: str


class MemoryEntry(BaseModel):
    """Long-term memory entry stored on disk."""

    user_id: str
    session_id: str
    summary: str
    preferences_snapshot: dict[str, object] = Field(default_factory=dict)
    created_at: str


class WeatherResult(BaseModel):
    """Current weather result from wttr.in."""

    city: str
    description: str
    temperature_c: str
    source: str = "wttr.in"
    raw_text: str = ""


class Destination(BaseModel):
    """Destination candidate backed by real search sources."""

    city: str
    country: str = ""
    description: str = ""
    highlights: list[str] = Field(default_factory=list)
    reason: str = ""
    source_links: list[SourceLink] = Field(default_factory=list)


class DestinationRecommendation(BaseModel):
    """Destination recommendation package."""

    destinations: list[Destination] = Field(default_factory=list)
    selected: Optional[Destination] = None
    reasoning: str = ""
    source_links: list[SourceLink] = Field(default_factory=list)


class FlightOption(BaseModel):
    """Suggested transport option derived from search + LLM."""

    label: str
    summary: str
    route: str = ""
    airline_hint: str = ""
    estimated_roundtrip_cost: float = 0.0
    duration_hint: str = ""
    booking_advice: str = ""
    source_links: list[SourceLink] = Field(default_factory=list)
    disclaimer: str = ""


class FlightSearchResult(BaseModel):
    """Transport planning result."""

    options: list[FlightOption] = Field(default_factory=list)
    recommended: Optional[FlightOption] = None
    total_flight_cost: float = 0.0
    disclaimer: str = ""


class HotelOption(BaseModel):
    """Suggested stay option derived from search + LLM."""

    name: str
    area: str = ""
    summary: str = ""
    nightly_price_text: str = ""
    estimated_total_cost: float = 0.0
    amenities: list[str] = Field(default_factory=list)
    source_links: list[SourceLink] = Field(default_factory=list)
    disclaimer: str = ""


class HotelSearchResult(BaseModel):
    """Hotel planning result."""

    hotels: list[HotelOption] = Field(default_factory=list)
    recommended: Optional[HotelOption] = None
    total_nights: int = 0
    total_hotel_cost: float = 0.0
    disclaimer: str = ""


class Activity(BaseModel):
    """One itinerary item."""

    name: str
    category: str = "sightseeing"
    location: str = ""
    duration_hours: float = 2.0
    price: float = 0.0
    description: str = ""
    time_slot: str = ""
    source_links: list[SourceLink] = Field(default_factory=list)


class DayPlan(BaseModel):
    """Activities grouped by day."""

    date: str
    activities: list[Activity] = Field(default_factory=list)
    day_cost: float = 0.0
    summary: str = ""


class ActivitySearchResult(BaseModel):
    """Activity planning result."""

    day_plans: list[DayPlan] = Field(default_factory=list)
    total_activity_cost: float = 0.0
    source_links: list[SourceLink] = Field(default_factory=list)
    disclaimer: str = ""


class BudgetBreakdown(BaseModel):
    """Budget estimates and adjustment advice."""

    flight_cost: float = 0.0
    hotel_cost: float = 0.0
    activity_cost: float = 0.0
    total_cost: float = 0.0
    budget: float = 0.0
    remaining: float = 0.0
    is_within_budget: bool = True
    over_budget_amount: float = 0.0
    suggestions: list[str] = Field(default_factory=list)
    disclaimer: str = ""


class PlanningEvent(BaseModel):
    """Serializable planning event."""

    event_id: str = Field(default_factory=lambda: uuid4().hex)
    event_type: PlanningEventType
    agent: str = ""
    message: str = ""
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: str


class TravelPlanState(BaseModel):
    """Global planning state shared across agents."""

    state: PlanningState = PlanningState.COLLECTING_PREFERENCES
    preferences: Optional[UserPreferences] = None
    destination_rec: Optional[DestinationRecommendation] = None
    weather_result: Optional[WeatherResult] = None
    flight_result: Optional[FlightSearchResult] = None
    hotel_result: Optional[HotelSearchResult] = None
    activity_result: Optional[ActivitySearchResult] = None
    budget_breakdown: Optional[BudgetBreakdown] = None
    memory_context: list[MemoryEntry] = Field(default_factory=list)
    conversation_history: list[MessageRecord] = Field(default_factory=list)
    event_log: list[PlanningEvent] = Field(default_factory=list)
    planning_notes: list[str] = Field(default_factory=list)
    error_messages: list[str] = Field(default_factory=list)

    @property
    def selected_destination(self) -> Optional[Destination]:
        if self.destination_rec and self.destination_rec.selected:
            return self.destination_rec.selected
        return None
