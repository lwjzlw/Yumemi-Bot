import nonebot
from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot.adapters import Message
from nonebot.params import CommandArg

from .config import PluginConfig
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    GROUP,
    Message,
    MessageSegment
)
from .prophecy import Prophecy
import json
import os
import random

__plugin_meta__ = PluginMetadata(
    name="KeyProphecy",
    description="",
    usage="",
    config=PluginConfig,
)

config = get_plugin_config(PluginConfig)

prophecy_event = nonebot.on_command("今日运势", aliases={"抽签", "占卜", "key占卜"}, priority=8, block=True)

@prophecy_event.handle()
async def _(event: GroupMessageEvent):
    user_id = str(event.get_user_id())
    prophecier = Prophecy(user_id)
    heroine = prophecier.getHeroine()
    #heroine = "月宫亚由"
    lucky_point = prophecier.getLuckyPoint()
    dos, donts = prophecier.getDosDonts()
    lucky_thing = prophecier.getLuckyThing()
    
    image_path = ""
    game_name = "null"
    try:
        character_data = dict()
        with open(config.character_json_path, 'r', encoding='utf-8') as f:
            character_data = json.load(f)
        
        if heroine in character_data:
            game_name = character_data[heroine]["game_name"]
            img_list = character_data[heroine]["img_path"]
            image_path = os.path.join(config.image_base_folder, random.choice(img_list))
            print(image_path)
            if not os.path.isfile(image_path):
                image_path = ""
    except Exception as e:
        image_path = ""
    
    msg = MessageSegment.at(user_id)
    msg += MessageSegment.text(f"\n你的今日运势为：{lucky_point}\n\n")
    msg += MessageSegment.text(f"🌟你今日的key社老婆为{game_name}中的{heroine}🌟\n")
    if image_path:
        msg += MessageSegment.image(image_path)
    msg += MessageSegment.text(f"\n✅宜: {dos[0]}、{dos[1]}、{dos[2]}\n")
    msg += MessageSegment.text(f"🈲忌: {donts[0]}、{donts[1]}、{donts[2]}\n\n")
    msg += MessageSegment.text(f"⭐占卜结果显示今天你会{lucky_thing}哦！")
    
    await prophecy_event.finish(msg)