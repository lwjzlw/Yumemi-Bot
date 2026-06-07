from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.utils.paths import CHAT_AGENT_MEMORY_PATH, CHAT_MEMORY_CACHE_PATH


class Config(BaseModel):
    """Chat plugin config."""

    chat_enabled: bool = False
    chat_group_whitelist: list[int] = Field(default_factory=list)
    chat_memory_max_messages: int = Field(default=20, ge=0, le=100)
    chat_memory_cache_path: str = str(CHAT_MEMORY_CACHE_PATH)
    chat_memory_record_all_group_messages: bool = True
    chat_agent_enabled: bool = False
    chat_agent_allow_network: bool = False
    chat_agent_memory_path: str = str(CHAT_AGENT_MEMORY_PATH)
    chat_agent_max_tool_rounds: int = Field(default=8, ge=1, le=20)
    chat_vndb_context_enabled: bool = True
    chat_vndb_context_timeout: float = Field(default=4.0, gt=0, le=20)
    chat_provider: Literal["closeai", "deepseek", "claude", "azure"] = "closeai"
    chat_closeai_model: str = "gemini-3-flash-preview"
    chat_deepseek_model: str = "deepseek-v4-flash"
    chat_claude_model: str = "claude-3-5-haiku-20241022"
    chat_azure_deployment: str = "gpt-35-turbo"
    chat_max_tokens: int = Field(default=1024, gt=0, le=4096)
    claude_api_key: str = ""
    deepseek_api_key: str = ""
    openai_endpoint: str = ""
    openai_api_key: str = ""
    openai_api_version: str = ""

    @field_validator("chat_group_whitelist", mode="before")
    @classmethod
    def parse_group_whitelist(cls, value):
        if value in (None, ""):
            return []
        if isinstance(value, str):
            groups = []
            for item in value.replace("，", ",").replace(" ", ",").split(","):
                item = item.strip()
                if item:
                    groups.append(int(item))
            return groups
        return value
