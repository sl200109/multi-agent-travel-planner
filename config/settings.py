"""
统一管理 API 客户端和本地运行参数的配置模块。

项目通过环境变量读取密钥和配置，
默认值也尽量保持本地开发可直接使用。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _first_env(*names: str, default: str = "") -> str:
    """Return the first non-empty environment variable."""

    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


class Settings:
    """Environment-backed application settings."""

    QWEN_API_KEY: str = _first_env(
        "QWEN_API_KEY",
        "DASHSCOPE_API_KEY",
        "OPENAI_API_KEY",
        "LLM_API_KEY",
    )
    QWEN_BASE_URL: str = _first_env(
        "QWEN_BASE_URL",
        "OPENAI_BASE_URL",
        "LLM_BASE_URL",
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    QWEN_MODEL: str = _first_env("QWEN_MODEL", "LLM_MODEL", default="qwen-plus")
    QWEN_TEMPERATURE: float = float(_first_env("QWEN_TEMPERATURE", "LLM_TEMPERATURE", default="0.3"))
    QWEN_MAX_TOKENS: int = int(_first_env("QWEN_MAX_TOKENS", "LLM_MAX_TOKENS", default="4096"))

    TAVILY_API_KEY: str = _first_env("TAVILY_API_KEY")
    WTTR_BASE_URL: str = _first_env("WTTR_BASE_URL", default="https://wttr.in")

    MEMORY_DIR: Path = Path(_first_env("MEMORY_DIR", default=str(BASE_DIR / "memories")))
    ENABLE_LONG_TERM_MEMORY: bool = _first_env("ENABLE_LONG_TERM_MEMORY", default="true").lower() in {"1", "true", "yes"}

    SEARCH_MAX_RESULTS: int = int(_first_env("SEARCH_MAX_RESULTS", default="5"))
    HTTP_TIMEOUT: int = int(_first_env("HTTP_TIMEOUT", default="30"))

    API_HOST: str = _first_env("API_HOST", default="0.0.0.0")
    API_PORT: int = int(_first_env("API_PORT", default="8000"))
    LOG_LEVEL: str = _first_env("LOG_LEVEL", default="INFO")


settings = Settings()
