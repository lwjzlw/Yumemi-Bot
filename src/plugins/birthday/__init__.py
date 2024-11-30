import nonebot
from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot.adapters import Message
from nonebot.params import CommandArg
from nonebot.matcher import Matcher
from nonebot import require
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler
from typing import List
from .character import Character
import pytz
from datetime import datetime
import os

from .config import PluginConfig
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    GROUP,
    Message,
    MessageSegment
)
from .query_birthday import get_birthdays

__plugin_usage__ = f"""
1. 输入 “#生日” 查询今日过生日的角色；
2. 输入 “#生日 角色名” 查询指定角色的生日；
3. 输入 “#生日 月 日” 查询指定日期过生日的角色。
"""


__plugin_meta__ = PluginMetadata(
    name="birthday",
    description="",
    usage=__plugin_usage__,
    config=PluginConfig,
)

config = get_plugin_config(PluginConfig)


def get_birthday_msg(character_str: str) -> MessageSegment:
    msg = MessageSegment.text(f"{character_str}\n")
    character = Character(character_str)
    if character.init(config.character_json_path, config.image_base_folder):
        if len(character.img_path) != 0:
            msg += MessageSegment.image(character.img_path[0])
        if character.game_name:
            msg += MessageSegment.text(f"作品名：{character.game_name}\n")
        if character.tag:
            msg += MessageSegment.text(f"所属：{character.tag}\n")
        if character.cv:
            msg += MessageSegment.text(f"CV：{character.cv}\n")
        if character.staff:
            msg += MessageSegment.text(f"画师：{character.staff}\n")
        if character.age:
            msg += MessageSegment.text(f"身高三围：{character.age}\n")
        if character.like:
            msg += MessageSegment.text(f"喜欢：{character.like}\n")
    return msg


def get_birthday_msg_list(character_list: List[str]) -> List[MessageSegment]:
    msg_list = []
    for character_str in character_list:
        msg_list.append(get_birthday_msg(character_str))
    return msg_list


birthday_event = nonebot.on_command("birthday", aliases={"生日"}, priority=8, block=True)

@birthday_event.handle()
async def birthday_event_handler(matcher: Matcher, event: GroupMessageEvent, args: Message=CommandArg()):
    user_id = str(event.get_user_id())
    args: str = args.extract_plain_text()
    if not args:
        month, day = datetime.today().month, datetime.today().day
    else:
        args: List[str] = args.split()
        
        if len(args) > 2:
            await birthday_event.finish(f"使用方法：\n{__plugin_usage__}")
            
        if len(args) == 1:    # Query birthday by character name.
            matcher.set_arg("character_name", args[0])
            matcher.skip()
        
        if not (args[0].isdigit() and args[1].isdigit()):
            await birthday_event.finish("请输入合法的月和日！\n")
        month, day = int(args[0]), int(args[1])
        
    try:    
        birthday_list = get_birthdays(config.birthday_file_path, month, day)
    except ValueError as e:
        await birthday_event.finish("请输入合法的月和日！\n")
    
    msg_list = get_birthday_msg_list(birthday_list)
    if not msg_list:
        msg_list.append(MessageSegment.at(user_id)+MessageSegment.text(f"\n{month}月{day}日没有过生日的角色哦！\n"))
     
    else:
        msg_list.insert(0, MessageSegment.at(user_id)+MessageSegment.text(f"\n{month}月{day}日过生日的角色有：\n"))
      
    birth_node =[]
    for character_msg in msg_list:
        birth_node.append(
                MessageSegment.node_custom(
                    user_id=os.getenv("QQ_NUMBER"),
                    nickname=os.getenv("QQ_ID"),
                    content=character_msg,
                )
            )
    # birth_node = MessageSegment.node_custom(user_id="2544412429", nickname="星野梦美", content= msg_list)
    # for msg in msg_list: 
    #     await birthday_event.send(msg)
    await birthday_event.finish(birth_node)
    
    
@birthday_event.handle()
async def send_birthday_by_name(matcher: Matcher, event: GroupMessageEvent, args: Message=CommandArg()):
    msg = MessageSegment.at(event.user_id) + MessageSegment.text("\n")
    
    character_name = matcher.get_arg("character_name")
    character = Character(character_name)
    if not character.init(config.character_json_path, config.image_base_folder):
        await birthday_event.finish(msg + f"梦美没有查询到名为{character_name}的角色信息，换个名称试试吧！")
    
    if character.birthday == "" or character.birthday == "unknown":
        await birthday_event.finish(msg + f"非常抱歉，梦美不知道{character_name}的生日")
    
    month, date = tuple(character.birthday.split('-'))
    await birthday_event.finish(msg + f"{character_name}的生日是{month}月{date}日")

async def daily_birthday_msg():
    bot = nonebot.get_bot()
    group_list: List[int] = [943858715, 737574359, 496642207]   # TODO: Get all groups and send birthday messages to those in the whitelist.
    
    birthday_characters: List[str] = get_birthdays(config.birthday_file_path)
    
    msg_list = get_birthday_msg_list(birthday_characters)
        
    if not msg_list:
        #msg_list.append(MessageSegment.text("今天没有人过生日哦！（该提醒仅为测试期间使用，测试完成后会删掉）\n"))
        return
    else:
        msg_list.insert(0, MessageSegment.text("今天过生日的Key社角色如下，让我们祝他们生日快乐吧!\n"))
    
    for group_id in group_list:
        birth_node =[]
        #for character_msg in msg_list:
        #    birth_node.append(
        #            MessageSegment.node_custom(
        #                user_id=os.getenv("QQ_NUMBER"),
        #                nickname=os.getenv("QQ_ID"),
        #                content=character_msg,
        #            )
        #        )
        #    await bot.call_api("send_group_msg", group_id=group_id, message=birth_node)
        for msg in msg_list:
            await bot.call_api("send_group_msg", group_id=group_id, message=msg)
    

scheduler.add_job(daily_birthday_msg, "cron", hour=0, minute=0, second=0, id='daily_birthday', timezone=pytz.timezone("Asia/Shanghai"))