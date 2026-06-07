#!/usr/bin/env bash
set -euo pipefail

KEY_PATH="${KEY_PATH:-/home/lwjzlw/.ssh/yumemi_aliyun}"
REMOTE_USER="${REMOTE_USER:-yumemi}"
REMOTE_HOST="${REMOTE_HOST:-47.100.170.173}"
REMOTE="${REMOTE_USER}@${REMOTE_HOST}"
REMOTE_DIR="${REMOTE_DIR:-/home/yumemi/Yumemi-Bot}"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
usage:
  tools/deploy_cloud.sh [code|images|all|requirements|restart|status]

commands:
  code          同步代码、配置和小资源，默认不传 resource/images
  images        只同步 resource/images
  all           同步整个项目，包含 resource/images
  requirements  在云端根据 requirements.txt 安装/更新 Python 依赖
  restart       重启云端 bot 服务
  status        查看云端服务状态

note:
  code/all 会刷新云端 ~/manage_bot.sh 和 ~/bin/yumemi 到项目根工作台

env:
  KEY_PATH      SSH key path, default /home/lwjzlw/.ssh/yumemi_aliyun
  REMOTE_HOST   cloud host, default 47.100.170.173
  REMOTE_USER   cloud user, default yumemi
  REMOTE_DIR    cloud repo dir, default /home/yumemi/Yumemi-Bot
EOF
}

rsync_common() {
  rsync -az --delete --info=progress2 \
    --exclude ".venv/" \
    --exclude "__pycache__/" \
    --exclude ".git/" \
    --exclude ".codex/" \
    --exclude "*.pyc" \
    -e "ssh -i $KEY_PATH" \
    "$@"
}

deploy_code() {
  rsync_common \
    --exclude "resource/images/" \
    "$LOCAL_DIR/" "$REMOTE:$REMOTE_DIR/"
}

deploy_images() {
  rsync -az --info=progress2 \
    -e "ssh -i $KEY_PATH" \
    "$LOCAL_DIR/resource/images/" "$REMOTE:$REMOTE_DIR/resource/images/"
}

deploy_all() {
  rsync_common "$LOCAL_DIR/" "$REMOTE:$REMOTE_DIR/"
}

install_requirements() {
  ssh -i "$KEY_PATH" "$REMOTE" \
    "cd '$REMOTE_DIR' && .venv/bin/pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com --timeout 120"
}

restart_bot() {
  ssh -i "$KEY_PATH" "$REMOTE" "sudo systemctl restart yumemi-bot && sudo systemctl --no-pager --lines=20 status yumemi-bot"
}

status_cloud() {
  ssh -i "$KEY_PATH" "$REMOTE" "sudo systemctl --no-pager --lines=8 status yumemi-xvfb yumemi-vnc yumemi-napcat yumemi-bot || true"
}

install_manage_launcher() {
  ssh -i "$KEY_PATH" "$REMOTE" "ln -sfn '$REMOTE_DIR/manage_bot' /home/yumemi/manage_bot.sh; mkdir -p /home/yumemi/bin; ln -sfn '$REMOTE_DIR/yumemi' /home/yumemi/bin/yumemi"
}

case "${1:-code}" in
  code) deploy_code; install_manage_launcher ;;
  images) deploy_images ;;
  all) deploy_all; install_manage_launcher ;;
  requirements) install_requirements ;;
  restart) restart_bot ;;
  status) status_cloud ;;
  help|-h|--help) usage ;;
  *)
    echo "unknown command: $1"
    echo
    usage
    exit 1
    ;;
esac
