# Yumemi-Bot Handoff

这份文档给新的维护对话快速接管用。不要先按旧经验判断项目，先读这里和 `README_CLOUD.md`。

## 当前状态简述

- 项目是 NoneBot2 + OneBot V11 + NapCat 的 QQ 群聊机器人。
- 主运行环境已经迁移到阿里云 ECS，本地 WSL 主要用于开发、图库整理和同步云端。
- 当前维护分支是 `maintenance-2026-06-07`，已推送到 origin；继续前仍必须先看 `git status --short`，不要随意回退用户未提交改动。
- `README.md` 已更新为当前入口说明，但详细交接仍以本文件为准。
- 云端信息、SSH、systemd 服务见 `README_CLOUD.md`。

## 近期维护进度

### 2026-06-07

- Git 整理从旧图库分支 `update-image-library-2026-03-23-162430` 切出维护分支 `maintenance-2026-06-07`，避免继续把非图库功能塞在旧分支名下。
- 已把明显运行态/临时文件加入 `.gitignore` 并推送到旧分支：`.tmp/`、`.codex`、`qrcode.png`、`resource/recent_errors.json`、`resource/chat_token_usage.jsonl*`、chat 记忆缓存等。
- 本轮整理前已跑敏感词扫描，命中均为变量名或示例占位，没有发现真实 key/token；`.env` 不在提交范围。
- 本轮整理前已跑 `python3 -m py_compile` 覆盖 `src/` 与 `tools/` 下 Python 文件，以及 `bot.py`，语法检查通过。
- 维护分支的提交建议分组：
  - 文档/工作台/云端同步工具。
  - chat agent、token usage、provider 配置与群聊记忆。
  - photo/vndb/birthday/KeyProphecy/logview/error history/角色数据。
- 实际已推送提交：
  - `97a58d6 Add Yumemi maintenance docs and tools`
  - `e648f94 Add Yumemi chat agent support`
  - `799b916 Update Yumemi bot plugins`
- 当前 `maintenance-2026-06-07` 工作区已整理为干净状态；如需合回主线，优先从该分支开 PR 或手工 merge。

### 2026-05-22

- 本机检查：`yumemi-bot` / `yumemi-napcat` systemd 服务为 inactive；已删除本机用户 crontab，旧的每天 04:00 自动重启任务不再存在。
- 云端检查：`yumemi-xvfb`、`yumemi-vnc`、`yumemi-napcat`、`yumemi-bot` 均为 active；云端用户和 root crontab 均无自动重启任务，也没有相关 timer。
- 已清理旧 04:00 重启脚本：本地和云端项目中的 `tools/qq_restart_scheduler.sh`、`tools/restart_qq_napcat.sh` 已移除；`logview` 不再把对应 `/tmp` 日志当作 bot 日志回退来源。
- `vndb` 角色查询仍优先本地资料，但附带图片从固定第一张改为本地图库随机图。
- `KeyProphecy` 已拆分：`#占卜` / `#今日运势` 走普通占卜，返回当天运势、随机老婆、宜忌和 lucky thing；`#抢` / `#抢老婆 角色名` 用于抢指定老婆。非管理员内部按“今日运势值 / 500”判定，成功后 4 小时内不会再次成功；成功时整体格式和普通占卜一致，只把随机老婆替换为指定老婆；失败、冷却命中、未指定/未识别目标时先回复“不给你抢”，再退回普通随机老婆占卜结果；管理员仍直接抢指定老婆成功但不播报特权。
- `KeyProphecy` 代码已整理：普通占卜和抢老婆共用 `build_prophecy_message()` / `build_prophecy_body()` 输出，抢老婆只负责决定是否传入指定角色；发送异常处理集中在 `finish_with_prophecy_message()`，后续维护时优先保持这个边界。
- `photo` 已整理主流程：请求解析集中到 `resolve_photo_selection()`，发送集中到 `send_photo_selection()`；合并转发失败会记录错误并尝试普通图片 fallback，QQ/平台拒发或网络/API 失败会提示“这次不扣额度”。限额只在发送成功或 NapCat 超时但大概率已发送成功后扣除；解析、选图、发送失败都不扣额度。
- 已运行 `.venv/bin/python -m py_compile src/plugins/vndb/__init__.py src/plugins/KeyProphecy/__init__.py src/plugins/KeyProphecy/prophecy.py src/plugins/photo/__init__.py src/plugins/logview/__init__.py src/plugins/help/__init__.py`，语法检查通过；也用虚拟环境导入 `KeyProphecy` 构造过普通占卜、抢成功、抢失败三条消息，并导入 `photo` 验证过角色、数量、随机图库和限额解析。

