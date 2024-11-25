from pydantic import BaseModel
from pathlib import Path

class PluginConfig(BaseModel):
    birthday_file_path: str = "/home/ubuntu/Yumemi-Bot/src/plugins/birthday/data/key_birthday.json"
    character_json_path: str = "/home/ubuntu/Yumemi-Bot/resource/character_data.json"
    image_base_folder: str = "/home/ubuntu/Yumemi-Bot/resource/images"
