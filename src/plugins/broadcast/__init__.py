import nonebot
from nonebot import logger
from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot.adapters import Message
from nonebot.params import CommandArg
import pytz
from openai import AzureOpenAI
import openai
from openai import OpenAI
import os
from nonebot import require
import nonebot_plugin_session
from nonebot_plugin_session import extract_session, SessionIdType
require("nonebot_plugin_chatrecorder")
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_chatrecorder import get_message_records, get_messages_plain_text
from datetime import datetime, timedelta
from nonebot.exception import FinishedException
from anthropic import Anthropic
from nonebot.permission import SUPERUSER
from nonebot.params import ArgPlainText
from nonebot.adapters.onebot.v11.exception import ActionFailed, ApiNotAvailable, NetworkError
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    GROUP,
    Message,
    MessageSegment
)
from src.utils.error_history import (
    describe_exception_reason,
    extract_exception_details,
    record_recent_error,
)

__plugin_meta__ = PluginMetadata(
    name="broadcast",
    description="",
    usage="",
)

#chat_event = nonebot.on_command("总结", priority=10, block=True)
test_event = nonebot.on_command("超管测试", permission=SUPERUSER)
broadcast_event = nonebot.on_command("广播", permission=SUPERUSER)
get_group_list_event = nonebot.on_command("获取群列表", permission=SUPERUSER)


def record_broadcast_error(
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

@test_event.handle()
async def test_handler(bot: Bot, event: GroupMessageEvent, args: Message=CommandArg()):
    await test_event.finish("测试成功")

@get_group_list_event.handle()
async def get_group_list_handler(bot: Bot):
    try:
        group_list = await  bot.get_group_list()
    except (ActionFailed, ApiNotAvailable, NetworkError) as error:
        logger.warning(f"Get group list failed: error={repr(error)}")
        record_broadcast_error(
            command="获取群列表",
            raw_input="",
            error=error,
        )
        await get_group_list_event.finish("获取群列表失败了，梦美已经把这次报错记下来了。")
    group_info = "group_id\tgroup_name\tmember_count\tmax_member_count\n"
    for group in group_list:
        group_id = group['group_id']
        group_name = group['group_name']
        member_count = group['member_count']
        max_member_count = group['max_member_count']
        group_info += f"{group_id}\t{group_name}\t{member_count}\t{max_member_count}\n"
    await get_group_list_event.finish(group_info)

@broadcast_event.got("content", prompt="请输入广播内容，输入“取消”结束广播")
async def broadcast_handler(bot: Bot, event: GroupMessageEvent, content: str = ArgPlainText()):
    if content == "取消":
        await broadcast_event.finish("广播已取消")
    user_id = str(event.get_user_id())
    try:
        group_list = await bot.get_group_list()
    except (ActionFailed, ApiNotAvailable, NetworkError) as error:
        logger.warning(f"Broadcast group list fetch failed: error={repr(error)}")
        record_broadcast_error(
            command="广播",
            raw_input=content,
            error=error,
            user_id=user_id,
        )
        await broadcast_event.finish("广播前获取群列表失败了，梦美已经把这次报错记下来了。")
    group_id_list = [ info['group_id'] for info in group_list ]
    total_num = len(group_id_list)
    error_list = []
    for group_id in group_id_list:
        try:
            await bot.send_group_msg(group_id=group_id, message=content)
        except (ActionFailed, ApiNotAvailable, NetworkError) as error:
            logger.warning(
                "Broadcast send failed: "
                f"group_id={group_id}, error={repr(error)}"
            )
            record_broadcast_error(
                command="广播",
                raw_input=content,
                error=error,
                user_id=user_id,
                group_id=str(group_id),
                extra_details={"group_total": str(total_num)},
            )
            error_list.append(group_id)
            continue
    try:
        await broadcast_event.send(f"发送失败群聊：{error_list}")
    except (ActionFailed, ApiNotAvailable, NetworkError) as error:
        logger.warning(f"Broadcast result send failed: error={repr(error)}")
        record_broadcast_error(
            command="广播",
            raw_input=content,
            error=error,
            user_id=user_id,
            extra_details={"failed_group_count": str(len(error_list))},
        )
        await broadcast_event.finish("广播结果回执发送失败了，梦美已经把这次报错记下来了。")