### 2026-05-23

- `resource/character_data.json` 已按 VNDB `v47937` 更新 `anemoi` 角色：原 5 位女主补生日，新增配角/相关角色条目；VNDB 没有生日的数据按用户补充填入，未提供生日的新增角色保留无生日。

### 2026-05-24

- 继续 `E:\Gal\Key\planetarian` 下两个游戏的临时解包/文本提取。Snow Globe 侧已通过 SiglusEngine/DBS 路线产出文本，临时结果在 `.tmp/planetarian_text_extract/raw/snowglobe_dbs/`，主脚本文件是 `text.dbs.txt`，另有 `system.dbs.txt`、`settitle.dbs.txt`、`cgmode.dbs.txt`。
- 旧版 `Planetarian～ちいさなほしのゆめ～` 直接从 `kineticdata.pak`、crass、GARbro、rldev 路线暂未得到可读脚本；memory dump 中已确认资源表记录，`SEEN.TXT` 在包内偏移 `0x029ad822`、大小 `0x28b6`，但对应数据仍是压缩/加密态。
- 旧版可用文本路线改为读取 `Kinetic.exe` 内嵌 `.seen` 段：文件偏移 `0x1c1000`、大小 `0x9b960`。已新增/使用 `.tmp/planetarian_text_extract/tools/extract_kinetic_seen_text.py`，输出在 `.tmp/planetarian_text_extract/old_kinetic/`。
- 旧版当前输出：`seen_section.bin` 为原始 `.seen` 段，`seen_dialogue_lines.txt` 抽到 1015 条疑似对白/旁白，`seen_cp932_string_candidates.txt` 抽到 1423 条 CP932 字符串候选。继续整理时优先处理 `seen_dialogue_lines.txt`；字符串候选包含引擎/debug/乱码噪声，只适合补漏。
- 辅助分析脚本 `.tmp/planetarian_text_extract/tools/minidump_extract.py` 可继续解析 minidump memory list 和资源表；除非后续必须还原资源包，不建议优先重走 pak 解密路线。
- 两个 planetarian 游戏的解包历史、失败路线和复现命令已单独整理到 `.tmp/planetarian_text_extract/EXTRACTION_HISTORY.md`。

## 先读清单

新对话接手时建议依次阅读：

1. `README_HANDOFF.md`
2. `README_CLOUD.md`
3. `git status --short`
4. `src/utils/character_data.py`
5. `src/plugins/photo/__init__.py`
6. `src/plugins/vndb/__init__.py`
7. `src/plugins/birthday/__init__.py`
8. `src/plugins/KeyProphecy/__init__.py`
9. `src/plugins/logview/__init__.py`
10. `tools/yumemi_imagetools.sh`

## 核心数据与路径

- 统一角色数据源：`resource/character_data.json`
- `anemoi` 角色资料更新来源：VNDB `v47937` 的 character API；生日来自用户补充（VNDB 未提供生日）。
- 作品别名表：`resource/game_aliases.json`
- 角色匹配共享逻辑：`src/utils/character_data.py`
- 资源路径工具：`src/utils/paths.py`
- 本地图库目录：`resource/images/<标准角色名>/`
- 最近错误记录：`resource/recent_errors.json`
- 图库检查报告：`resource/image_folder_check_report.txt`
- 图库计数表：`resource/image_folder_image_count.csv`

角色匹配、别名解析、从整句文本中抽取角色、本地图片索引等逻辑尽量集中在 `src/utils/character_data.py`，不要在各插件里再写一套。

## 主要插件现状

### `photo`

