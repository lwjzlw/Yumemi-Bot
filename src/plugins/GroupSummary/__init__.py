import nonebot
import asyncio
from nonebot import get_plugin_config, logger
from nonebot.plugin import PluginMetadata
from nonebot.adapters import Message
from nonebot.params import CommandArg
import pytz
from openai import AzureOpenAI
import openai
from openai import OpenAI
import os
from nonebot import require
require("nonebot_plugin_chatrecorder")
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_chatrecorder import get_message_records, get_messages_plain_text
from nonebot_plugin_uninfo import SceneType
from datetime import datetime, timedelta
from nonebot.exception import FinishedException
from anthropic import Anthropic
from nonebot.adapters.onebot.v11.exception import ActionFailed, ApiNotAvailable, NetworkError
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    GROUP,
    Message,
    MessageSegment
)
from .config import Config
from src.utils.error_history import (
    describe_exception_reason,
    extract_exception_details,
    record_recent_error,
)

__plugin_meta__ = PluginMetadata(
    name="chat",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)
DAILY_SUMMARY_ENABLED = False


def record_group_summary_error(
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


chat_event = nonebot.on_command("总结", priority=10, block=True)
system_message = '''
    你是一个消息总结助理。我会发给你一个qq群聊一天之内的聊天内容，你对聊天记录进行总结。请用“群友”来指代“群内成员”。你的总结应该是一段完整通顺的话，而不是分条列点。如果聊天记录较多，你可以选择一两个有趣话题进行详细总结，不要流水账式记录。你的总结应该符合聊天记录本身，不要添加聊天记录没有提到的内容。你应该使你的总结简洁、有趣、幽默，可以多玩梗。在你的回复中，只需要回复总结的内容，不要添加其他提示词。
'''

@chat_event.handle()
async def chat_handler(bot: Bot, event: GroupMessageEvent, args: Message=CommandArg()):
    if event.user_id != 295259537:
        await chat_event.finish("测试期间，仅允许bot管理者使用此功能。")
    raw_input = args.extract_plain_text()
    user_id = str(event.get_user_id())
    group_id = str(event.group_id)
    try:
        msgs = await get_messages_plain_text(
            scene_ids=[group_id],
            scene_types=[SceneType.GROUP],
            types=["message"],
            time_start=datetime.now() - timedelta(days=1),
        )
        msgs = [ msg for msg in msgs if not msg.startswith("#") ]
        prompt = "这是今天的群聊信息，请对它们进行总结:" + "\n".join(msgs)
        reponse = await asyncio.to_thread(get_response, prompt, model="deepseek-reasoner")
    except Exception as error:
        logger.exception(
            "GroupSummary generation failed: "
            f"user_id={user_id}, group_id={group_id}, error={repr(error)}"
        )
        record_group_summary_error(
            command="总结",
            raw_input=raw_input,
            error=error,
            user_id=user_id,
            group_id=group_id,
        )
        await chat_event.finish("群聊总结生成失败了，梦美已经把这次报错记下来了。")

    try:
        await chat_event.finish(f"今日群聊内容总结如下：\n {reponse}")
    except (ActionFailed, ApiNotAvailable, NetworkError) as error:
        logger.warning(
            "GroupSummary response send failed: "
            f"user_id={user_id}, group_id={group_id}, error={repr(error)}"
        )
        record_group_summary_error(
            command="总结",
            raw_input=raw_input,
            error=error,
            user_id=user_id,
            group_id=group_id,
        )
        await chat_event.finish("群聊总结发送失败了，梦美已经把这次报错记下来了。")

def get_deepseek_response(prompt: str, model = "deepseek-reasoner"):
    client = OpenAI(
        base_url='https://api.deepseek.com/v1',
        api_key=os.getenv("DEEPSEEK_API_KEY")
    )

    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system",  "content": system_message},
            {
                "role": "user",
                "content": prompt,
            }
        ],
        model=model,
    )
    return chat_completion.choices[0].message.content


