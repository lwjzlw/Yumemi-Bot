from pydantic import BaseModel
from pathlib import Path

class PluginConfig(BaseModel):
    
    birthday_file_path: str = "/home/ubuntu/Yumemi-Bot/src/plugins/birthday/data/key_birthday.json"
