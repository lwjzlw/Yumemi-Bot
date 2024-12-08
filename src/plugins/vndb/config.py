from pydantic import BaseModel
from pathlib import Path

class PluginConfig(BaseModel):
    character_json_path: str = "/home/ubuntu/Yumemi-Bot/src/plugins/vndb/resources/vndb_character.json"
