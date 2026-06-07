#!/usr/bin/env bash
set -euo pipefail

BOT_SERVICE="yumemi-bot"
NAPCAT_SERVICE="yumemi-napcat"
XVFB_SERVICE="yumemi-xvfb"
VNC_SERVICE="yumemi-vnc"

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
  PROJECT_ROOT="${YUMEMI_BOT_HOME:-/home/yumemi/Yumemi-Bot}"
fi

ENV_FILE="${ENV_FILE:-$PROJECT_ROOT/.env}"
PYTHON_BIN="${PYTHON_BIN:-$PROJECT_ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

QRCODE_PATH="/home/yumemi/NapCat/napcat/cache/qrcode.png"

service_state() {
  local service_name="$1"
  sudo systemctl is-active "$service_name" 2>/dev/null || true
}

start_all() {
  sudo systemctl start "$XVFB_SERVICE"
  sudo systemctl start "$NAPCAT_SERVICE"
  sleep 8
  sudo systemctl start "$BOT_SERVICE"
  echo "started cloud $NAPCAT_SERVICE and $BOT_SERVICE"
}

stop_all() {
  sudo systemctl stop "$BOT_SERVICE" "$NAPCAT_SERVICE" || true
  echo "stopped cloud $BOT_SERVICE and $NAPCAT_SERVICE"
}

restart_all() {
  stop_all
  sleep 3
  start_all
}

restart_bot_service() {
  sudo systemctl restart "$BOT_SERVICE"
  sudo systemctl --no-pager --lines=12 status "$BOT_SERVICE" || true
}

chat_summary() {
  local enabled whitelist
  enabled="$("$PYTHON_BIN" "$PROJECT_ROOT/tools/manage_bot_env.py" "$ENV_FILE" get chat_enabled false 2>/dev/null || echo false)"
  whitelist="$("$PYTHON_BIN" "$PROJECT_ROOT/tools/manage_bot_env.py" "$ENV_FILE" get chat_group_whitelist "[]" 2>/dev/null || echo "[]")"
  echo "  chat_enabled: $enabled"
  echo "  chat_group_whitelist: ${whitelist:-[]}"
}

status_all() {
  echo "service summary:"
  echo "  $XVFB_SERVICE: $(service_state "$XVFB_SERVICE")"
  echo "  $VNC_SERVICE: $(service_state "$VNC_SERVICE")"
  echo "  $NAPCAT_SERVICE: $(service_state "$NAPCAT_SERVICE")"
  echo "  $BOT_SERVICE: $(service_state "$BOT_SERVICE")"
  chat_summary
  echo
  sudo systemctl --no-pager --lines=8 status "$XVFB_SERVICE" "$VNC_SERVICE" "$NAPCAT_SERVICE" "$BOT_SERVICE" || true
}

show_logs() {
  local service_name="$1"
  sudo journalctl -u "$service_name" -n 120 --no-pager
}

follow_logs() {
  local service_name="$1"
  exec sudo journalctl -u "$service_name" -f
}

chat_status() {
  "$PYTHON_BIN" "$PROJECT_ROOT/tools/check_chat_config.py" "$ENV_FILE"
}

chat_set_bool() {
  local key="$1"
  local desired="$2"
  "$PYTHON_BIN" "$PROJECT_ROOT/tools/manage_bot_env.py" "$ENV_FILE" set-bool "$key" "$desired"
  echo
  chat_status
  echo
  echo "$key 修改后需要重启 bot 才会生效："
  echo "  $0 restart-bot"
}

chat_set() {
  chat_set_bool chat_enabled "$1"
}

chat_agent_set() {
  chat_set_bool chat_agent_enabled "$1"
}

chat_agent_network_set() {
  chat_set_bool chat_agent_allow_network "$1"
}

chat_toggle() {
  local current desired
  current="$("$PYTHON_BIN" "$PROJECT_ROOT/tools/manage_bot_env.py" "$ENV_FILE" get chat_enabled false)"
  case "${current,,}" in
    1|true|yes|on) desired="false" ;;
    *) desired="true" ;;
  esac
  chat_set "$desired"
}

chat_agent_toggle() {
  local current desired
  current="$("$PYTHON_BIN" "$PROJECT_ROOT/tools/manage_bot_env.py" "$ENV_FILE" get chat_agent_enabled false)"
  case "${current,,}" in
    1|true|yes|on) desired="false" ;;
    *) desired="true" ;;
  esac
  chat_agent_set "$desired"
}

chat_agent_network_toggle() {
  local current desired
  current="$("$PYTHON_BIN" "$PROJECT_ROOT/tools/manage_bot_env.py" "$ENV_FILE" get chat_agent_allow_network false)"
  case "${current,,}" in
    1|true|yes|on) desired="false" ;;
    *) desired="true" ;;
  esac
  chat_agent_network_set "$desired"
}

