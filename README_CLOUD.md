# Yumemi-Bot Cloud Ops

云端实例：
- Host: `47.100.170.173`
- SSH alias: `ssh yumemi-aliyun`
- SSH key in WSL: `/home/lwjzlw/.ssh/yumemi_aliyun`
- SSH key in Windows: `C:\Users\lwjzl\.ssh\yumemi_aliyun`
- Cloud user: `yumemi`
- Project dir: `/home/yumemi/Yumemi-Bot`
- NapCat dir: `/home/yumemi/NapCat`

密钥备注：
- 当前 Windows SSH config 使用 `C:\Users\lwjzl\.ssh\yumemi_aliyun`。
- WSL 中 `/home/lwjzlw/.ssh/yumemi_aliyun` 与 Windows `.ssh` 中的当前 key 指纹一致。
- Windows 桌面上曾看到 `yumemi-aliyun` / `yumemi-aliyun.pub`，其公钥指纹与当前 `.ssh/yumemi_aliyun.pub` 不一致；不要当作简单重复文件直接删除，除非确认它不是阿里云控制台里仍保留的旧密钥。

常用服务：
- `yumemi-xvfb`: 云端虚拟显示 `:99`
- `yumemi-vnc`: 仅监听云端 `127.0.0.1:5900` 的 VNC
- `yumemi-napcat`: QQ + NapCat
- `yumemi-bot`: NoneBot

本机管理：
```bash
cd /home/ubuntu/Yumemi-Bot
yumemi
./manage_bot
bash /home/lwjzlw/manage_bot.sh
/home/lwjzlw/manage_bot.sh cloud-status
/home/lwjzlw/manage_bot.sh cloud-restart
/home/lwjzlw/manage_bot.sh cloud-bot
/home/lwjzlw/manage_bot.sh cloud-napcat
```

Chat 开关：
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

云端管理：
```bash
ssh yumemi-aliyun
bash ~/manage_bot.sh
```

本地更新后同步到云端：
```bash
tools/deploy_cloud.sh code
tools/deploy_cloud.sh requirements
tools/deploy_cloud.sh restart
```

`tools/deploy_cloud.sh code` 会同步代码并刷新云端 `~/manage_bot.sh` 到项目根工作台。
工作台里也可直接用 `yumemi sync-code`、`yumemi sync-images`、`yumemi sync-restart`。

如果更新了图库：
```bash
yumemi_imagetools
```

图库工作台常用顺序：
```text
1 sync-temp
2 import
3 organize
4 dedupe
Q check
C cloud
G git-add
```

说明：
- `sync-temp` 只把 Windows `D:\Bot\Yumemi-Bot\resource\temp` 同步到 WSL `resource/temp`。
- `import` 才会把 WSL temp 中可匹配角色的图片移动到正式图库。
- `organize` 只整理命名，不默认删除重复图。
- `dedupe` 按 SHA256 删除完全重复图片，删除前会备份到 `resource/temp/_dedupe_backup_时间戳/`。
- `cloud` 只同步 manifest 涉及的角色目录到云端。

如果需要 VNC：
```bash
tools/cloud_vnc_tunnel.sh
```
然后用 MobaXterm VNC 连接 `localhost:5900`。

给新对话的接手提示：
请先阅读 `README_HANDOFF.md` 和 `README_CLOUD.md`，然后查看 `git status --short`。不要按旧 `README.md` 判断项目现状。云端可通过 `ssh yumemi-aliyun` 进入，服务状态用 `/home/lwjzlw/manage_bot.sh cloud-status` 或云端 `bash ~/manage_bot.sh status` 查看。
