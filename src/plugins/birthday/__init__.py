import nonebot
from nonebot import get_plugin_config, logger
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
from src.utils.character_data import list_character_images, normalize_lookup_text
from src.utils.error_history import (
    describe_exception_reason,
    extract_exception_details,
    record_recent_error,
)
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    GROUP,
    Message,
    MessageSegment
)
from nonebot.adapters.onebot.v11.exception import ActionFailed, ApiNotAvailable, NetworkError
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


def record_birthday_error(
    *,
    command: str,
    raw_input: str,
    error: Exception,
    user_id: str = "",
    group_id: str = "",
    extra_details: dict[str, str] | None = None,
) -> None:
    details = {
        "user_id": user_id,
        "group_id": group_id,
        **extract_exception_details(error),
    }
    if extra_details:
        details.update(extra_details)
    record_recent_error(
        command=command,
        raw_input=raw_input,
        reason=describe_exception_reason(command, error),
        details=details,
    )


def format_character_display_name(query_name: str, canonical_name: str, matched_name: str) -> str:
    if normalize_lookup_text(query_name) == normalize_lookup_text(canonical_name):
        return canonical_name
    if normalize_lookup_text(query_name) == normalize_lookup_text(matched_name):
        return f"{canonical_name}（{matched_name}）"
    return f"{canonical_name}（{query_name}→{matched_name}）"


def get_birthday_msg(character_str: str) -> MessageSegment:
    msg = MessageSegment.text(f"{character_str}\n")
    character = Character(character_str)
    if character.init(config.character_json_path, config.image_base_folder):
        image_list = list_character_images(character.cha_name, config.image_base_folder)
        if len(image_list) != 0:
            msg += MessageSegment.image(image_list[0])
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
broadcast_event = nonebot.on_command("生日广播", aliases={"生日广播2"}, priority=8, block=True)

@birthday_event.handle()
async def birthday_event_handler(matcher: Matcher, event: GroupMessageEvent, args: Message=CommandArg()):
    user_id = str(event.get_user_id())
    group_id = str(event.group_id)
    raw_input = args.extract_plain_text()
    if not raw_input:
        month, day = datetime.today().month, datetime.today().day
    else:
        args_list: List[str] = raw_input.split()
        
        if len(args_list) > 2:
            await birthday_event.finish(f"使用方法：\n{__plugin_usage__}")
            
        if len(args_list) == 1:    # Query birthday by character name.
            matcher.set_arg("character_name", args_list[0])
            matcher.skip()
        
        if not (args_list[0].isdigit() and args_list[1].isdigit()):
            await birthday_event.finish("请输入合法的月和日！\n")
        month, day = int(args_list[0]), int(args_list[1])
        
    try:
        birthday_list = get_birthdays(config.character_json_path, month, day)
    except ValueError:
        await birthday_event.finish("请输入合法的月和日！\n")
    except Exception as error:
        logger.exception(
            "Birthday query preparation failed: "
            f"user_id={user_id}, group_id={group_id}, raw_input={raw_input}, error={repr(error)}"
        )
        record_birthday_error(
            command="生日",
            raw_input=raw_input,
            error=error,
            user_id=user_id,
            group_id=group_id,
        )
        await birthday_event.finish("生日查询时出了点问题，梦美已经把这次报错记下来了。")
    
    try:
        msg_list = get_birthday_msg_list(birthday_list)
    except Exception as error:
        logger.exception(
            "Birthday message rendering failed: "
            f"user_id={user_id}, group_id={group_id}, raw_input={raw_input}, error={repr(error)}"
        )
        record_birthday_error(
            command="生日",
            raw_input=raw_input,
            error=error,
            user_id=user_id,
            group_id=group_id,
        )
        await birthday_event.finish("生日信息整理失败了，梦美已经把这次报错记下来了。")

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
    try:
        await birthday_event.finish(birth_node)
    except (ActionFailed, ApiNotAvailable, NetworkError) as error:
        logger.warning(
            "Birthday response send failed: "
            f"user_id={user_id}, group_id={group_id}, raw_input={raw_input}, error={repr(error)}"
        )
        record_birthday_error(
            command="生日",
            raw_input=raw_input,
            error=error,
            user_id=user_id,
            group_id=group_id,
        )
        await birthday_event.finish("生日结果发送失败了，梦美已经把这次报错记下来了。")
    
    
