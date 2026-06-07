#!/usr/bin/env bash
set -euo pipefail

KEY_PATH="${KEY_PATH:-/home/lwjzlw/.ssh/yumemi_aliyun}"
REMOTE="${REMOTE:-root@47.100.170.173}"
LOCAL_PORT="${LOCAL_PORT:-5900}"
REMOTE_PORT="${REMOTE_PORT:-5900}"

ssh -i "$KEY_PATH" "$REMOTE" \
  "systemctl start yumemi-xvfb yumemi-vnc; systemctl is-active --quiet yumemi-vnc"

echo "VNC is available at localhost:${LOCAL_PORT} while this tunnel stays open."
echo "Open MobaXterm VNC to localhost:${LOCAL_PORT}, or keep this terminal running."
ssh -i "$KEY_PATH" -N -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" "$REMOTE"
