import random
from datetime import datetime
from .config import PluginConfig
from typing import List

class Prophecy():
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.variant_seed = f"{self.user_id}_{self.today}"
        
    def getLuckyPoint(self) -> int:
        random.seed(f"{self.variant_seed}_lukcypoint")
        return random.randint(0, 100)
        
    def getHeroine(self) -> str:
        random.seed(f"{self.variant_seed}_heroine")
        heroines: List[str]
        with open("/home/ubuntu/Yumemi-Bot/src/plugins/KeyProphecy/resource/heroine.txt", 'r') as f:
            heroines = [ s.strip() for s in f.readlines() ]
        return random.choice(heroines)
    
    def getDosDonts(self) -> (List[str], List[str]):
        random.seed(f"{self.variant_seed}_should_do")
        dos: List[str]
        with open("/home/ubuntu/Yumemi-Bot/src/plugins/KeyProphecy/resource/littlethings.txt", 'r') as f:
            dos = [ s.strip() for s in f.readlines() ]
        samples = random.sample(dos, 6)
        return (samples[:3], samples[3:])
    
    def getLuckyThing(self) -> str:
        random.seed(f"{self.variant_seed}_lucky")
        lucky_things: List[str]
        with open("/home/ubuntu/Yumemi-Bot/src/plugins/KeyProphecy/resource/luckythings.txt", 'r') as f:
            lucky_things = [ s.strip() for s in f.readlines() ]
        return random.choice(lucky_things)
    