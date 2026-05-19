"""
用于实时旅行规划展示的 Streamlit 界面。

界面会复用与 API 相同的规划事件流，
在同一页里展示过程事件和最终结果。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from models.schemas import PlanningEvent, PlanningEventType, TravelPlanState
from orchestrator import TravelPlanner
from services import build_preferences

st.set_page_config(page_title="真实旅行规划 Agent", page_icon="✈️", layout="wide")

if "session_id" not in st.session_state:
    st.session_state.session_id = uuid4().hex

planner = TravelPlanner()


def _render_final_state(state: TravelPlanState) -> None:
    destination = state.selected_destination
    if destination:
        st.subheader(f"目的地：{destination.city}, {destination.country}")
        st.write(destination.description)
        if destination.highlights:
            st.write("亮点：", "、".join(destination.highlights))

    if state.weather_result:
        weather = state.weather_result
        st.info(f"天气：{weather.description}，{weather.temperature_c}°C")

    tab1, tab2, tab3, tab4 = st.tabs(["交通", "酒店", "行程", "预算"])

    with tab1:
        if state.flight_result and state.flight_result.recommended:
            item = state.flight_result.recommended
            st.metric("推荐方案", item.label, f"¥{item.estimated_roundtrip_cost:.0f}")
            st.write(item.summary)
            for link in item.source_links[:5]:
                st.markdown(f"- [{link.title}]({link.url})")

    with tab2:
        if state.hotel_result and state.hotel_result.recommended:
            hotel = state.hotel_result.recommended
            st.metric("推荐酒店", hotel.name, f"¥{hotel.estimated_total_cost:.0f}")
            st.write(hotel.summary)
            if hotel.amenities:
                st.write("设施：", "、".join(hotel.amenities))
            for link in hotel.source_links[:5]:
                st.markdown(f"- [{link.title}]({link.url})")

    with tab3:
        if state.activity_result:
            for day in state.activity_result.day_plans:
                st.markdown(f"### {day.date} | ¥{day.day_cost:.0f}")
                st.write(day.summary)
                for activity in day.activities:
                    st.write(
                        f"- [{activity.time_slot}] {activity.name} | "
                        f"{activity.location} | ¥{activity.price:.0f}"
                    )

    with tab4:
        if state.budget_breakdown:
            budget = state.budget_breakdown
            col1, col2, col3 = st.columns(3)
            col1.metric("交通", f"¥{budget.flight_cost:.0f}")
            col2.metric("酒店", f"¥{budget.hotel_cost:.0f}")
            col3.metric("活动", f"¥{budget.activity_cost:.0f}")
            st.metric(
                "总计 / 预算",
                f"¥{budget.total_cost:.0f} / ¥{budget.budget:.0f}",
                delta=f"剩余 ¥{budget.remaining:.0f}" if budget.remaining >= 0 else f"超出 ¥{abs(budget.remaining):.0f}",
                delta_color="normal" if budget.remaining >= 0 else "inverse",
            )
            for suggestion in budget.suggestions:
                st.write(f"- {suggestion}")
            st.caption(budget.disclaimer)

    if state.memory_context:
        st.subheader("长期记忆摘要")
        for item in state.memory_context[-3:]:
            st.write(f"- {item.summary}")

    if state.error_messages:
        for item in state.error_messages:
            st.warning(item)


async def _run_stream(preferences, log_placeholder, result_placeholder) -> None:
    lines: list[str] = []
    async for event in planner.stream(preferences):
        lines.append(f"- `{event.event_type.value}` {event.agent}: {event.message}")
        log_placeholder.markdown("\n".join(lines[-20:]) or "等待事件...")
        if event.event_type == PlanningEventType.FINAL_PLAN:
            state = TravelPlanState(**event.payload["state"])
            with result_placeholder.container():
                _render_final_state(state)


st.title("✈️ 真实旅行规划 Agent")
st.caption("Tavily + Qwen + wttr.in + 流式输出 + 长短期记忆")

left, right = st.columns([1, 2])

with left:
    budget = st.number_input("总预算（人民币）", min_value=1000, max_value=500000, value=12000, step=1000)
    departure = st.text_input("出发城市", value="上海")
    start_date = st.date_input("出发日期")
    end_date = st.date_input("返回日期")
    style = st.selectbox(
        "旅行风格",
        ["comfort", "budget", "luxury", "adventure", "cultural", "relaxation"],
    )
    travelers = st.number_input("出行人数", min_value=1, max_value=10, value=1)
    interests = st.multiselect("兴趣标签", ["美食", "历史", "艺术", "自然", "购物", "摄影", "徒步"])
    user_id = st.text_input("用户 ID", value="streamlit-user")
    enable_memory = st.checkbox("启用长期记忆", value=True)
    notes = st.text_area("补充说明", placeholder="例如：更想看博物馆，少走路，不想红眼航班")
    start = st.button("开始规划", type="primary", use_container_width=True)

with right:
    event_placeholder = st.empty()
    result_placeholder = st.empty()

if start:
    preferences = build_preferences(
        budget=float(budget),
        departure_city=departure,
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        travel_style=style,
        num_travelers=int(travelers),
        interests=interests,
        notes=notes,
        user_id=user_id,
        session_id=st.session_state.session_id,
        enable_long_term_memory=enable_memory,
    )
    with st.spinner("Agents 正在进行真实查询和规划..."):
        asyncio.run(_run_stream(preferences, event_placeholder, result_placeholder))
else:
    right.info("填写偏好后点击“开始规划”，右侧会实时显示 agent 事件流。")
