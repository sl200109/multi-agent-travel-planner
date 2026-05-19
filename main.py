"""
真实旅行规划器的命令行入口。

这里复用统一的偏好构建和规划主链路，
保证 CLI、API 和 UI 的行为保持一致。
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from loguru import logger

from orchestrator import TravelPlanner
from services import build_preferences

logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Real-data travel planner")
    parser.add_argument("--budget", type=float, default=10000)
    parser.add_argument("--departure", type=str, default="Beijing")
    parser.add_argument("--start", type=str, default="2026-05-01")
    parser.add_argument("--end", type=str, default="2026-05-05")
    parser.add_argument("--style", type=str, default="comfort")
    parser.add_argument("--travelers", type=int, default=1)
    parser.add_argument("--user-id", type=str, default="cli-user")
    parser.add_argument("--interests", nargs="*", default=[])
    args = parser.parse_args()

    preferences = build_preferences(
        budget=args.budget,
        departure_city=args.departure,
        start_date=args.start,
        end_date=args.end,
        travel_style=args.style,
        num_travelers=args.travelers,
        interests=args.interests,
        user_id=args.user_id,
    )
    state = asyncio.run(TravelPlanner().plan(preferences))

    print("\n" + "=" * 60)
    print("Travel Plan")
    print("=" * 60)

    if state.selected_destination:
        destination = state.selected_destination
        print(f"\nDestination: {destination.city}, {destination.country}")
        print(destination.description)
        if destination.highlights:
            print("Highlights:", ", ".join(destination.highlights))

    if state.weather_result:
        weather = state.weather_result
        print(f"\nWeather: {weather.description}, {weather.temperature_c}C")

    if state.flight_result and state.flight_result.recommended:
        transport = state.flight_result.recommended
        print(f"\nTransport: {transport.label}")
        print(f"Estimated cost: {transport.estimated_roundtrip_cost:.0f} CNY")
        print(transport.summary)

    if state.hotel_result and state.hotel_result.recommended:
        hotel = state.hotel_result.recommended
        print(f"\nHotel: {hotel.name}")
        print(f"Estimated total: {hotel.estimated_total_cost:.0f} CNY")
        print(hotel.summary)

    if state.activity_result:
        print("\nItinerary:")
        for day in state.activity_result.day_plans:
            print(f"  {day.date} - {day.summary} ({day.day_cost:.0f} CNY)")
            for activity in day.activities:
                print(f"    [{activity.time_slot}] {activity.name} - {activity.price:.0f} CNY")

    if state.budget_breakdown:
        budget = state.budget_breakdown
        print("\nBudget:")
        print(f"  Flight: {budget.flight_cost:.0f}")
        print(f"  Hotel: {budget.hotel_cost:.0f}")
        print(f"  Activities: {budget.activity_cost:.0f}")
        print(f"  Total: {budget.total_cost:.0f} / {budget.budget:.0f}")
        for suggestion in budget.suggestions:
            print(f"  - {suggestion}")

    if state.error_messages:
        print("\nWarnings:")
        for message in state.error_messages:
            print(f"  - {message}")


if __name__ == "__main__":
    main()
