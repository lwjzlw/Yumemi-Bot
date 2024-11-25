from .config import PluginConfig
from typing import List, Dict
import json
import os

class Character():
    def __init__(self, name: str):
        self.cha_name = name
        self.game_name: str
        self.aliases: List[str]
        self.birthday: str  # mm-dd
        self.img_path: List[str]
        self.cv: str
        self.staff: str
        self.like: str
        self.age: str
        
    def init(self, json_path: str, image_base_path: str) -> bool:
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if self.cha_name not in data:
                return False
        except Exception as e:
            return False
        
        cha_data: Dict = data[self.cha_name]
        self.game_name = cha_data.get("game_name", "")
        self.aliases = cha_data.get("aliases", [])
        self.birthday = cha_data.get("birthday", "")
        self.img_path = cha_data.get("img_path", [])
        self.img_path = [ os.path.join(image_base_path, img) for img in self.img_path if os.path.isfile(os.path.join(image_base_path, img)) ]
        self.cv = cha_data.get("cv", "")
        self.staff = cha_data.get("staff", "")
        self.age = cha_data.get("age", "")
        self.like = cha_data.get("like", "")
        return True
        
        

        
        