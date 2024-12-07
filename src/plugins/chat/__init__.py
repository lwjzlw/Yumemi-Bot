import nonebot
from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot.adapters import Message
from nonebot.params import CommandArg
from openai import AzureOpenAI
import openai
import os
from .sys_msg import system_message
from anthropic import Anthropic
from nonebot.adapters.onebot.v11 import (
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


chat_event = nonebot.on_command("chat", priority=10, block=True)

@chat_event.handle()
async def chat_handler(event: GroupMessageEvent, args: Message=CommandArg()):
    if content := args.extract_plain_text():
        await chat_event.send("梦美正在思考中……")
        response = get_response(content)
        msgs = [ MessageSegment.at(event.user_id), "\n" + response ]
        node_msg = []
        for msg in msgs:
            node_msg.append(
                MessageSegment.node_custom(
                    user_id=os.getenv("QQ_NUMBER"),
                    nickname=os.getenv("QQ_ID"),
                    content=msg,
                )
            )
        await chat_event.finish(node_msg)
    else:
        await chat_event.finish("你想和梦美聊些什么？请输入内容啦！")


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