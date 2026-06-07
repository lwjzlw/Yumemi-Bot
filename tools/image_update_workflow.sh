#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
WIN_TEMP="${WIN_TEMP:-/mnt/d/Bot/Yumemi-Bot/resource/temp}"
WSL_TEMP="${WSL_TEMP:-$REPO_ROOT/resource/temp}"
MANIFEST_PATH="${MANIFEST_PATH:-$REPO_ROOT/.git/yumemi_image_update_manifest.txt}"
CLOUD_KEY="${CLOUD_KEY:-/home/lwjzlw/.ssh/yumemi_aliyun}"
CLOUD_HOST="${CLOUD_HOST:-47.100.170.173}"
CLOUD_USER="${CLOUD_USER:-yumemi}"
CLOUD_REPO="${CLOUD_REPO:-/home/yumemi/Yumemi-Bot}"
COMMIT_MESSAGE="${COMMIT_MESSAGE:-更新图库}"

cd "$REPO_ROOT"

usage() {
  cat <<'EOF'
usage:
  tools/image_update_workflow.sh [command]

commands:
  sync-temp      从 Windows temp 同步到 WSL resource/temp
  import         导入 temp 中可匹配的图片，未匹配的只报告
  organize
                执行整理全图库，只修改真正需要整理的角色
  dedupe         按 SHA256 删除重复图，删除前备份到 resource/temp
  check          检查图库并生成报告
  cloud          只把 manifest 涉及的角色图片同步到云端
  git-add        只 git add manifest 涉及的角色图片和相关报告
  commit         git-add 后提交，提交信息默认“更新图库”
  push           git push 当前分支
  mark NAME...   手动把角色名写入 manifest
  clear          清空 manifest
  manifest       显示当前 manifest
  status         显示 git 状态和 manifest

env:
  WIN_TEMP       Windows 待导入目录，默认 /mnt/d/Bot/Yumemi-Bot/resource/temp
  MANIFEST_PATH 变更角色清单，默认 .git/yumemi_image_update_manifest.txt
  COMMIT_MESSAGE commit 信息，默认“更新图库”

typical:
  tools/image_update_workflow.sh sync-temp
  tools/image_update_workflow.sh import
  tools/image_update_workflow.sh organize
  tools/image_update_workflow.sh check
  tools/image_update_workflow.sh cloud
  tools/image_update_workflow.sh git-add
EOF
}

ensure_manifest_parent() {
  mkdir -p "$(dirname "$MANIFEST_PATH")"
}

read_manifest_entries() {
  [[ -f "$MANIFEST_PATH" ]] || return 0
  awk 'NF {print $0}' "$MANIFEST_PATH" | sort -u
}

append_manifest_entries() {
  ensure_manifest_parent
  {
    read_manifest_entries || true
    printf '%s\n' "$@"
  } | awk 'NF {print $0}' | sort -u > "${MANIFEST_PATH}.tmp"
  mv "${MANIFEST_PATH}.tmp" "$MANIFEST_PATH"
}

sync_temp() {
  if [[ ! -d "$WIN_TEMP" ]]; then
    echo "Windows temp not found: $WIN_TEMP"
    exit 1
  fi
  mkdir -p "$WSL_TEMP"
  echo "开始同步 temp..."
  echo "  from: $WIN_TEMP/"
  echo "  to:   $WSL_TEMP/"
  rsync -a --info=progress2 "$WIN_TEMP/" "$WSL_TEMP/"
  echo
  echo "temp 同步完成。"
}