@birthday_event.handle()
async def send_birthday_by_name(matcher: Matcher, event: GroupMessageEvent, args: Message=CommandArg()):
    msg = MessageSegment.at(event.user_id) + MessageSegment.text("\n")
    user_id = str(event.get_user_id())
    group_id = str(event.group_id)
    
    query_name = str(matcher.get_arg("character_name"))
    character = Character(query_name)
    if not character.init(config.character_json_path, config.image_base_folder):
        await birthday_event.finish(msg + f"梦美没有查询到名为{query_name}的角色信息，换个名称试试吧！")

    display_name = format_character_display_name(query_name, character.cha_name, character.matched_name)
    
    if character.birthday == "" or character.birthday == "unknown":
        await birthday_event.finish(msg + f"非常抱歉，梦美不知道{display_name}的生日")
    
    month, date = tuple(character.birthday.split('-'))
    try:
        await birthday_event.finish(msg + f"{display_name}的生日是{month}月{date}日")
    except (ActionFailed, ApiNotAvailable, NetworkError) as error:
        logger.warning(
            "Birthday by-name response send failed: "
            f"user_id={user_id}, group_id={group_id}, query_name={query_name}, error={repr(error)}"
        )
        record_birthday_error(
            command="生日",
            raw_input=query_name,
            error=error,
            user_id=user_id,
            group_id=group_id,
            extra_details={"matched_name": character.cha_name},
        )
        await birthday_event.finish("生日结果发送失败了，梦美已经把这次报错记下来了。")

async def daily_birthday_msg():
    bot = nonebot.get_bot()
    group_list: List[int] = [739177245, 943858715, 737574359, 496642207, 264271679, 1026440181, 961707929, 608533421, 762617891, 198894147, 485279600,102572884]   # TODO: Get all groups and send birthday messages to those in the whitelist.

    try:
        birthday_characters: List[str] = get_birthdays(config.character_json_path)
        msg_list = get_birthday_msg_list(birthday_characters)
    except Exception as error:
        logger.exception(f"Daily birthday generation failed: error={repr(error)}")
        record_birthday_error(
            command="生日广播",
            raw_input="daily_birthday_msg",
            error=error,
        )
        return
        
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
            try:
                await bot.call_api("send_group_msg", group_id=group_id, message=msg)
            except (ActionFailed, ApiNotAvailable, NetworkError) as error:
                logger.warning(
                    "Daily birthday send failed: "
                    f"group_id={group_id}, error={repr(error)}"
                )
                record_birthday_error(
                    command="生日广播",
                    raw_input="daily_birthday_msg",
                    error=error,
                    group_id=str(group_id),
                )
                break
    
    
@broadcast_event.handle()
async def broadcast_daily_birthday_msg(matcher: Matcher, event: GroupMessageEvent, args: Message=CommandArg()):
    if event.user_id != 295259537:
        await broadcast_event.finish("Permission denied.")
        return
    bot = nonebot.get_bot()
    group_list: List[int] = [739177245,943858715, 737574359, 496642207, 264271679, 1026440181, 961707929, 608533421, 762617891, 198894147, 485279600,102572884]   # TODO: Get all groups and send birthday messages to those in the whitelist.

    try:
        birthday_characters: List[str] = get_birthdays(config.character_json_path)
        msg_list = get_birthday_msg_list(birthday_characters)
    except Exception as error:
        logger.exception(f"Manual birthday broadcast generation failed: error={repr(error)}")
        record_birthday_error(
            command="生日广播",
            raw_input=args.extract_plain_text(),
            error=error,
            user_id=str(event.get_user_id()),
            group_id=str(event.group_id),
        )
        await broadcast_event.finish("生日广播整理失败了，梦美已经把这次报错记下来了。")
        
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
            try:
                await bot.call_api("send_group_msg", group_id=group_id, message=msg)
            except (ActionFailed, ApiNotAvailable, NetworkError) as error:
                logger.warning(
                    "Manual birthday broadcast send failed: "
                    f"group_id={group_id}, error={repr(error)}"
                )
                record_birthday_error(
                    command="生日广播",
                    raw_input=args.extract_plain_text(),
                    error=error,
                    user_id=str(event.get_user_id()),
                    group_id=str(group_id),
                )
                break

scheduler.add_job(daily_birthday_msg, "cron", hour=0, minute=0, second=0, id='daily_birthday', timezone=pytz.timezone("Asia/Shanghai"))
