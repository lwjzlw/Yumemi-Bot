#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${REPO_ROOT:-}" ]]; then
  if [[ -d "$(pwd)/resource/images" && -d "$(pwd)/tools" ]]; then
    REPO_ROOT="$(pwd)"
  elif [[ -d "/home/ubuntu/Yumemi-Bot/resource/images" ]]; then
    REPO_ROOT="/home/ubuntu/Yumemi-Bot"
  else
    REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  fi
fi
WORKFLOW="$REPO_ROOT/tools/image_update_workflow.sh"
NORMALIZE="$REPO_ROOT/tools/normalize_image_names.py"
CHECK="$REPO_ROOT/tools/check_image_folders.py"
cd "$REPO_ROOT"

run_workflow() {
  "$WORKFLOW" "$@"
}

run_step() {
  local title="$1"
  shift
  echo
  echo "==> $title"
  "$@"
  echo "==> $title 完成"
}

organize_images() {
  python "$NORMALIZE" --apply --recursive
  echo
  echo "下一步建议："
  echo "  Q) check"
  echo "  C) cloud"
  echo "  G) git-add"
}

dedupe_images() {
  python "$NORMALIZE" --apply --recursive --dedupe
  echo
  echo "下一步建议："
  echo "  Q) check"
  echo "  C) cloud"
  echo "  G) git-add"
}

mark_roles() {
  local names
  read -r -p "写入 manifest 的角色名，可空格分隔: " names
  if [[ -z "${names// }" ]]; then
    echo "未输入角色名。"
    return 1
  fi
  # shellcheck disable=SC2206
  local args=($names)
  run_workflow mark "${args[@]}"
}

commit_images() {
  local message
  read -r -p "commit message [更新图库]: " message
  if [[ -n "$message" ]]; then
    COMMIT_MESSAGE="$message" run_workflow commit
  else
    run_workflow commit
  fi
}

print_usage() {
  cat <<'EOF'
usage:
  [1/S] sync-temp   同步 Windows temp 到 WSL temp
  [2/I] import      导入 temp 图片
  [3/O] organize    整理图库命名
  [4/D] dedupe      删除重复图片
  [Q]   check       检查图库
  [C]   cloud       同步到云端
  [G]   git-add     暂存图库改动
  [K]   commit      提交图库改动
  [U]   push        推送当前分支
  [T]   status      查看状态
  [R]   manifest    显示变更清单
  [E]   clear       清空变更清单
  [M]   mark        手动标记角色
  [H/?] help        显示帮助
  [X]   exit        退出
EOF
}

run_action() {
  case "${1:-}" in
    sync-temp) run_step "同步 temp" run_workflow sync-temp ;;
    import|apply) run_step "导入图片" run_workflow import ;;
    organize|organize-apply|normalize-all|apply-all) run_step "整理图库" organize_images ;;
    dedupe) run_step "删除重复图片" dedupe_images ;;
    mark) mark_roles ;;
    cloud) run_step "同步云端" run_workflow cloud ;;
    git-add) run_step "暂存 Git 改动" run_workflow git-add ;;
    commit) run_step "提交 Git 改动" commit_images ;;
    push) run_step "推送当前分支" run_workflow push ;;
    status) run_step "查看状态" run_workflow status ;;
    manifest) run_step "显示变更清单" run_workflow manifest ;;
    clear) run_step "清空变更清单" run_workflow clear ;;
    check) run_step "检查图库" python "$CHECK" ;;
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

if [[ $# -eq 0 ]]; then
  while true; do
    print_usage
    echo
    read -r -p "select image action: " choice
    case "${choice^^}" in
      1|S) run_action sync-temp ;;
      2|I) run_action import ;;
      3|O) run_action organize ;;
      4|D) run_action dedupe ;;
      M) run_action mark ;;
      C) run_action cloud ;;
      G) run_action git-add ;;
      K) run_action commit ;;
      U) run_action push ;;
      T) run_action status ;;
      R) run_action manifest ;;
      E) run_action clear ;;
      Q) run_action check ;;
      H|\?) print_usage ;;
      X|"")
        echo "bye."
        exit 0
        ;;
      *) echo "unknown selection: $choice" ;;
    esac
    echo
    read -r -p "press Enter to return to menu..." _
    echo
  done
else
  run_action "${1:-}"
fi