def get_claude_response(prompt: str):
    client = Anthropic(
        base_url='https://api.openai-proxy.org/anthropic',
        api_key=os.getenv("CLAUDE_API_KEY"),
    )
    
    message = client.messages.create(
        max_tokens=2048,
        system=system_message,
        messages=[
		    {"role": "user", "content": prompt}
        ],
        model="claude-3-7-sonnet-20250219"
    )
    return message.content[0].text
    
def get_close_ai_response(prompt: str):
    client = OpenAI(
        base_url='https://yunwu.ai/v1',
        api_key=os.getenv("CLAUDE_API_KEY")
    )

    chat_completion = client.chat.completions.create(
        messages=[
            {"role": "system",  "content": system_message},
            {
                "role": "user",
                "content": prompt,
            }
        ],
        model="gemini-3-flash-preview",
    )
    return chat_completion.choices[0].message.content

def get_azure_response(prompt: str):
    azure_endpoint = os.getenv("OPENAI_ENDPOINT")
    api_key = os.getenv("OPENAI_API_KEY")
    api_version = os.getenv("OPENAI_API_VERSION")
    client = AzureOpenAI(
		azure_endpoint=azure_endpoint,
		api_key=api_key,
		api_version=api_version
	)
    
    deployment_name="gpt-35-turbo"   # Such things can be implemented in Config in the future.
    
    messages = [
		{"role": "system",  "content": system_message},
		{"role": "user", "content": prompt}
	]
    
    response = client.chat.completions.create(
		model=deployment_name,
		messages=messages
	)
    
    return response.choices[0].message.content

def get_response(prompt, model="deepseek-reasoner"):
    return get_close_ai_response(prompt)



async def daily_summary():
    bot = nonebot.get_bot()
    white_list = config.white_list
    for group in white_list:
        
        try:
            msgs = await get_messages_plain_text(
                scene_ids=[str(group)],
                scene_types=[SceneType.GROUP],
                types=["message"],
                time_start=datetime.now() - timedelta(days=1)
            )
            msgs = [ msg for msg in msgs if not msg.startswith("#") ]
            msgs = [ msg for msg in msgs if not "梦美" in msg ]
            if not msgs:
                continue
            prompt = "这是今天的群聊信息，请对它们进行总结:" + "\n".join(msgs)
            reponse = await asyncio.to_thread(get_response, prompt)
            msg = f"今日群聊内容总结如下(By Gemini-3-Flash)：\n {reponse}"
            await bot.call_api("send_group_msg", group_id=group, message=msg)
        except Exception as error:
            logger.exception(f"Daily summary failed: group_id={group}, error={repr(error)}")
            record_group_summary_error(
                command="总结",
                raw_input="daily_summary",
                error=error,
                group_id=str(group),
            )
            try:
                await bot.call_api("send_group_msg", group_id=group, message="进行每日总结时发生错误："+repr(error))
            except (ActionFailed, ApiNotAvailable, NetworkError) as send_error:
                logger.warning(
                    "Daily summary failure notice send failed: "
                    f"group_id={group}, error={repr(send_error)}"
                )
                record_group_summary_error(
                    command="总结",
                    raw_input="daily_summary:error_notice",
                    error=send_error,
                    group_id=str(group),
                )
            #await bot.call_api("send_group_msg", group_id=group, message="尝试用低级模型进行总结……")
            #reponse = get_response("这是今天的群聊信息，请对它们进行总结:"+"\n".join(msgs), model="deepseek-chat")
           # msg = f"今日群聊内容总结如下(By deepseek-chat)：\n {reponse}"
            #await bot.call_api("send_group_msg", group_id=group, message=msg)
            
            
            

if DAILY_SUMMARY_ENABLED:
    scheduler.add_job(
        daily_summary,
        "cron",
        hour=23,
        minute=50,
        second=0,
        id="daily_summary",
        timezone=pytz.timezone("Asia/Shanghai"),
    )
else:
    logger.info("Daily group summary scheduler is disabled.")
