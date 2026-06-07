import nonebot
from nonebot import get_plugin_config, logger
from nonebot.plugin import PluginMetadata
from nonebot.adapters import Message
from nonebot.params import CommandArg
from nonebot.matcher import Matcher
from nonebot import require
from nonebot.exception import FinishedException
import json
import random
import subprocess
import traceback
from nonebot_plugin_apscheduler import scheduler
from typing import Dict, List, Tuple

import pytz
from datetime import datetime
import os

from .config import PluginConfig
from src.utils.character_data import (
    get_character_profile,
    list_character_images,
    normalize_lookup_text,
)
from src.utils.error_history import record_recent_error
from src.utils.error_history import describe_exception_reason, extract_exception_details
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    GROUP,
    Message,
    MessageSegment,
    Bot
)
from nonebot.adapters.onebot.v11.exception import ActionFailed, ApiNotAvailable, NetworkError


__plugin_usage__ = f"""
1. 输入 “#查询 角色名” 查询角色信息；
"""


__plugin_meta__ = PluginMetadata(
    name="vndb",
    description="",
    usage=__plugin_usage__,
    config=PluginConfig,
)

config = get_plugin_config(PluginConfig)


def record_vndb_error(
    *,
    raw_input: str,
    error: Exception,
    user_id: str = "",
    group_id: str = "",
    extra_details: dict[str, str] | None = None,
    reason_action: str = "查询",
) -> None:
    details = {
        "user_id": user_id,
        "group_id": group_id,
        **extract_exception_details(error),
    }
    if extra_details:
        details.update(extra_details)
    record_recent_error(
        command="查询",
        raw_input=raw_input,
        reason=describe_exception_reason(reason_action, error),
        details=details,
    )

def get_name_cid(name: str) -> Tuple[str, str]:
    profile = get_character_profile(name, config.character_json_path)
    if profile is None:
        return "", ""
    return profile.name, profile.cid


def should_query_vndb(profile) -> bool:
    if profile is None or not profile.cid:
        return False
    return not all([profile.birthday, profile.game_name, profile.age])


def format_local_character_message(display_name: str, profile) -> MessageSegment:
    msg = MessageSegment.text(f"{display_name}\n")
    msg += MessageSegment.text(f"作品名：{profile.game_name or '未知'}\n")
    if profile.birthday:
        msg += MessageSegment.text(f"生日：{profile.birthday}\n")
    if profile.cv:
        msg += MessageSegment.text(f"CV：{profile.cv}\n")
    if profile.staff:
        msg += MessageSegment.text(f"画师：{profile.staff}\n")
    if profile.age:
        msg += MessageSegment.text(f"设定：{profile.age}\n")
    if profile.tag:
        msg += MessageSegment.text(f"所属：{profile.tag}\n")
    if profile.like:
        msg += MessageSegment.text(f"喜欢/吐槽：{profile.like}\n")
    return msg


def format_vndb_supplement(profile, data: dict) -> MessageSegment:
    msg = MessageSegment.text("")
    if data.get("original"):
        msg += MessageSegment.text(f"原文名：{data['original']}\n")
    if data.get("birthday") and not profile.birthday:
        msg += MessageSegment.text(f"VNDB生日：{data['birthday'][0]}-{data['birthday'][1]}\n")
    if data.get("vns") and not profile.game_name:
        vns_dict = {}
        for vn in data["vns"]:
            vns_dict[vn["id"]] = vn["title"]
        msg += MessageSegment.text(f"VNDB登场作品：{', '.join(vns_dict.values())}\n")

    body_parts = []
    if data.get("age") and not profile.age:
        body_parts.append(f"年龄：{data['age']}")
    if data.get("height") and not profile.age:
        body_parts.append(f"身高：{data['height']}cm")
    if data.get("weight") and not profile.age:
        body_parts.append(f"体重：{data['weight']}kg")
    if body_parts:
        msg += MessageSegment.text(" / ".join(body_parts) + "\n")

    measure_parts = []
    if data.get("bust") and not profile.age:
        measure_parts.append(f"胸围：{data['bust']}cm")
    if data.get("waist") and not profile.age:
        measure_parts.append(f"腰围：{data['waist']}cm")
    if data.get("hips") and not profile.age:
        measure_parts.append(f"臀围：{data['hips']}cm")
    if data.get("cup") and not profile.age:
        measure_parts.append(f"罩杯：{data['cup']}")
    if measure_parts:
        msg += MessageSegment.text(" / ".join(measure_parts) + "\n")

    if str(msg):
        msg += MessageSegment.text("以上补充数据来源于 VNDB")
    return msg