start_vnc() {
  sudo systemctl start "$XVFB_SERVICE" "$VNC_SERVICE"
  sudo systemctl --no-pager --lines=8 status "$VNC_SERVICE" || true
  echo
  echo "VNC listens only on cloud localhost:5900."
  echo "Use SSH tunnel from your PC before connecting a VNC client."
}

stop_vnc() {
  sudo systemctl stop "$VNC_SERVICE" || true
  echo "stopped $VNC_SERVICE"
}

refresh_qrcode() {
  sudo systemctl restart "$NAPCAT_SERVICE"
  sleep 6
  sudo journalctl -u "$NAPCAT_SERVICE" --no-pager -n 80 | grep -E "二维码解码URL|二维码已保存" | tail -4 || true
  echo
  echo "qrcode path: $QRCODE_PATH"
}

print_usage() {
  cat <<'EOF'
Yumemi 云端工作台
  [1/S] service   云端 bot / napcat 服务
  [2/A] chat      云端 chat / agent 开关
  [3/T] tools     二维码和 VNC
  [H/?] help      显示这个菜单
  [X/E] exit      退出

直达命令仍可用；需要完整列表时看 README_CLOUD.md。
EOF
}

print_service_usage() {
  cat <<'EOF'
云端服务
  [1/S] start         启动云端 napcat 和 bot
  [2/T] stop          停止云端 napcat 和 bot
  [3/R] restart       重启云端 napcat 和 bot
  [4/U] status        查看云端服务状态
  [5/B] attach-bot    实时跟随 bot 日志
  [6/N] attach-napcat 实时跟随 napcat 日志
  [7/P] peek-bot      查看 bot 最近日志
  [8/Q] peek-napcat   查看 napcat 最近日志
  [9/O] restart-bot   只重启 bot 服务
  [X/E] back          返回
EOF
}

print_chat_usage() {
  cat <<'EOF'
云端 Chat
  [1/S] status       查看 chat 配置摘要
  [2/O] on           打开 chat_enabled
  [3/F] off          关闭 chat_enabled
  [4/T] toggle       切换 chat_enabled
  [5/R] restart-bot  只重启 bot 服务
  [6/A] agent-on     打开 chat_agent_enabled
  [7/D] agent-off    关闭 chat_agent_enabled
  [8/N] network-on   打开 chat_agent_allow_network
  [9/W] network-off  关闭 chat_agent_allow_network
  [X/E] back         返回
EOF
}

print_tools_usage() {
  cat <<'EOF'
云端工具
  [1/Q] qrcode     重启 napcat 并刷新登录二维码
  [2/V] vnc-start  启动云端 VNC 服务
  [3/Z] vnc-stop   停止云端 VNC 服务
  [X/E] back       返回
EOF
}

run_action() {
  local action="${1:-}"
  shift || true
  case "$action" in
    service) service_menu ;;
    chat) if [[ -n "${1:-}" ]]; then run_action "chat-$1"; else chat_menu; fi ;;
    tools) tools_menu ;;
    start) start_all ;;
    stop) stop_all ;;
    restart) restart_all ;;
    restart-bot) restart_bot_service ;;
    status) status_all ;;
    attach-bot|bot) follow_logs "$BOT_SERVICE" ;;
    attach-napcat|napcat) follow_logs "$NAPCAT_SERVICE" ;;
    logs-bot|peek|peek-bot) show_logs "$BOT_SERVICE" ;;
    logs-napcat|peek-napcat) show_logs "$NAPCAT_SERVICE" ;;
    chat-status) chat_status ;;
    chat-on) chat_set true ;;
    chat-off) chat_set false ;;
    chat-toggle) chat_toggle ;;
    agent-on|chat-agent-on) chat_agent_set true ;;
    agent-off|chat-agent-off) chat_agent_set false ;;
    agent-toggle|chat-agent-toggle) chat_agent_toggle ;;
    network-on|chat-network-on|chat-agent-network-on) chat_agent_network_set true ;;
    network-off|chat-network-off|chat-agent-network-off) chat_agent_network_set false ;;
    network-toggle|chat-network-toggle|chat-agent-network-toggle) chat_agent_network_toggle ;;
    vnc-start|vnc) start_vnc ;;
    vnc-stop) stop_vnc ;;
    qrcode|qr) refresh_qrcode ;;
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
      H|\?) print_service_usage ;;
      X|E|"") return 0 ;;
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
      6|A) run_action agent-on ;;
      7|D) run_action agent-off ;;
      8|N) run_action network-on ;;
      9|W) run_action network-off ;;
      H|\?) print_chat_usage ;;
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
      1|Q) run_action qrcode ;;
      2|V) run_action vnc-start ;;
      3|Z) run_action vnc-stop ;;
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
    read -r -p "select Yumemi cloud action: " choice
    case "${choice^^}" in
      1|S) service_menu ;;
      2|A) chat_menu ;;
      3|T) tools_menu ;;
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
