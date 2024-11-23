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