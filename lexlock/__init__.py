"""Ядро «ЛексЛока» — локального юридического ассистента (полностью офлайн)."""

from .config import Config, load_config
from .llm import LLM, ChatResult, LLMError, ToolCall
from .agent import Agent, Event

__all__ = [
    "Config",
    "load_config",
    "LLM",
    "ChatResult",
    "LLMError",
    "ToolCall",
    "Agent",
    "Event",
]
