import nonebot
from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot.adapters import Message
from nonebot.params import CommandArg

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="echo",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

echo = nonebot.on_command("echo", priority=5, block=True)

@echo.handle()
async def echo_handler(args: Message=CommandArg()):
    content = args.extract_plain_text()
    await echo.finish(content)
    

