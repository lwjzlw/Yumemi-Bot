# Yumemi-Bot

Yumemi-Bot 是一个基于 NoneBot2 + OneBot V11 + NapCat 的 QQ 群聊机器人项目。当前主运行环境已经迁移到阿里云 ECS，本地 WSL 主要用于开发、整理资源和同步部署。

## 先读这里

继续维护前建议按这个顺序看：

1. `README_HANDOFF.md`
2. `README_CLOUD.md`
3. `git status --short`

旧版 README 的部署说明已经不再代表现状；本文件只保留当前维护入口。

## 当前核心约定

- 统一角色数据源：`resource/character_data.json`
- 作品别名表：`resource/game_aliases.json`
- 角色匹配逻辑：`src/utils/character_data.py`
- 本地图库：`resource/images/<标准角色名>/`
- 近期重点插件：`photo`、`vndb`、`birthday`、`KeyProphecy`、`logview`
- Chat/API/群白名单配置：`README_CHAT.md`

## 常用管理

本机管理 bot / 云端服务：

```bash
yumemi
./manage_bot
/home/lwjzlw/manage_bot.sh
```

常用直达命令：

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
./manage_bot sync-code
```

`chat-on/off` 只切换 `.env` 里的 `chat_enabled`；群白名单仍按 `README_CHAT.md` 配置，改完需要重启 bot 才生效。

图库维护工作台：

```bash
yumemi_imagetools
```

常见图库流程：

```text
1 sync-temp   同步 Windows temp 到 WSL temp
2 import      导入 temp 图片
3 organize    整理图库命名
4 dedupe      删除重复图片
Q check       检查图库
C cloud       同步到云端
G git-add     暂存图库改动
```

云端部署和服务信息见 `README_CLOUD.md`。

## 运行

开发环境可直接运行：

```bash
python bot.py
```

线上运行通过 systemd 管理：

```bash
/home/lwjzlw/manage_bot.sh cloud-status
/home/lwjzlw/manage_bot.sh cloud-restart
```

## 注意

当前工作区经常会有未提交改动。继续维护时不要随意 `git reset`、`git checkout --` 或删除用户现有文件；先确认改动来源和目的。
