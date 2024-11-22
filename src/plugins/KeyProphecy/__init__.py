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

__plugin_meta__ = PluginMetadata(
    name="KeyProphecy",
    description="",
    usage="",
    config=PluginConfig,
)

config = get_plugin_config(PluginConfig)

prophecy_event = nonebot.on_command("今日运势", aliases={"抽签", "占卜"}, priority=8, block=True)

@prophecy_event.handle()
async def _(event: GroupMessageEvent):
    user_id = str(event.get_user_id())
    prophecier = Prophecy(user_id)
    heroine = prophecier.getHeroine()
    lucky_point = prophecier.getLuckyPoint()
    dos, donts = prophecier.getDosDonts()
    lucky_thing = prophecier.getLuckyThing()
    
    msg = MessageSegment.at(user_id)
    msg += MessageSegment.text(f"\n你的今日运势为：{lucky_point}\n\n")
    msg += MessageSegment.text(f"你今日的key社老婆为: {heroine}\n")
    msg += MessageSegment.text(f"[这里想加个老婆照片]\n\n")
    msg += MessageSegment.text(f"宜: {dos[0]}、{dos[1]}、{dos[2]}\n")
    msg += MessageSegment.text(f"忌: {donts[0]}、{donts[1]}、{donts[2]}\n\n")
    msg += MessageSegment.text(f"占卜结果显示今天你会{lucky_thing}哦！")
    
    await prophecy_event.finish(msg)