- 本地图库优先。
- 支持角色、作品、随机图库目标。
- 作品别名来自 `resource/game_aliases.json`。
- 图片目录按标准角色名组织。
- 普通用户每小时限额在内存中记录；不要在发送前扣额度。当前只有 `send_photo_selection()` 返回成功后才调用 `consume_photo_quota()`。
- 合并转发发送失败会记录 `send_mode=forward`，随后尝试普通图片 fallback；fallback 失败会再记录 `send_mode=plain_fallback`。QQ/平台拒发、网络/API 失败、解析/选图异常都应保留“不扣额度”的行为。

### `vndb`

- 本地角色数据优先。
- VNDB 只作为缺失字段或本地无结果时的补充。
- 如果只用了本地数据，不应显示“数据来自 VNDB”。
- 查询结果附图从本地图库随机抽取，不再固定使用第一张。

### `birthday`

- 生日查询已经尽量接入统一角色数据。
- 输出形式可参考其合并转发卡片式实现。

### `KeyProphecy`

- 占卜结果按天固定。
- `#占卜` / `#今日运势` 返回普通随机老婆占卜结果。
- `#抢` / `#抢老婆 角色名` 单独尝试抢指定老婆；成功时输出仍遵循普通占卜格式，只替换老婆信息。非管理员内部成功率为当天运势值 / 500，成功后 4 小时内不会再次成功；失败、冷却命中、未指定/未识别目标时先回“不给你抢”，再退回普通随机老婆占卜结果，不播报概率、判定值或冷却。管理员直接抢指定老婆成功，也不播报管理员特权。
- 非管理员抢老婆成功记录保存在 `resource/rob_wife_success.json`，属于运行时状态，已加入 `.gitignore`。
- 普通占卜和抢老婆共用 `build_prophecy_message()` / `build_prophecy_body()` 输出；抢老婆成功只传入指定 `CharacterProfile`，失败则设置 `rob_denied=True` 后回普通随机老婆占卜。图片和角色匹配尽量复用共享工具。

### `logview`

- 日志查看插件在最近维护中做过卡片/合并转发输出调整。
- 已接入最近错误记录思路，错误记录文件是 `resource/recent_errors.json`。
- 继续改日志时要同时考虑 bot 侧异常、NapCat/QQ 发送失败、网络失败、图片问题。

## 图库维护工具

当前推荐入口：

```bash
yumemi_imagetools
```

源文件：

- `tools/yumemi_imagetools.sh`
- `tools/image_update_workflow.sh`
- `tools/import_temp_images.py`
- `tools/normalize_image_names.py`
- `tools/check_image_folders.py`

快捷入口：

- `/home/lwjzlw/yumemi_imagetools`
- `/home/lwjzlw/bin/yumemi_imagetools`

常用顺序：

```text
1 sync-temp   同步 Windows temp 到 WSL temp
2 import      导入 temp 图片
3 organize    整理图库命名
4 dedupe      删除重复图片
Q check       检查图库
C cloud       同步到云端
G git-add     暂存图库改动
```

重要行为：

- `sync-temp` 只从 Windows `D:\Bot\Yumemi-Bot\resource\temp` 同步到 WSL `resource/temp`，不进正式图库。
- `import` 才把 WSL temp 中能按父文件夹名或文件名匹配到角色目录的图片移动到 `resource/images/<角色名>/`。
- `organize` 只整理命名，默认不删除重复图。
- `organize` 补编号空洞时采用“用最后一张图填前面空位”的策略，避免大批整体前移。
- `dedupe` 按 SHA256 删除二进制完全相同的重复图片，删除前备份 duplicate/original 到 `resource/temp/_dedupe_backup_时间戳/`。
- `cloud` 和 `git-add` 只按 `.git/yumemi_image_update_manifest.txt` 里的角色目录做增量处理。

最近曾创建过校对区：

```text
resource/temp/_organize_review_20260422/
```

里面保存了某次 organize 中 Git 显示被删的旧文件，以及 duplicate/original 两侧文件。用户已校对其中重复项确实为重复图。

## 云端与 SSH

云端详情见 `README_CLOUD.md`。关键点：

