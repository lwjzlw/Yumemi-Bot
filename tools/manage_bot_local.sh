#!/usr/bin/env bash
set -euo pipefail

BOT_SERVICE="yumemi-bot"
NAPCAT_SERVICE="yumemi-napcat"

SOURCE="${BASH_SOURCE[0]}"
while [[ -L "$SOURCE" ]]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  case "$SOURCE" in
    /*) ;;
    *) SOURCE="$DIR/$SOURCE" ;;
  esac
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
if [[ -f "$SCRIPT_DIR/../bot.py" ]]; then
  PROJECT_ROOT="$(cd -P "$SCRIPT_DIR/.." && pwd)"
elif [[ -f "$SCRIPT_DIR/bot.py" ]]; then
  PROJECT_ROOT="$SCRIPT_DIR"
else
  PROJECT_ROOT="${YUMEMI_BOT_HOME:-/home/ubuntu/Yumemi-Bot}"
fi

LOCAL_ENV="${LOCAL_ENV:-$PROJECT_ROOT/.env}"
PYTHON_BIN="${PYTHON_BIN:-$PROJECT_ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

CLOUD_HOST="${CLOUD_HOST:-47.100.170.173}"
CLOUD_ROOT="${CLOUD_ROOT:-root@${CLOUD_HOST}}"
CLOUD_USER="${CLOUD_USER:-yumemi@${CLOUD_HOST}}"
CLOUD_PROJECT_ROOT="${CLOUD_PROJECT_ROOT:-/home/yumemi/Yumemi-Bot}"
CLOUD_ENV="${CLOUD_ENV:-$CLOUD_PROJECT_ROOT/.env}"
CLOUD_KEY="${CLOUD_KEY:-/home/lwjzlw/.ssh/yumemi_aliyun}"
CLOUD_QRCODE_REMOTE="/home/yumemi/NapCat/napcat/cache/qrcode.png"
CLOUD_QRCODE_LOCAL="$PROJECT_ROOT/qrcode.png"

require_systemd() {
  if [[ "$(ps -p 1 -o comm= 2>/dev/null | tr -d ' ')" != "systemd" ]]; then
    echo "当前 WSL 还没有切到 systemd 模式。"
    echo "请先在 Windows 里执行一次: wsl --shutdown"
    echo "然后重新打开 Ubuntu 再使用 manage_bot.sh。"
    return 1
  fi
}

service_state() {
  local service_name="$1"
  local state
  state="$(sudo systemctl is-active "$service_name" 2>/dev/null || true)"
  if [[ -z "$state" ]]; then
    echo "unknown"
  else
    echo "$state"
  fi
}

filter_processes() {
  local pattern="$1"
  pgrep -af "$pattern" || return 1
}

cleanup_legacy_processes() {
  tmux kill-session -t yumemi2-bot 2>/dev/null || true
  tmux kill-session -t yumemi2-napcat 2>/dev/null || true
  pkill -f "python bot.py" 2>/dev/null || true
  pkill -f "/opt/QQ/qq" 2>/dev/null || true
  pkill -f "libnapcat_launcher.so qq" 2>/dev/null || true
}

start_all() {
  require_systemd || return 1
  cleanup_legacy_processes
  sudo systemctl start "$NAPCAT_SERVICE"
  sleep 8
  sudo systemctl start "$BOT_SERVICE"
  echo "started local $NAPCAT_SERVICE and $BOT_SERVICE"
}

stop_all() {
  require_systemd || return 1
  sudo systemctl stop "$BOT_SERVICE" "$NAPCAT_SERVICE" || true
  cleanup_legacy_processes
  echo "stopped local $BOT_SERVICE and $NAPCAT_SERVICE"
}

restart_all() {
  require_systemd || return 1
  stop_all
  sleep 3
  start_all
}

restart_bot_service() {
  require_systemd || return 1
  sudo systemctl restart "$BOT_SERVICE"
  sudo systemctl --no-pager --lines=12 status "$BOT_SERVICE" || true
}

local_chat_summary() {
  local enabled whitelist
  enabled="$("$PYTHON_BIN" "$PROJECT_ROOT/tools/manage_bot_env.py" "$LOCAL_ENV" get chat_enabled false 2>/dev/null || echo false)"
  whitelist="$("$PYTHON_BIN" "$PROJECT_ROOT/tools/manage_bot_env.py" "$LOCAL_ENV" get chat_group_whitelist "[]" 2>/dev/null || echo "[]")"
  echo "  chat_enabled: $enabled"
  echo "  chat_group_whitelist: ${whitelist:-[]}"
}

status_all() {
  require_systemd || return 1
  echo "local service summary:"
  echo "  $BOT_SERVICE: $(service_state "$BOT_SERVICE")"
  echo "  $NAPCAT_SERVICE: $(service_state "$NAPCAT_SERVICE")"
  local_chat_summary
  echo
  sudo systemctl --no-pager --lines=0 status "$BOT_SERVICE" "$NAPCAT_SERVICE" || true
  echo
  echo "local bot processes:"
  filter_processes "$PROJECT_ROOT/.venv/bin/python $PROJECT_ROOT/bot.py|python bot.py" || echo "  no bot process"
  echo
  echo "local napcat/qq processes:"
  filter_processes "/opt/QQ/qq|libnapcat_launcher.so qq" || echo "  no napcat process"
}

chat_status_local() {
  "$PYTHON_BIN" "$PROJECT_ROOT/tools/check_chat_config.py" "$LOCAL_ENV"
}

chat_set_bool_local() {
  local key="$1"
  local desired="$2"
  "$PYTHON_BIN" "$PROJECT_ROOT/tools/manage_bot_env.py" "$LOCAL_ENV" set-bool "$key" "$desired"
  echo
  chat_status_local
  echo
  echo "$key 修改后需要重启 bot 才会生效："
  echo "  $0 restart-bot"
}

chat_set_local() {
  chat_set_bool_local chat_enabled "$1"
}

chat_agent_set_local() {
  chat_set_bool_local chat_agent_enabled "$1"
}

chat_agent_network_set_local() {
  chat_set_bool_local chat_agent_allow_network "$1"
}

chat_toggle_local() {
  local current desired
  current="$("$PYTHON_BIN" "$PROJECT_ROOT/tools/manage_bot_env.py" "$LOCAL_ENV" get chat_enabled false)"
  case "${current,,}" in
    1|true|yes|on) desired="false" ;;
    *) desired="true" ;;
  esac
  chat_set_local "$desired"
}

chat_agent_toggle_local() {
  local current desired
  current="$("$PYTHON_BIN" "$PROJECT_ROOT/tools/manage_bot_env.py" "$LOCAL_ENV" get chat_agent_enabled false)"
  case "${current,,}" in
    1|true|yes|on) desired="false" ;;
    *) desired="true" ;;
  esac
  chat_agent_set_local "$desired"
}

chat_agent_network_toggle_local() {
  local current desired
  current="$("$PYTHON_BIN" "$PROJECT_ROOT/tools/manage_bot_env.py" "$LOCAL_ENV" get chat_agent_allow_network false)"
  case "${current,,}" in
    1|true|yes|on) desired="false" ;;
    *) desired="true" ;;
  esac
  chat_agent_network_set_local "$desired"
}

show_logs() {
  local service_name="$1"
  require_systemd || return 1
  sudo journalctl -u "$service_name" -n 120 --no-pager
}

follow_logs() {
  local service_name="$1"
  require_systemd || return 1
  exec sudo journalctl -u "$service_name" -f
}

cloud_ssh_root() {
  ssh -i "$CLOUD_KEY" "$CLOUD_ROOT" "$@"
}

cloud_ssh_user() {
  ssh -i "$CLOUD_KEY" "$CLOUD_USER" "$@"
}

cloud_restart_bot() {
  cloud_ssh_root "systemctl restart yumemi-bot; systemctl --no-pager --lines=12 status yumemi-bot || true"
}

cloud_start() {
  cloud_ssh_root "systemctl start yumemi-xvfb; systemctl start yumemi-napcat; sleep 8; systemctl start yumemi-bot; systemctl --no-pager --lines=8 status yumemi-napcat yumemi-bot"
}

cloud_stop() {
  cloud_ssh_root "systemctl stop yumemi-bot yumemi-napcat || true; systemctl --no-pager --lines=8 status yumemi-napcat yumemi-bot || true"
}

cloud_restart() {
  cloud_ssh_root "systemctl stop yumemi-bot yumemi-napcat || true; sleep 3; systemctl start yumemi-xvfb yumemi-napcat; sleep 8; systemctl start yumemi-bot; systemctl --no-pager --lines=8 status yumemi-napcat yumemi-bot"
}

cloud_status() {
  cloud_ssh_root "systemctl is-active yumemi-xvfb yumemi-vnc yumemi-napcat yumemi-bot || true; echo; systemctl --no-pager --lines=10 status yumemi-xvfb yumemi-vnc yumemi-napcat yumemi-bot || true"
}

cloud_chat_status() {
  cloud_ssh_user "cd '$CLOUD_PROJECT_ROOT' && python3 tools/check_chat_config.py '$CLOUD_ENV'"
}

cloud_chat_set_bool() {
  local key="$1"
  local desired="$2"
  cloud_ssh_user "cd '$CLOUD_PROJECT_ROOT' && python3 tools/manage_bot_env.py '$CLOUD_ENV' set-bool '$key' '$desired' && python3 tools/check_chat_config.py '$CLOUD_ENV'"
  echo
  echo "cloud $key 修改后需要重启 bot 才会生效："
  echo "  $0 cloud-restart-bot"
}

cloud_chat_set() {
  cloud_chat_set_bool chat_enabled "$1"
}

cloud_chat_agent_set() {
  cloud_chat_set_bool chat_agent_enabled "$1"
}

cloud_chat_agent_network_set() {
  cloud_chat_set_bool chat_agent_allow_network "$1"
}

cloud_chat_toggle() {
  local current desired
  current="$(cloud_ssh_user "cd '$CLOUD_PROJECT_ROOT' && python3 tools/manage_bot_env.py '$CLOUD_ENV' get chat_enabled false")"
  case "${current,,}" in
    1|true|yes|on) desired="false" ;;
    *) desired="true" ;;
  esac
  cloud_chat_set "$desired"
}

cloud_chat_agent_toggle() {
  local current desired
  current="$(cloud_ssh_user "cd '$CLOUD_PROJECT_ROOT' && python3 tools/manage_bot_env.py '$CLOUD_ENV' get chat_agent_enabled false")"
  case "${current,,}" in
    1|true|yes|on) desired="false" ;;
    *) desired="true" ;;
  esac
  cloud_chat_agent_set "$desired"
}

cloud_chat_agent_network_toggle() {
  local current desired
  current="$(cloud_ssh_user "cd '$CLOUD_PROJECT_ROOT' && python3 tools/manage_bot_env.py '$CLOUD_ENV' get chat_agent_allow_network false")"
  case "${current,,}" in
    1|true|yes|on) desired="false" ;;
    *) desired="true" ;;
  esac
  cloud_chat_agent_network_set "$desired"
}

cloud_show_logs() {
  local service_name="$1"
  cloud_ssh_root "journalctl -u '$service_name' -n 120 --no-pager"
}

cloud_follow_logs() {
  local service_name="$1"
  exec ssh -i "$CLOUD_KEY" "$CLOUD_ROOT" "journalctl -u '$service_name' -f"
}

cloud_qrcode() {
  cloud_ssh_root "systemctl restart yumemi-napcat; sleep 6; journalctl -u yumemi-napcat --no-pager -n 80 | grep -E '二维码解码URL|二维码已保存' | tail -4 || true"
  rsync -az -e "ssh -i $CLOUD_KEY" "$CLOUD_USER:$CLOUD_QRCODE_REMOTE" "$CLOUD_QRCODE_LOCAL" || true
  echo
  echo "local qrcode: $CLOUD_QRCODE_LOCAL"
}

cloud_vnc() {
  local local_port="${LOCAL_PORT:-5900}"
  cloud_ssh_root "systemctl start yumemi-xvfb yumemi-vnc; systemctl is-active --quiet yumemi-vnc"
  echo "VNC is available at localhost:${local_port} while this tunnel stays open."
  echo "Open MobaXterm VNC to localhost:${local_port}."
  exec ssh -i "$CLOUD_KEY" -N -L "${local_port}:127.0.0.1:5900" "$CLOUD_ROOT"
}

cloud_vnc_start() {
  cloud_ssh_root "systemctl start yumemi-xvfb yumemi-vnc; systemctl --no-pager --lines=8 status yumemi-vnc || true"
}

cloud_vnc_stop() {
  cloud_ssh_root "systemctl stop yumemi-vnc || true; systemctl --no-pager --lines=8 status yumemi-vnc || true"
}

cloud_manage() {
  exec ssh -t -i "$CLOUD_KEY" "$CLOUD_USER" "if [ -x '$CLOUD_PROJECT_ROOT/manage_bot' ]; then cd '$CLOUD_PROJECT_ROOT' && YUMEMI_MANAGE_MODE=cloud ./manage_bot; else /home/yumemi/manage_bot.sh; fi"
}

deploy_cloud() {
  "$PROJECT_ROOT/tools/deploy_cloud.sh" "$1"
}

image_workbench() {
  exec "$PROJECT_ROOT/tools/yumemi_imagetools.sh"
}

print_usage() {
  cat <<'EOF'
Yumemi 工作台
  [1/S] service   本机 bot / napcat 服务
  [2/A] chat      本机 chat 开关和配置
  [3/C] cloud     云端服务、日志、二维码、VNC
  [4/Y] sync      同步部署到云端
  [5/T] tools     图库和维护工具
  [H/?] help      显示这个菜单
  [X/E] exit      退出

直达命令仍可用；需要完整列表时看 README.md / README_CHAT.md。
EOF
}

print_service_usage() {
  cat <<'EOF'
本机服务
  [1/S] start          启动本机 napcat 和 bot
  [2/T] stop           停止本机 napcat 和 bot
  [3/R] restart        重启本机 napcat 和 bot
  [4/U] status         查看本机服务状态
  [5/B] attach-bot     实时跟随本机 bot 日志
  [6/N] attach-napcat  实时跟随本机 napcat 日志
  [7/P] peek-bot       查看本机 bot 最近日志
  [8/Q] peek-napcat    查看本机 napcat 最近日志
  [9/O] restart-bot    只重启本机 bot 服务
  [X/E] back           返回
EOF
}

print_chat_usage() {
  cat <<'EOF'
Chat
  [1/S] status   查看本机 chat 配置摘要
  [2/O] on       打开本机 chat_enabled
  [3/F] off      关闭本机 chat_enabled
  [4/T] toggle   切换本机 chat_enabled
  [5/R] restart  只重启本机 bot 服务
  [6/A] agent-on 打开本机 chat_agent_enabled
  [7/D] agent-off 关闭本机 chat_agent_enabled
  [8/N] network-on 打开本机 chat_agent_allow_network
  [9/W] network-off 关闭本机 chat_agent_allow_network
  [X/E] back     返回
EOF
}

print_cloud_usage() {
  cat <<'EOF'
云端服务
  [1/S] status       查看云端服务状态
  [2/A] start        启动云端 napcat 和 bot
  [3/T] stop         停止云端 napcat 和 bot
  [4/R] restart      重启云端 napcat 和 bot
  [5/O] restart-bot  只重启云端 bot 服务
  [6/B] bot-log      实时跟随云端 bot 日志
  [7/N] napcat-log   实时跟随云端 napcat 日志
  [8/P] qrcode       刷新并拉取云端登录二维码
  [9/V] vnc          打开云端 VNC SSH 隧道
  [I] vnc-start      只启动云端 VNC 服务
  [Z] vnc-stop       停止云端 VNC 服务
  [M] manage         SSH 打开云端 manage 菜单
  [C] chat           云端 chat 二级菜单
  [X/E] back         返回
EOF
}

print_cloud_chat_usage() {
  cat <<'EOF'
云端 Chat
  [1/S] status       查看云端 chat 配置摘要
  [2/O] on           打开云端 chat_enabled
  [3/F] off          关闭云端 chat_enabled
  [4/T] toggle       切换云端 chat_enabled
  [5/R] restart-bot  只重启云端 bot 服务
  [6/A] agent-on     打开云端 chat_agent_enabled
  [7/D] agent-off    关闭云端 chat_agent_enabled
  [8/N] network-on   打开云端 chat_agent_allow_network
  [9/W] network-off  关闭云端 chat_agent_allow_network
  [X/E] back         返回
EOF
}

print_sync_usage() {
  cat <<'EOF'
同步部署
  [1/C] code          同步代码、配置和小资源，不含 resource/images
  [2/I] images        只同步 resource/images
  [3/A] all           同步整个项目，包含 resource/images
  [4/P] requirements  在云端安装/更新依赖
  [5/R] restart       重启云端 bot 服务
  [6/S] status        查看云端服务状态
  [X/E] back          返回
EOF
}

print_tools_usage() {
  cat <<'EOF'
维护工具
  [1/I] images   打开图库维护工作台
  [2/Q] qrcode   刷新并拉取云端登录二维码
  [3/V] vnc      打开云端 VNC SSH 隧道
  [X/E] back     返回
EOF
}

run_action() {
  local action="${1:-}"
  shift || true
  case "$action" in
    service) service_menu ;;
    chat) if [[ -n "${1:-}" ]]; then run_action "chat-$1"; else chat_menu; fi ;;
    cloud) if [[ -n "${1:-}" ]]; then run_action "cloud-$1"; else cloud_menu; fi ;;
    sync) if [[ -n "${1:-}" ]]; then run_action "sync-$1"; else sync_menu; fi ;;
    tools) tools_menu ;;
    image-workbench|images-workbench) image_workbench ;;
    start) start_all ;;
    stop) stop_all ;;
    restart) restart_all ;;
    restart-bot) restart_bot_service ;;
    status) status_all ;;
    attach-bot|bot) follow_logs "$BOT_SERVICE" ;;
    attach-napcat|napcat) follow_logs "$NAPCAT_SERVICE" ;;
    logs-bot|peek|peek-bot) show_logs "$BOT_SERVICE" ;;
    logs-napcat|peek-napcat) show_logs "$NAPCAT_SERVICE" ;;
    chat-status) chat_status_local ;;
    chat-on) chat_set_local true ;;
    chat-off) chat_set_local false ;;
    chat-toggle) chat_toggle_local ;;
    chat-agent-on) chat_agent_set_local true ;;
    chat-agent-off) chat_agent_set_local false ;;
    chat-agent-toggle) chat_agent_toggle_local ;;
    chat-network-on|chat-agent-network-on) chat_agent_network_set_local true ;;
    chat-network-off|chat-agent-network-off) chat_agent_network_set_local false ;;
    chat-network-toggle|chat-agent-network-toggle) chat_agent_network_toggle_local ;;
    cloud-start) cloud_start ;;
    cloud-stop) cloud_stop ;;
    cloud-restart) cloud_restart ;;
    cloud-restart-bot) cloud_restart_bot ;;
    cloud-status) cloud_status ;;
    cloud-bot|cloud-attach-bot) cloud_follow_logs "yumemi-bot" ;;
    cloud-napcat|cloud-attach-napcat) cloud_follow_logs "yumemi-napcat" ;;
    cloud-logs-bot|cloud-peek-bot) cloud_show_logs "yumemi-bot" ;;
    cloud-logs-napcat|cloud-peek-napcat) cloud_show_logs "yumemi-napcat" ;;
    cloud-qrcode|cloud-qr) cloud_qrcode ;;
    cloud-vnc) cloud_vnc ;;
    cloud-vnc-start) cloud_vnc_start ;;
    cloud-vnc-stop) cloud_vnc_stop ;;
    cloud-manage) cloud_manage ;;
    cloud-chat-status) cloud_chat_status ;;
    cloud-chat-on) cloud_chat_set true ;;
    cloud-chat-off) cloud_chat_set false ;;
    cloud-chat-toggle) cloud_chat_toggle ;;
    cloud-chat-agent-on) cloud_chat_agent_set true ;;
    cloud-chat-agent-off) cloud_chat_agent_set false ;;
    cloud-chat-agent-toggle) cloud_chat_agent_toggle ;;
    cloud-chat-network-on|cloud-chat-agent-network-on) cloud_chat_agent_network_set true ;;
    cloud-chat-network-off|cloud-chat-agent-network-off) cloud_chat_agent_network_set false ;;
    cloud-chat-network-toggle|cloud-chat-agent-network-toggle) cloud_chat_agent_network_toggle ;;
    sync-code|deploy-code) deploy_cloud code ;;
    sync-images|deploy-images) deploy_cloud images ;;
    sync-all|deploy-all) deploy_cloud all ;;
    sync-requirements|deploy-requirements) deploy_cloud requirements ;;
    sync-restart|deploy-restart) deploy_cloud restart ;;
    sync-status|deploy-status) deploy_cloud status ;;
    help|"") print_usage ;;
    exit) return 0 ;;
    *)
      echo "unknown command: $1"
      echo
      print_usage
      exit 1
      ;;
  esac
}

service_menu() {
  while true; do
    print_service_usage
    echo
    read -r -p "select service action: " choice
    case "${choice^^}" in
      1|S) run_action start ;;
      2|T) run_action stop ;;
      3|R) run_action restart ;;
      4|U) run_action status ;;
      5|B) run_action attach-bot ;;
      6|N) run_action attach-napcat ;;
      7|P) run_action peek-bot ;;
      8|Q) run_action peek-napcat ;;
      9|O) run_action restart-bot ;;
      H|\?) print_usage ;;
      X|E|"")
        return 0
        ;;
      *) echo "unknown selection: $choice" ;;
    esac
    echo
    read -r -p "press Enter to return to menu..." _
    echo
  done
}

chat_menu() {
  while true; do
    print_chat_usage
    echo
    read -r -p "select chat action: " choice
    case "${choice^^}" in
      1|S) run_action chat-status ;;
      2|O) run_action chat-on ;;
      3|F) run_action chat-off ;;
      4|T) run_action chat-toggle ;;
      5|R) run_action restart-bot ;;
      6|A) run_action chat-agent-on ;;
      7|D) run_action chat-agent-off ;;
      8|N) run_action chat-agent-network-on ;;
      9|W) run_action chat-agent-network-off ;;
      H|\?) print_chat_usage ;;
      X|E|"") return 0 ;;
      *) echo "unknown selection: $choice" ;;
    esac
    echo
    read -r -p "press Enter to return to menu..." _
    echo
  done
}

cloud_chat_menu() {
  while true; do
    print_cloud_chat_usage
    echo
    read -r -p "select cloud chat action: " choice
    case "${choice^^}" in
      1|S) run_action cloud-chat-status ;;
      2|O) run_action cloud-chat-on ;;
      3|F) run_action cloud-chat-off ;;
      4|T) run_action cloud-chat-toggle ;;
      5|R) run_action cloud-restart-bot ;;
      6|A) run_action cloud-chat-agent-on ;;
      7|D) run_action cloud-chat-agent-off ;;
      8|N) run_action cloud-chat-agent-network-on ;;
      9|W) run_action cloud-chat-agent-network-off ;;
      H|\?) print_cloud_chat_usage ;;
      X|E|"") return 0 ;;
      *) echo "unknown selection: $choice" ;;
    esac
    echo
    read -r -p "press Enter to return to menu..." _
    echo
  done
}

cloud_menu() {
  while true; do
    print_cloud_usage
    echo
    read -r -p "select cloud action: " choice
    case "${choice^^}" in
      1|S) run_action cloud-status ;;
      2|A) run_action cloud-start ;;
      3|T) run_action cloud-stop ;;
      4|R) run_action cloud-restart ;;
      5|O) run_action cloud-restart-bot ;;
      6|B) run_action cloud-bot ;;
      7|N) run_action cloud-napcat ;;
      8|P) run_action cloud-qrcode ;;
      9|V) run_action cloud-vnc ;;
      I) run_action cloud-vnc-start ;;
      Z) run_action cloud-vnc-stop ;;
      M) run_action cloud-manage ;;
      C) cloud_chat_menu ;;
      H|\?) print_cloud_usage ;;
      X|E|"") return 0 ;;
      *) echo "unknown selection: $choice" ;;
    esac
    echo
    read -r -p "press Enter to return to menu..." _
    echo
  done
}

sync_menu() {
  while true; do
    print_sync_usage
    echo
    read -r -p "select sync action: " choice
    case "${choice^^}" in
      1|C) run_action sync-code ;;
      2|I) run_action sync-images ;;
      3|A) run_action sync-all ;;
      4|P) run_action sync-requirements ;;
      5|R) run_action sync-restart ;;
      6|S) run_action sync-status ;;
      H|\?) print_sync_usage ;;
      X|E|"") return 0 ;;
      *) echo "unknown selection: $choice" ;;
    esac
    echo
    read -r -p "press Enter to return to menu..." _
    echo
  done
}

tools_menu() {
  while true; do
    print_tools_usage
    echo
    read -r -p "select tool action: " choice
    case "${choice^^}" in
      1|I) run_action image-workbench ;;
      2|Q) run_action cloud-qrcode ;;
      3|V) run_action cloud-vnc ;;
      H|\?) print_tools_usage ;;
      X|E|"") return 0 ;;
      *) echo "unknown selection: $choice" ;;
    esac
    echo
    read -r -p "press Enter to return to menu..." _
    echo
  done
}

main_menu() {
  while true; do
    print_usage
    echo
    read -r -p "select Yumemi action: " choice
    case "${choice^^}" in
      1|S) service_menu ;;
      2|A) chat_menu ;;
      3|C) cloud_menu ;;
      4|Y) sync_menu ;;
      5|T) tools_menu ;;
      H|\?) print_usage ;;
      X|E|"")
        echo "bye."
        exit 0
        ;;
      *) echo "unknown selection: $choice" ;;
    esac
    echo
  done
}

if [[ $# -eq 0 ]]; then
  main_menu
else
  run_action "$@"
fi
