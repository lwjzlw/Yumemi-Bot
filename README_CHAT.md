# Yumemi chat config

Chat 配置入口是项目根目录的 `.env`。

本地路径：

```text
/home/ubuntu/Yumemi-Bot/.env
```

云端路径：

```text
/home/yumemi/Yumemi-Bot/.env
```

修改云端 `.env` 后需要重启 bot：

```bash
/home/lwjzlw/manage_bot.sh cloud-restart
```

本地开发重启则重新运行：

```bash
python bot.py
```

也可以直接从工作台切换 chat 开关；这些命令只修改 `chat_enabled`，不会打印密钥内容：

```bash
./manage_bot chat-status
./manage_bot chat-on
./manage_bot chat-off
./manage_bot chat-agent-on
./manage_bot chat-agent-network-on
./manage_bot restart-bot
./manage_bot cloud-chat-status
./manage_bot cloud-chat-on
./manage_bot cloud-chat-off
./manage_bot cloud-chat-agent-on
./manage_bot cloud-chat-agent-network-on
./manage_bot cloud-restart-bot
```

## 最小配置

默认 `chat_enabled=false`，白名单为空，所以 chat 不会响应任何群聊。

要开放某个测试群，加入：

```dotenv
chat_enabled=true
chat_group_whitelist=[123456789]
```

多个群：

```dotenv
chat_group_whitelist=[123456789,987654321]
```

也支持逗号写法：

```dotenv
chat_group_whitelist=123456789,987654321
```

为了测试安全，保持白名单为空就是“启用代码但不开放任何群”的状态：

```dotenv
chat_group_whitelist=[]
```

## API provider

当前支持：

```dotenv
chat_provider=closeai
```

可选值：

```text
closeai
deepseek
claude
azure
```

### closeai

`closeai` 当前走 `https://yunwu.ai/v1`，使用 `CLAUDE_API_KEY` 这个环境变量作为 key。

```dotenv
chat_provider=closeai
CLAUDE_API_KEY=填你的_key
chat_closeai_model=gemini-3-flash-preview
```

### deepseek

```dotenv
chat_provider=deepseek
DEEPSEEK_API_KEY=填你的_key
chat_deepseek_model=deepseek-v4-flash
```

### claude

`claude` 当前走 `https://api.openai-proxy.org/anthropic`。

```dotenv
chat_provider=claude
CLAUDE_API_KEY=填你的_key
chat_claude_model=claude-3-5-haiku-20241022
```

### azure

```dotenv
chat_provider=azure
OPENAI_ENDPOINT=填你的_azure_endpoint
OPENAI_API_KEY=填你的_key
OPENAI_API_VERSION=填你的_api_version
chat_azure_deployment=gpt-35-turbo
```

## 记忆和 VNDB

短期记忆按群保存，并写入本地缓存文件；重启后仍会读取最近窗口：

```dotenv
chat_memory_max_messages=20
```

`20` 的含义是最近 20 条消息，包含 user 和 assistant 两边。

默认会记录白名单群里的全部纯文本消息，而不只是 @梦美 的消息：

```dotenv
chat_memory_record_all_group_messages=true
```

默认缓存路径：

```text
resource/chat_memory_cache.json
```

可以在 `.env` 里改到其他位置：

```dotenv
chat_memory_cache_path=/home/yumemi/Yumemi-Bot/resource/chat_memory_cache.json
```

想清空记忆时，停止或重启前删除这个缓存文件即可；它已经被 `.gitignore` 忽略，不会上传到 git。

角色补充资料默认会按需查询 VNDB，失败会静默回退：

```dotenv
chat_vndb_context_enabled=true
chat_vndb_context_timeout=4.0
```

如果测试时不想访问 VNDB：

```dotenv
chat_vndb_context_enabled=false
```

## Chat Agent

Chat Agent 默认关闭。开启后，梦美可以在模型工具调用真实发生时写入结构化记忆草稿；联网搜索仍需要单独打开。

```dotenv
chat_agent_enabled=true
chat_agent_allow_network=true
chat_agent_memory_path=resource/chat_agent_memory.jsonl
chat_agent_max_tool_rounds=8
```

当前工具范围：

```text
local_time              获取当前日期和时间
get_weather             获取指定地点当前天气和短期预报，需要 chat_agent_allow_network=true
write_memory_entry      写入 Key 角色 / Key 梗 / 群聊成员记忆条目
search_memory_entries   搜索已有条目，避免重复
web_search              搜索公开网页，需要 chat_agent_allow_network=true
fetch_url               读取公开网页，需要 chat_agent_allow_network=true
```

记忆条目写入 `resource/chat_agent_memory.jsonl`，已被 `.gitignore` 忽略。它是草稿知识库，不替代 `resource/character_data.json`；确认无误后再手工整理进正式角色数据。

Chat 模型调用会把 token 用量写入 `resource/chat_token_usage.jsonl`。记录只包含 provider、model、实际/估算 token、消息数量和工具数量，不保存 prompt 正文或 API key。

## 检查配置

检查当前 `.env` 的 chat 配置，不打印密钥内容：

```bash
python3 tools/check_chat_config.py
```

指定其他 env 文件：

```bash
python3 tools/check_chat_config.py /home/yumemi/Yumemi-Bot/.env
```

## 上传到云端

只改了 `.env`：

```bash
rsync -azR -e "ssh -i /home/lwjzlw/.ssh/yumemi_aliyun" \
  .env \
  yumemi@47.100.170.173:/home/yumemi/Yumemi-Bot/

ssh -i /home/lwjzlw/.ssh/yumemi_aliyun yumemi@47.100.170.173 \
  "sudo systemctl restart yumemi-bot"
```

只改了梦美提示词：

```bash
rsync -azR -e "ssh -i /home/lwjzlw/.ssh/yumemi_aliyun" \
  src/plugins/chat/sys_msg.py \
  yumemi@47.100.170.173:/home/yumemi/Yumemi-Bot/

ssh -i /home/lwjzlw/.ssh/yumemi_aliyun yumemi@47.100.170.173 \
  "sudo systemctl restart yumemi-bot"
```

改了 chat 代码或配置说明：

```bash
rsync -azR -e "ssh -i /home/lwjzlw/.ssh/yumemi_aliyun" \
  .env README_CHAT.md .gitignore src/utils/paths.py src/plugins/chat/ tools/check_chat_config.py \
  yumemi@47.100.170.173:/home/yumemi/Yumemi-Bot/

ssh -i /home/lwjzlw/.ssh/yumemi_aliyun yumemi@47.100.170.173 \
  "cd /home/yumemi/Yumemi-Bot && python3 tools/check_chat_config.py .env && .venv/bin/python -m py_compile src/plugins/chat/*.py src/utils/paths.py && sudo systemctl restart yumemi-bot"
```

查看云端 bot 状态：

```bash
ssh -i /home/lwjzlw/.ssh/yumemi_aliyun yumemi@47.100.170.173 \
  "sudo systemctl --no-pager --lines=20 status yumemi-bot"
```
