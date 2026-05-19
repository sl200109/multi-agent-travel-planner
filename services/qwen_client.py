"""
使用 LangChain 链式写法的 Qwen 客户端。

这里不再直接暴露底层 client 调用，
而是使用 prompt | llm | parser 的方式组织请求。
"""

from __future__ import annotations

import json
from typing import AsyncIterator

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from config.settings import settings


def _extract_json_block(text: str) -> dict[str, object]:
    """从模型输出中提取第一个 JSON 对象。"""

    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(stripped[start : end + 1])


def to_langchain_messages(records: list[dict[str, str]] | list[object]) -> list[BaseMessage]:
    """把简单消息记录转换成 LangChain message 对象。"""

    messages: list[BaseMessage] = []
    for item in records:
        role = getattr(item, "role", None) or item.get("role", "user")
        content = getattr(item, "content", None) or item.get("content", "")
        if role == "system":
            messages.append(SystemMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    return messages


class QwenClient:
    """基于 LangChain ChatOpenAI 的 Qwen 封装。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        self.api_key = api_key or settings.QWEN_API_KEY
        self.base_url = base_url or settings.QWEN_BASE_URL
        self.model = model or settings.QWEN_MODEL
        self.temperature = settings.QWEN_TEMPERATURE if temperature is None else temperature
        self.max_tokens = settings.QWEN_MAX_TOKENS if max_tokens is None else max_tokens
        self.llm: ChatOpenAI | None = None

    def _ensure_llm(self, *, temperature: float | None = None) -> ChatOpenAI:
        """懒加载 LangChain LLM，避免导入时就做鉴权。"""

        if not self.api_key:
            raise ValueError(
                "缺少 Qwen API Key。请在环境变量中设置 `QWEN_API_KEY`、"
                "`DASHSCOPE_API_KEY`、`OPENAI_API_KEY` 或 `LLM_API_KEY`。"
            )
        temp = self.temperature if temperature is None else temperature
        if self.llm is None or self.llm.temperature != temp:
            self.llm = ChatOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                model=self.model,
                temperature=temp,
                max_tokens=self.max_tokens,
            )
        return self.llm

    async def complete_text(
        self,
        prompt: ChatPromptTemplate,
        variables: dict[str, object],
        *,
        temperature: float | None = None,
    ) -> str:
        """使用 LangChain chain 异步获取文本输出。"""

        llm = self._ensure_llm(temperature=temperature)
        chain = prompt | llm | StrOutputParser()
        return await chain.ainvoke(variables)

    async def complete_json(
        self,
        prompt: ChatPromptTemplate,
        variables: dict[str, object],
    ) -> dict[str, object]:
        """获取文本后解析 JSON。"""

        text = await self.complete_text(prompt, variables, temperature=0)
        return _extract_json_block(text)

    async def stream_text(
        self,
        prompt: ChatPromptTemplate,
        variables: dict[str, object],
        *,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """使用 LangChain chain 流式输出文本片段。"""

        llm = self._ensure_llm(temperature=temperature)
        chain = prompt | llm | StrOutputParser()
        async for chunk in chain.astream(variables):
            if chunk:
                yield chunk
