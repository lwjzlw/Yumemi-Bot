#!/usr/bin/env python3
"""Print a safe summary of Yumemi chat configuration."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path


DEFAULT_ENV = Path(".env")
SECRET_KEYS = {
    "CLAUDE_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_ENDPOINT",
    "OPENAI_API_VERSION",
}
CHAT_KEYS = {
    "chat_enabled",
    "chat_group_whitelist",
    "chat_memory_max_messages",
    "chat_memory_cache_path",
    "chat_memory_record_all_group_messages",
    "chat_agent_enabled",
    "chat_agent_allow_network",
    "chat_agent_memory_path",
    "chat_agent_max_tool_rounds",
    "chat_vndb_context_enabled",
    "chat_vndb_context_timeout",
    "chat_provider",
    "chat_closeai_model",
    "chat_deepseek_model",
    "chat_claude_model",
    "chat_azure_deployment",
    "chat_max_tokens",
}
PROVIDER_KEYS = {
    "closeai": ["CLAUDE_API_KEY"],
    "claude": ["CLAUDE_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "azure": ["OPENAI_ENDPOINT", "OPENAI_API_KEY", "OPENAI_API_VERSION"],
}


def get_value(env: dict[str, str | None], key: str, default: str = "") -> str:
    return str(env.get(key) or env.get(key.upper()) or default)


def strip_inline_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
            continue
        if char == "#" and quote is None:
            return value[:index].rstrip()
    return value.strip()


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        if not key:
            continue
        env[key] = unquote(strip_inline_comment(value))
    return env


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_whitelist(value: str) -> list[int]:
    value = value.strip()
    if not value:
        return []
    if value.startswith("["):
        parsed = ast.literal_eval(value)
        return [int(item) for item in parsed]
    result = []
    for item in value.replace("，", ",").replace(" ", ",").split(","):
        item = item.strip()
        if item:
            result.append(int(item))
    return result


def masked_status(env: dict[str, str | None], key: str) -> str:
    value = get_value(env, key)
    if not value:
        return "missing"
    return f"set ({len(value)} chars)"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("env_file", nargs="?", type=Path, default=DEFAULT_ENV)
    args = parser.parse_args()

    if not args.env_file.exists():
        raise SystemExit(f"env file not found: {args.env_file}")
    env = load_env(args.env_file)

    provider = get_value(env, "chat_provider", "closeai").lower()
    enabled = parse_bool(get_value(env, "chat_enabled", "false"))
    whitelist = parse_whitelist(get_value(env, "chat_group_whitelist", ""))
    memory = get_value(env, "chat_memory_max_messages", "20")
    agent_enabled = parse_bool(get_value(env, "chat_agent_enabled", "false"))
    agent_network = parse_bool(get_value(env, "chat_agent_allow_network", "false"))
    agent_memory = get_value(env, "chat_agent_memory_path", "resource/chat_agent_memory.jsonl")
    vndb_enabled = get_value(env, "chat_vndb_context_enabled", "true")

    print(f"env: {args.env_file}")
    print(f"chat_enabled: {enabled}")
    print(f"chat_group_whitelist: {whitelist or '[] (no groups allowed)'}")
    print(f"chat_memory_max_messages: {memory}")
    print(f"chat_agent_enabled: {agent_enabled}")
    print(f"chat_agent_allow_network: {agent_network}")
    print(f"chat_agent_memory_path: {agent_memory}")
    print(f"chat_vndb_context_enabled: {vndb_enabled}")
    print(f"chat_provider: {provider}")

    print("\nprovider secrets:")
    for key in PROVIDER_KEYS.get(provider, []):
        print(f"- {key}: {masked_status(env, key)}")

    print("\nchat options in env:")
    for key in sorted(CHAT_KEYS):
        value = get_value(env, key)
        if value:
            print(f"- {key}: {value}")

    print("\nsecret keys in env:")
    for key in sorted(SECRET_KEYS):
        print(f"- {key}: {masked_status(env, key)}")


if __name__ == "__main__":
    main()
