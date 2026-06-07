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

import pytz
from datetime import datetime
import os

from .config import Config
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    GROUP,
    Message,
    MessageSegment
)


__plugin_usage__ = f"""

"""


__plugin_meta__ = PluginMetadata(
    name="help",
    description="",
    usage=__plugin_usage__,
    config=Config,
)

config = get_plugin_config(Config)


help_event = nonebot.on_command("help", aliases={"帮助"}, priority=8, block=True)


@help_event.handle()
async def birthday_event_handler(matcher: Matcher, event: GroupMessageEvent, args: Message=CommandArg()):
    help_msg = """命令全集：
    #help / #帮助：显示本条信息
    #占卜：获取今日运势及随机 Key 社老婆
    #抢 / #抢老婆 角色名：抢指定 Key 社老婆
    #查询 [角色名]：优先查询本地角色资料，必要时补充 VNDB 信息；支持别名和模糊匹配
    #生日：查询今天过生日的角色
    #生日 [角色名]：查询指定角色的生日；支持别名和模糊匹配
    #生日 [月] [日]：查询某月某日过生日的角色
    #图片 / #涩图 [角色名] [数量]：优先按角色识别并随机发送图片；也支持“随机”或作品名
    #r / #roll / #随机数 a：获得 [1, a] 间的随机整数
    #r / #roll / #随机数 a b：获得 [a, b] 间的随机整数
    #日志：管理员默认查看最近 5 条报错
    #日志 [报错|bot|napcat|全部] [行数] [角色名] [编号/文件名]：管理员查看报错或日志，也可顺手定位某张本地图

补充说明：
    查询、生日、图片等角色检索功能支持标准名、别名和较自然的模糊匹配。
    占卜结果每天固定；如果图片偶尔发送失败，多半是网络或平台侧波动，稍后再试即可。

其他功能：
    每日群聊总结：每天晚上，用大模型为当日的群聊内容进行总结
    Key 社生日推送：每日 0 点，推送当日过生日的 Key 社角色

目前 bot 仍处于测试阶段，羽未最近比较忙,有bug可以尝试联系风子(也很忙)

暂时不处理新入群请求
    """
    
    help_node =[]
    
    help_node.append(
            MessageSegment.node_custom(
                user_id=os.getenv("QQ_NUMBER"),
                nickname=os.getenv("QQ_ID"),
                content=help_msg,
            )
        )
    # birth_node = MessageSegment.node_custom(user_id="2544412429", nickname="星野梦美", content= msg_list)
    # for msg in msg_list: 
    #     await birthday_event.send(msg)
    await help_event.finish(help_node)
    
