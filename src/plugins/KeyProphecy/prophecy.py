import random
from datetime import datetime
from .config import PluginConfig
from functools import lru_cache
from typing import List
import hashlib
from nonebot import get_plugin_config


@lru_cache(maxsize=8)
def load_prophecy_lines(path: str) -> tuple[str, ...]:
    with open(path, 'r', encoding='utf-8') as f:
        return tuple(s.strip() for s in f.readlines() if s.strip())


class Prophecy():
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.variant_seed = f"{self.user_id}_{self.today}"
    
    def seed(self, s):
        return int(hashlib.md5(s.encode()).hexdigest(),16)%(2**32)
        
    def getLuckyPoint(self) -> int:
        random.seed(self.seed(f"lukcypoint_{self.variant_seed}"))
        return random.randint(0, 100)

    def getRobSuccessRoll(self, denominator: int = 500) -> int:
        random.seed(self.seed(f"rob_success_{self.variant_seed}"))
        return random.randint(1, denominator)
        
    def getHeroine(self) -> str:
        random.seed(self.seed(f"heroine_{self.variant_seed}"))
        config = get_plugin_config(PluginConfig)
        heroines = load_prophecy_lines(config.heroine_path)
        return random.choice(heroines)
    
    def getDosDonts(self) -> (List[str], List[str]):
        random.seed(self.seed(f"should_do_{self.variant_seed}"))
        config = get_plugin_config(PluginConfig)
        dos = list(load_prophecy_lines(config.littlethings_path))
        samples = random.sample(dos, 6)
        return (samples[:3], samples[3:])
    
    def getLuckyThing(self) -> str:
        random.seed(self.seed(f"lucky_{self.variant_seed}"))
        config = get_plugin_config(PluginConfig)
        lucky_things = load_prophecy_lines(config.luckythings_path)
        return random.choice(lucky_things)
    
