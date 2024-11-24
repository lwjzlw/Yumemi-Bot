from pydantic import BaseModel
from pathlib import Path

class PluginConfig(BaseModel):
    heroine_path: str = "/home/ubuntu/Yumemi-Bot/src/plugins/KeyProphecy/resource/heroine.txt"
    littlethings_path: str = "/home/ubuntu/Yumemi-Bot/src/plugins/KeyProphecy/resource/littlethings.txt"
    luckythings_path: str = "/home/ubuntu/Yumemi-Bot/src/plugins/KeyProphecy/resource/luckythings.txt"
    character_json_path: str = "/home/ubuntu/Yumemi-Bot/resource/character_data.json"
    image_base_folder: str = "/home/ubuntu/Yumemi-Bot/resource/images"
