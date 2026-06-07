from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESOURCE_DIR = PROJECT_ROOT / "resource"
IMAGE_RESOURCE_DIR = RESOURCE_DIR / "images"
CHARACTER_DATA_PATH = RESOURCE_DIR / "character_data.json"
GAME_ALIAS_PATH = RESOURCE_DIR / "game_aliases.json"
RECENT_ERROR_LOG_PATH = RESOURCE_DIR / "recent_errors.json"
CHAT_MEMORY_CACHE_PATH = RESOURCE_DIR / "chat_memory_cache.json"
CHAT_AGENT_MEMORY_PATH = RESOURCE_DIR / "chat_agent_memory.jsonl"

PLUGINS_DIR = PROJECT_ROOT / "src" / "plugins"
KEY_PROPHECY_RESOURCE_DIR = PLUGINS_DIR / "KeyProphecy" / "resource"
GROUP_WELCOME_DATA_DIR = PLUGINS_DIR / "GroupWelcome" / "data"
BIRTHDAY_DATA_DIR = PLUGINS_DIR / "birthday" / "data"