manifest_args() {
  mapfile -t entries < <(read_manifest_entries)
  if [[ ${#entries[@]} -eq 0 ]]; then
    return 1
  fi
  printf '%s\0' "${entries[@]}"
}

run_import() {
  ensure_manifest_parent
  python tools/import_temp_images.py --manifest "$MANIFEST_PATH"
  echo
  echo "下一步建议："
  echo "  1) yumemi_imagetools organize"
  echo "  2) yumemi_imagetools check"
  echo "  3) yumemi_imagetools cloud / git-add"
}

organize_images() {
  python tools/normalize_image_names.py --apply --recursive
  echo
  echo "下一步建议：yumemi_imagetools check"
}

dedupe_images() {
  python tools/normalize_image_names.py --apply --recursive --dedupe
  echo
  echo "下一步建议：yumemi_imagetools check"
}

sync_cloud() {
  mapfile -t entries < <(read_manifest_entries)
  if [[ ${#entries[@]} -eq 0 ]]; then
    echo "manifest 为空，没有需要同步到云端的角色。"
    return 0
  fi
  for entry in "${entries[@]}"; do
    local src="resource/images/$entry"
    local dst="$CLOUD_USER@$CLOUD_HOST:$CLOUD_REPO/resource/images/$entry"
    if [[ -d "$src" ]]; then
      rsync -az --delete --info=progress2 -e "ssh -i $CLOUD_KEY" "$src/" "$dst/"
      echo "cloud synced: $entry"
    else
      ssh -i "$CLOUD_KEY" "$CLOUD_USER@$CLOUD_HOST" "rm -rf '$CLOUD_REPO/resource/images/$entry'"
      echo "cloud removed: $entry"
    fi
  done
}

git_add_manifest() {
  mapfile -t entries < <(read_manifest_entries)
  if [[ ${#entries[@]} -eq 0 ]]; then
    echo "manifest 为空，没有需要 git add 的角色。"
    return 0
  fi
  local pathspecs=()
  for entry in "${entries[@]}"; do
    pathspecs+=("resource/images/$entry")
  done
  git add -A -- "${pathspecs[@]}"
  git add -A -- resource/image_folder_check_report.txt resource/image_folder_image_count.csv resource/image_small_files.csv 2>/dev/null || true
  git --no-pager status --short -- "${pathspecs[@]}" resource/image_folder_check_report.txt resource/image_folder_image_count.csv resource/image_small_files.csv
}

commit_manifest() {
  git_add_manifest
  if git diff --cached --quiet; then
    echo "没有 staged 改动，跳过 commit。"
    return 0
  fi
  git commit -m "$COMMIT_MESSAGE"
}

show_manifest() {
  if [[ -f "$MANIFEST_PATH" ]]; then
    cat "$MANIFEST_PATH"
  else
    echo "manifest not found: $MANIFEST_PATH"
  fi
}

clear_manifest() {
  ensure_manifest_parent
  : > "$MANIFEST_PATH"
  echo "cleared: $MANIFEST_PATH"
}

mark_entries() {
  if [[ $# -eq 0 ]]; then
    echo "usage: tools/image_update_workflow.sh mark NAME..."
    exit 1
  fi
  append_manifest_entries "$@"
  show_manifest
}

show_status() {
  echo "repo:      $REPO_ROOT"
  echo "win temp:  $WIN_TEMP"
  echo "wsl temp:  $WSL_TEMP"
  echo "manifest:  $MANIFEST_PATH"
  echo
  echo "manifest entries:"
  read_manifest_entries || true
  echo
  git --no-pager status --short -- resource/images resource/temp resource/image_folder_check_report.txt resource/image_folder_count.csv "$MANIFEST_PATH" || true
}

case "${1:-help}" in
  sync-temp) sync_temp ;;
  import|apply) run_import ;;
  organize|normalize|normalize-apply) organize_images ;;
  dedupe) dedupe_images ;;
  check) python tools/check_image_folders.py ;;
  cloud) sync_cloud ;;
  git-add) git_add_manifest ;;
  commit) commit_manifest ;;
  push) git push ;;
  mark) shift; mark_entries "$@" ;;
  clear) clear_manifest ;;
  manifest) show_manifest ;;
  status) show_status ;;
  help|-h|--help) usage ;;
  *)
    echo "unknown command: $1"
    echo
    usage
    exit 1
    ;;
esac
