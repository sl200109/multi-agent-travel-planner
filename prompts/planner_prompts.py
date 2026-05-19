"""
项目里所有 Agent 共用的提示词模板。

这里统一使用中文提示词，
但仍要求模型输出固定的 JSON 键，方便程序继续解析。
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


def destination_prompt() -> ChatPromptTemplate:
    """目的地推荐提示词。"""

    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是一个旅行规划分析助手。"
                "你会结合真实搜索结果、用户偏好和历史记忆，给出结构化的目的地推荐。"
                "请只返回合法 JSON，不要输出解释性文字。"
                "JSON 必须包含 keys: destinations, selected_city, reasoning。"
                "其中每个 destination 项必须包含 city, country, description, highlights, reason。",
            ),
            MessagesPlaceholder(variable_name="conversation_history", optional=True),
            (
                "human",
                "用户偏好：\n{preferences}\n\n"
                "长期记忆：\n{memory_context}\n\n"
                "搜索摘要：\n{search_answer}\n\n"
                "搜索来源：\n{search_sources}",
            ),
        ]
    )


def flight_prompt() -> ChatPromptTemplate:
    """交通建议提示词。"""

    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是一个旅行交通规划助手。"
                "你需要基于真实网页搜索结果，总结出用户可执行的交通建议。"
                "请只返回合法 JSON，不要输出解释性文字。"
                "JSON 必须包含 keys: options, recommended_label, disclaimer。"
                "每个 option 必须包含 label, summary, route, airline_hint, estimated_roundtrip_cost, "
                "duration_hint, booking_advice。",
            ),
            MessagesPlaceholder(variable_name="conversation_history", optional=True),
            (
                "human",
                "用户偏好：\n{preferences}\n\n"
                "目标目的地：\n{destination}\n\n"
                "搜索摘要：\n{search_answer}\n\n"
                "搜索来源：\n{search_sources}",
            ),
        ]
    )


def hotel_prompt() -> ChatPromptTemplate:
    """酒店建议提示词。"""

    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是一个旅行住宿规划助手。"
                "你需要把真实搜索结果整理成结构化的酒店建议。"
                "请只返回合法 JSON，不要输出解释性文字。"
                "JSON 必须包含 keys: hotels, recommended_name, disclaimer。"
                "每个 hotel 必须包含 name, area, summary, nightly_price_text, estimated_total_cost, amenities。",
            ),
            MessagesPlaceholder(variable_name="conversation_history", optional=True),
            (
                "human",
                "用户偏好：\n{preferences}\n\n"
                "目标目的地：\n{destination}\n\n"
                "天气信息：\n{weather}\n\n"
                "搜索摘要：\n{search_answer}\n\n"
                "搜索来源：\n{search_sources}",
            ),
        ]
    )


def activity_prompt() -> ChatPromptTemplate:
    """按天行程生成提示词。"""

    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是一个旅行行程规划助手。"
                "你需要把真实景点、美食和体验信息整理成逐日 itinerary。"
                "请只返回合法 JSON，不要输出解释性文字。"
                "JSON 必须包含 keys: day_plans, disclaimer。"
                "每个 day_plan 必须包含 date, summary, day_cost, activities。"
                "每个 activity 必须包含 name, category, location, duration_hours, price, description, time_slot。",
            ),
            MessagesPlaceholder(variable_name="conversation_history", optional=True),
            (
                "human",
                "用户偏好：\n{preferences}\n\n"
                "目标目的地：\n{destination}\n\n"
                "天气信息：\n{weather}\n\n"
                "搜索摘要：\n{search_answer}\n\n"
                "搜索来源：\n{search_sources}",
            ),
        ]
    )
