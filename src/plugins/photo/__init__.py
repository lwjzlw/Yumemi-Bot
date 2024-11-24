import nonebot
from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot.adapters import Message
from nonebot.params import CommandArg
import os

from .config import PluginConfig
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    GROUP,
    Message,
    MessageSegment
)

__plugin_meta__ = PluginMetadata(
    name="photo",
    description="",
    usage="",
    config=PluginConfig,
)

config = get_plugin_config(PluginConfig)

photo_event = nonebot.on_command("照片", aliases={"图片"}, priority=5, block=True)

@photo_event.handle()
async def _(event: GroupMessageEvent, args: Message=CommandArg()):
    message_id = event.message_id
    role_name = args.extract_plain_text()
    msg = MessageSegment.reply(message_id)
    
    if not role_name:
        msg += MessageSegment.text("请输入角色名！\n")
        photo_event.finish(msg)
    
    resource_folder = "/home/ubuntu/Yumemi-Bot/resources/images"
    photo_path = os.path.join(resource_folder, f"{role_name}.jpg")
    msg += MessageSegment.image(photo_path)
    
    await photo_event.finish(msg)