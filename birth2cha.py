import json
import os
from typing import Dict

data: Dict = dict()
with open("/home/ubuntu/Yumemi-Bot/src/plugins/birthday/data/key_birthday.json", 'r') as f:
    data = json.load(f)
    
new_data: Dict = dict()
for birthday in data.keys():
    for cha_data in data[birthday]:
        cha_name = cha_data["cha_name"]
        new_data[cha_name] = dict()
        for attr in cha_data.keys():
            if attr == "cha_name":
                continue
            new_data[cha_name][attr] = cha_data[attr]
            new_data[cha_name]["birthday"] = birthday
            new_data[cha_name]["aliases"] = "" 

with open("/home/ubuntu/Yumemi-Bot/resource/character_data.json", 'w') as f:
    json.dump(new_data, f, ensure_ascii=False, indent=4)
    