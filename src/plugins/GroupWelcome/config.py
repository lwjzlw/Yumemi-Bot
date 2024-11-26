from pydantic import BaseModel
from pathlib import Path

class PluginConfig(BaseModel):
    welcome_json: str = "/home/ubuntu/Yumemi-Bot/src/plugins/GroupWelcome/data/data.json"