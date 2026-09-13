"""Centralized environment configuration for the FinSight AI service.

USE_REAL_LLM defaults to False so the service never makes a paid LLM call
unless someone explicitly opts in (via .env) after adding their own API key.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv(override=True)


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


# 실제 LLM 호출 여부. False면 어떤 요청도 비용을 발생시키지 않습니다.
USE_REAL_LLM: bool = _get_bool("USE_REAL_LLM", False)

# USE_REAL_LLM=true일 때 어떤 제공자를 쓸지. "claude"(유료) 또는 "gemini"(무료 티어).
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "claude").strip().lower()

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

# 임베딩 등 보조 용도로만 사용 (현재는 용어 캐싱용 벡터 임베딩 생성에 사용).
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

CHROMA_HOST: str = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT: int = _get_int("CHROMA_PORT", 8000)