def get_vndb(cid: str):
    cmd = f'''
    curl https://api.vndb.org/kana/character --header 'Content-Type: application/json' --data '{{
    "filters": ["id", "=", "{cid}"],
    "fields": "name, original, image.url, height, weight, bust, waist, hips, cup, age, birthday, vns.title"
    }}'
    '''
    response = subprocess.check_output(cmd, shell=True, text=True)
    response = json.loads(response)
    result = response["results"][0]
    return result
    



query_by_name = nonebot.on_command("查询", aliases={"角色"}, priority=10, block=True)

@query_by_name.handle()
async def _(bot: Bot, matcher: Matcher, event: GroupMessageEvent, args: Message=CommandArg()):
    user_id = str(event.get_user_id())
    group_id = str(event.group_id)
    args: str = args.extract_plain_text()
    if not args:
        await query_by_name.finish("请输入查询的角色名！")
    else:
        try:
            profile = get_character_profile(args, config.character_json_path)
            if profile is None:
                await query_by_name.finish(MessageSegment.at(user_id)+f" 梦美没有查询到名为{args}的角色，换个名称试试吧！")

            name = profile.name
            matched_name = profile.matched_name or name
            if normalize_lookup_text(args) == normalize_lookup_text(name):
                display_name = name
            elif normalize_lookup_text(args) == normalize_lookup_text(matched_name):
                display_name = f"{name}（{matched_name}）"
            else:
                display_name = f"{name}（{args}→{matched_name}）"
            msg = format_local_character_message(display_name, profile)

            image_list = list_character_images(name, config.image_base_folder)
            if image_list:
                msg += MessageSegment.image(random.choice(image_list))

            data = None
            if should_query_vndb(profile):
                try:
                    data = get_vndb(profile.cid)
                except Exception as error:
                    logger.warning(
                        "VNDB supplement fetch failed, fallback to local profile only: "
                        f"user_id={user_id}, group_id={group_id}, cid={profile.cid}, error={repr(error)}"
                    )
                    record_vndb_error(
                        raw_input=args,
                        error=error,
                        user_id=user_id,
                        group_id=group_id,
                        extra_details={"cid": profile.cid, "matched_name": profile.name},
                        reason_action="查询补充资料",
                    )
                    data = None

            if data:
                supplement = format_vndb_supplement(profile, data)
                if str(supplement):
                    msg += MessageSegment.text("\n")
                    msg += supplement

            try:
                await query_by_name.send(msg)
            except (ActionFailed, ApiNotAvailable, NetworkError) as error:
                logger.warning(
                    "VNDB query response send failed: "
                    f"user_id={user_id}, group_id={group_id}, query={args}, error={repr(error)}"
                )
                record_vndb_error(
                    raw_input=args,
                    error=error,
                    user_id=user_id,
                    group_id=group_id,
                    extra_details={"matched_name": name},
                )
                await query_by_name.finish("查询结果发送失败了，梦美已经把这次报错记下来了。")
        except FinishedException as f:
            return
        except Exception as e:
            #error_info = traceback.format_exc()
            error_info = ""
            logger.exception(
                "Character query failed: "
                f"user_id={user_id}, group_id={group_id}, query={args}, error={repr(e)}"
            )
            record_vndb_error(
                raw_input=args,
                error=e,
                user_id=user_id,
                group_id=group_id,
                reason_action="角色查询",
            )
            try:
                await query_by_name.send(f"查询失败：前方拥堵，请稍后再试")
            except (ActionFailed, ApiNotAvailable, NetworkError) as send_error:
                logger.warning(
                    "VNDB failure notice send failed: "
                    f"user_id={user_id}, group_id={group_id}, query={args}, error={repr(send_error)}"
                )
                record_vndb_error(
                    raw_input=args,
                    error=send_error,
                    user_id=user_id,
                    group_id=group_id,
                    reason_action="查询失败提示发送",
                )
            #await bot.send_msg(group_id=943858715, message=repr(e)+str(data))
    
   
