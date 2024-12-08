import nonebot
from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot.adapters import Message
from nonebot.params import CommandArg
from nonebot.matcher import Matcher
from nonebot import require
from nonebot.exception import FinishedException
import json
import subprocess
import traceback
from nonebot_plugin_apscheduler import scheduler
from typing import List, Dict, Tuple

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

def get_name_cid(name: str) -> Tuple[str, str]:
    with open(config.character_json_path, 'r') as f:
        data = json.load(f)
        if name in data:
            return name, data[name]["cid"]
        for cha_name, information in data.items():
            if not information["aliases"]:
                continue
            for alias in information["aliases"]:
                if alias.lower() == name.lower():
                    return cha_name, information["cid"]
    return "", ""

def get_vndb(cid: str):
    cmd = f'''
    curl https://api.vndb.org/kana/character --header 'Content-Type: application/json' --data '{{
    "filters": ["id", "=", "{cid}"],
    "fields": "name, original, image.url, height, weight, bust, waist, hips, cup, age, birthday, vns.title"
    }}'
    '''
    try:
        response = subprocess.check_output(cmd, shell=True, text=True)
        response = json.loads(response)
        result = response["results"][0]
        return result
    except Exception as e:
        return None
    



query_by_name = nonebot.on_command("查询", aliases={"角色"}, priority=10, block=True)

@query_by_name.handle()
async def _(matcher: Matcher, event: GroupMessageEvent, args: Message=CommandArg()):
    user_id = str(event.get_user_id())
    args: str = args.extract_plain_text()
    if not args:
        await query_by_name.finish("请输入查询的角色名！")
    else:
        try:
            name, cid = get_name_cid(args)
            if not cid:
                await query_by_name.finish(MessageSegment.at(user_id)+f" 梦美没有查询到名为{args}的角色，换个名称试试吧！")
            data = get_vndb(cid)
            if not data:
                await query_by_name.finish(MessageSegment.at(user_id)+f" 查询角色{args}数据时出错")
            msg = MessageSegment.text(f"{name}\n")
            msg += MessageSegment.text(f"{data['name']}")
            if data["original"]:
                msg += MessageSegment.text(f"/{data['original']}")
            msg += "\n"
            
            if data["image"] and data["image"]["url"]:
                msg += MessageSegment.image(data["image"]["url"])
            if data["birthday"]:
                msg += f"生日：{data['birthday'][0]}-{data['birthday'][1]}\n"
                #msg += f"生日：{data['birthday']}\n"
            if data["vns"]:
                vns = data["vns"]
                vns_dict = dict()
                for vn in vns:
                    vns_dict[vn["id"]] = vn["title"]
                msg += f"登场作品：{', '.join(vns_dict.values())}\n"
            if data["age"]:
                msg += f"年龄：{data['age']}/ "
            if data['height']:
                msg += f"身高：{data['height']}cm/ "
            if data["weight"]:
                msg += f"体重：{data['weight']}kg/ "
            msg += "\n"
            if data["bust"]:
                msg += f"胸围：{data['bust']}cm/ "
            if data["waist"]:
                msg += f"腰围：{data['waist']}cm/ "
            if data["hips"]:
                msg += f"臀围：{data['hips']}cm/ "
            if data["cup"]:
                msg += f"罩杯：{data['cup']}" 
            msg += "\n以上数据来源于vndb"
            await query_by_name.finish(msg)
        except FinishedException as f:
            return
        except Exception as e:
            #error_info = traceback.format_exc()
            error_info = ""
            await query_by_name.finish(f"{repr(e)}\n{error_info}")
    
   