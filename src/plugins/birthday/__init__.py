import nonebot
from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot.adapters import Message
from nonebot.params import CommandArg
from nonebot import require
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler
from typing import List
from .character import Character
import pytz

from .config import PluginConfig
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    GROUP,
    Message,
    MessageSegment
)
from .query_birthday import get_today_birthdays

__plugin_meta__ = PluginMetadata(
    name="birthday",
    description="",
    usage="",
    config=PluginConfig,
)

config = get_plugin_config(PluginConfig)

birthday_event = nonebot.on_command("birthday", aliases={"生日"}, priority=8, block=True)

@birthday_event.handle()
async def _(event: GroupMessageEvent):
    user_id = str(event.get_user_id())
    birthday_str = get_today_birthdays(config.birthday_file_path)
    
    msg = MessageSegment.at(user_id)
    msg += MessageSegment.text(f"查询结果为：{birthday_str}")
    
    await birthday_event.finish(msg)

async def daily_birthday_msg():
    bot = nonebot.get_bot()
    group_list: List[int] = [943858715]   # TODO: Get all groups and send birthday messages to those in the whitelist.
    
    birthday_characters: List[str] = get_today_birthdays(config.birthday_file_path).split()
    
    msg_list: List[MessageSegment] = []
    for character_str in birthday_characters[1:]:
        msg = MessageSegment.text(f"{character_str}\n")
        character = Character(character_str)
        if character.init(config.character_json_path, config.image_base_folder):
            if len(character.img_path) != 0:
                msg += MessageSegment.image(character.img_path[0])
            if character.game_name:
                msg += MessageSegment.text(f"作品名：{character.game_name}\n")
            if character.cv:
                msg += MessageSegment.text(f"CV：{character.cv}\n")
            if character.staff:
                msg += MessageSegment.text(f"画师：{character.staff}\n")
            if character.age:
                msg += MessageSegment.text(f"身高三围：{character.age}\n")
            if character.like:
                msg += MessageSegment.text(f"喜欢：{character.like}\n")
        msg_list.append(msg)
        
    if not msg_list:
        msg_list.append(MessageSegment.text("今天没有人过生日哦！（该提醒仅为测试期间使用，测试完成后会删掉）\n"))
    else:
        msg_list.insert(0, MessageSegment.text("今天过生日的Key社角色如下，让我们祝他们生日快乐吧!\n"))
    
    for group_id in group_list:
        for msg in msg_list:
            await bot.call_api("send_group_msg", group_id=group_id, message=msg)
    

scheduler.add_job(daily_birthday_msg, "cron", hour=0, minute=0, second=0, id='daily_birthday', timezone=pytz.timezone("Asia/Shanghai"))