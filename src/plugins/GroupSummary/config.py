from pydantic import BaseModel
from typing import List

class Config(BaseModel):
    white_list: List[int] = [
        398227078,
        737574359,
        496642207
    ]
