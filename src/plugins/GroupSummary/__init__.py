import nonebot
from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot.adapters import Message
from nonebot.params import CommandArg
import pytz
from openai import AzureOpenAI
import openai
import os
from nonebot import require
import nonebot_plugin_session
from nonebot_plugin_session import extract_session, SessionIdType
require("nonebot_plugin_chatrecorder")
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_chatrecorder import get_message_records, get_messages_plain_text
from datetime import datetime, timedelta

from anthropic import Anthropic
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    GROUP,
    Message,
    MessageSegment
)
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="chat",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)


chat_event = nonebot.on_command("总结", priority=10, block=True)
system_message = '''
    你是一个消息总结助理。我会发给你一个群聊一天之内的聊天内容，你用200字以内对聊天记录进行总结。请用“群友”来指代“群内成员”。在你的回复中，只需要回复总结的内容，不需要添加其他任何提示。
'''

@chat_event.handle()
async def chat_handler(bot: Bot, event: GroupMessageEvent, args: Message=CommandArg()):
    if event.user_id != 295259537:
        await chat_event.finish("测试期间，仅允许bot管理者使用此功能。")
    session = extract_session(bot, event)
    msgs = await get_messages_plain_text(
        session=session,
        id_type=SessionIdType.GROUP,
        types=["message"],
        time_start=datetime.now() - timedelta(days=1),
    )
    
    reponse = get_response("这是今天的群聊信息，请对它们进行总结：\n".join(msgs))
    await chat_event.finish(f"今日群聊内容总结如下：(By claude-3-5-haiku-20241022)\n {reponse}")


def get_claude_response(prompt: str):
    try:
        client = Anthropic(
            base_url='https://api.openai-proxy.org/anthropic',
            api_key=os.getenv("CLAUDE_API_KEY"),
        )
        
        message = client.messages.create(
            max_tokens=1024,
            system=system_message,
            messages=[
			    {"role": "user", "content": prompt}
            ],
            model="claude-3-5-haiku-20241022"
        )
        return message.content[0].text
    except Exception as e:
        return repr(e)

def get_azure_response(prompt: str):
    try:
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
    except Exception as e:
        return repr(e)

def get_response(prompt: str):
    return get_claude_response(prompt)



async def daily_summary():
    bot = nonebot.get_bot()
    white_list = config.white_list
    for group in white_list:
        msgs = await get_messages_plain_text(
            id2s=[str(group)],
            types=["message"],
            time_start=datetime.now() - timedelta(days=1)
        )
        msgs = [ msg for msg in msgs if not msg.startswith("#") ]
        reponse = get_response("这是今天的群聊信息，请对它们进行总结：\n".join(msgs))
        msg = f"今日群聊内容总结如下：(By claude-3-5-haiku-20241022)\n {reponse}"
        await bot.call_api("send_group_msg", group_id=group, message=msg)

scheduler.add_job(daily_summary, "cron", hour=0, minute=0, second=0, id='daily_summary', timezone=pytz.timezone("Asia/Shanghai"))