- 云端 SSH alias：`ssh yumemi-aliyun`
- 云端项目目录：`/home/yumemi/Yumemi-Bot`
- 云端 NapCat 目录：`/home/yumemi/NapCat`
- 项目根工作台：`/home/ubuntu/Yumemi-Bot/manage_bot`
- PATH 工作台入口：`yumemi`
- 本机管理入口：`/home/lwjzlw/manage_bot.sh`
- 云端管理入口：`/home/yumemi/manage_bot.sh`
- 云端 `yumemi` 用户已配置免密码 sudo。

SSH 密钥状态：

- Windows 当前 SSH config 使用 `C:\Users\lwjzl\.ssh\yumemi_aliyun`。
- WSL 当前使用 `/home/lwjzlw/.ssh/yumemi_aliyun`。
- 这两份当前 key 指纹一致。
- Windows 桌面上的 `yumemi-aliyun` / `yumemi-aliyun.pub` 与当前 `.ssh/yumemi_aliyun.pub` 指纹不一致，不是简单重复副本；删除前需要确认它不是阿里云控制台中仍登记的旧密钥。

## 云端服务

systemd 服务：

- `yumemi-xvfb`
- `yumemi-vnc`
- `yumemi-napcat`
- `yumemi-bot`

本机常用：

```bash
/home/lwjzlw/manage_bot.sh cloud-status
/home/lwjzlw/manage_bot.sh cloud-restart
/home/lwjzlw/manage_bot.sh cloud-bot
/home/lwjzlw/manage_bot.sh cloud-napcat
/home/lwjzlw/manage_bot.sh chat-status
/home/lwjzlw/manage_bot.sh cloud-chat-status
/home/lwjzlw/manage_bot.sh sync-code
```

云端常用：

```bash
ssh yumemi-aliyun
bash ~/manage_bot.sh
```

代码同步：

```bash
tools/deploy_cloud.sh code
tools/deploy_cloud.sh requirements
tools/deploy_cloud.sh restart
```

`tools/deploy_cloud.sh code` 会刷新云端 `~/manage_bot.sh` 和 `~/bin/yumemi` 到项目根工作台；根入口在云端会自动进入 cloud 菜单。

图库同步优先用 `yumemi_imagetools` 的 `cloud`，因为它按 manifest 增量同步。

## 当前风险点

- 工作区有较多未提交改动和未跟踪文件，不能随意清理。
- `tools/` 目前包含大量维护脚本，部分可能仍未被 Git 跟踪。
- 旧 04:00 重启任务已清理；不要重新加入 `qq_restart_scheduler.sh` / `restart_qq_napcat.sh` 或类似 crontab，除非用户明确要求恢复。
- 图库刚经过导入、整理、去重逻辑调整；继续操作前先看 `git status --short` 和 manifest。
- `resource/temp/` 可能包含待导入图片、校对区和 dedupe 备份，不要直接删除。
- QQ/NapCat 富媒体发送偶发失败，日志和错误记录仍可能需要继续加强。
- Windows 桌面旧 SSH key 不应直接当重复文件删除。

## 给新对话的开场模板

```text
这是一个 NoneBot2 + OneBot V11 + NapCat 的 QQ 群聊机器人项目，仓库名是 Yumemi-Bot。

先不要按旧 README 判断项目现状，请先阅读：
1. README_HANDOFF.md
2. README_CLOUD.md
3. git status --short
4. src/utils/character_data.py
5. src/plugins/photo/__init__.py
6. src/plugins/vndb/__init__.py
7. src/plugins/birthday/__init__.py
8. src/plugins/KeyProphecy/__init__.py
9. src/plugins/logview/__init__.py
10. tools/yumemi_imagetools.sh

已知背景：
- 统一角色数据源是 resource/character_data.json
- 作品别名表是 resource/game_aliases.json
- 角色匹配逻辑尽量统一收敛在 src/utils/character_data.py
- 本地图库优先，图片目录按标准角色名组织
- 当前主运行环境在阿里云，云端信息看 README_CLOUD.md
- 图库维护入口是 yumemi_imagetools
- 本机管理入口是 /home/lwjzlw/manage_bot.sh，云端管理入口是 /home/yumemi/manage_bot.sh
- 当前工作区不是干净状态，不能随便回退已有未提交改动

先给我一个“当前状态简述 + 你准备先看的文件/风险点”，然后再继续处理我的新需求。
```
