#!/usr/bin/env bash
set -euo pipefail

export GIT_PAGER=cat

WIN_REPO_ROOT="${WIN_REPO_ROOT:-/mnt/d/Bot/Yumemi-Bot}"
WIN_IMAGES="${WIN_IMAGES:-$WIN_REPO_ROOT/resource/images}"
REPO_ROOT="${REPO_ROOT:-/home/ubuntu/Yumemi-Bot}"
TARGET_IMAGES="$REPO_ROOT/resource/images"
MANIFEST_PATH="${MANIFEST_PATH:-$WIN_REPO_ROOT/.git/yumemi_image_update_manifest.txt}"
FULL="${FULL:-0}"
CLEAR_MANIFEST="${CLEAR_MANIFEST:-0}"
RESUME="${RESUME:-0}"
STATE_ROOT="${STATE_ROOT:-$REPO_ROOT/.git/yumemi_image_push_state}"

BASE_BRANCH="${BASE_BRANCH:-main}"
MAX_BATCH_MB="${MAX_BATCH_MB:-700}"
MAX_BATCH_BYTES=$((MAX_BATCH_MB * 1024 * 1024))

UPDATE_DATE="${UPDATE_DATE:-$(date +%F)}"
TIME_TAG="${TIME_TAG:-$(date +%H%M%S)}"
BRANCH_NAME="${BRANCH_NAME:-update-image-library-${UPDATE_DATE}-${TIME_TAG}}"
COMMIT_PREFIX="更新图库（${UPDATE_DATE}）"
PR_TITLE="图库更新 ${UPDATE_DATE}"

STATE_DIR=""
STATE_FILE=""
BATCH_DIR=""
ENTRIES_FILE=""
CURRENT_BRANCH_FILE=""
TOTAL_BATCHES=0
LAST_COMMITTED_BATCH=0
LAST_PUSHED_BATCH=0
STATE_BRANCH_NAME=""
STATE_UPDATE_DATE=""
STATE_FULL="0"
STATE_BASE_BRANCH=""
STATE_MANIFEST_PATH=""

human_size() {
  if command -v numfmt >/dev/null 2>&1; then
    numfmt --to=iec --suffix=B "$1"
  else
    echo "${1}B"
  fi
}

ensure_state_paths() {
  mkdir -p "$STATE_ROOT"
  CURRENT_BRANCH_FILE="$STATE_ROOT/current_branch.txt"
  STATE_DIR="$STATE_ROOT/$BRANCH_NAME"
  STATE_FILE="$STATE_DIR/state.env"
  BATCH_DIR="$STATE_DIR/batches"
  ENTRIES_FILE="$STATE_DIR/entries.txt"
}

read_manifest_entries() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    return 0
  fi
  awk 'NF {print $0}' "$file" | sort -u
}

entry_pathspec() {
  local entry="$1"
  printf 'resource/images/%s' "$entry"
}

entry_size_bytes() {
  local entry="$1"
  local src="$WIN_IMAGES/$entry"
  local dst="$TARGET_IMAGES/$entry"

  if [[ -d "$src" ]]; then
    du -sb "$src" | awk '{print $1}'
  elif [[ -f "$src" ]]; then
    stat -c%s "$src"
  elif [[ -d "$dst" ]]; then
    du -sb "$dst" | awk '{print $1}'
  elif [[ -f "$dst" ]]; then
    stat -c%s "$dst"
  else
    echo 0
  fi
}

print_entries_summary() {
  local batch_file="$1"
  local entries=()
  mapfile -t entries < "$batch_file"
  echo "Entries (${#entries[@]}): ${entries[*]}"
}

sync_entry() {
  local entry="$1"
  local src="$WIN_IMAGES/$entry"
  local dst="$TARGET_IMAGES/$entry"

  if [[ -d "$src" ]]; then
    mkdir -p "$dst"
    rsync -a --delete "$src/" "$dst/"
    echo "  synced dir : $entry"
  elif [[ -f "$src" ]]; then
    mkdir -p "$(dirname "$dst")"
    rsync -a "$src" "$dst"
    echo "  synced file: $entry"
  elif [[ -e "$dst" ]]; then
    rm -rf "$dst"
    echo "  removed    : $entry"
  else
    echo "  skipped    : $entry (源和目标都不存在)"
  fi
}

collect_changed_entries_from_git() {
  local -a tracked_paths=()
  local -a untracked_paths=()
  local -A seen_entries=()
  local rel top p

  mapfile -d '' tracked_paths < <(git diff --name-only -z -- resource/images)
  mapfile -d '' untracked_paths < <(git ls-files --others --exclude-standard -z -- resource/images)

  for p in "${tracked_paths[@]}" "${untracked_paths[@]}"; do
    [[ -n "$p" ]] || continue
    rel="${p#resource/images/}"
    [[ -n "$rel" ]] || continue
    if [[ "$rel" == */* ]]; then
      top="${rel%%/*}"
    else
      top="$rel"
    fi
    seen_entries["$top"]=1
  done

  printf '%s\n' "${!seen_entries[@]}" | sort
}

branch_has_upstream() {
  git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1
}

save_state() {
  mkdir -p "$STATE_DIR" "$BATCH_DIR"
  cat > "$STATE_FILE" <<STATEEOF
BRANCH_NAME='$BRANCH_NAME'
BASE_BRANCH='$BASE_BRANCH'
UPDATE_DATE='$UPDATE_DATE'
FULL='$FULL'
MANIFEST_PATH='$MANIFEST_PATH'
MAX_BATCH_MB='$MAX_BATCH_MB'
TOTAL_BATCHES='$TOTAL_BATCHES'
LAST_COMMITTED_BATCH='$LAST_COMMITTED_BATCH'
LAST_PUSHED_BATCH='$LAST_PUSHED_BATCH'
STATEEOF
  printf '%s\n' "$BRANCH_NAME" > "$CURRENT_BRANCH_FILE"
}

load_state() {
  if [[ -z "${BRANCH_NAME:-}" && -f "$CURRENT_BRANCH_FILE" ]]; then
    BRANCH_NAME="$(tr -d '\r\n' < "$CURRENT_BRANCH_FILE")"
  fi
  if [[ -z "${BRANCH_NAME:-}" ]]; then
    echo "Error: RESUME=1 时未提供 BRANCH_NAME，且没有找到 current_branch.txt。"
    exit 1
  fi

  STATE_DIR="$STATE_ROOT/$BRANCH_NAME"
  STATE_FILE="$STATE_DIR/state.env"
  BATCH_DIR="$STATE_DIR/batches"
  ENTRIES_FILE="$STATE_DIR/entries.txt"

  if [[ ! -f "$STATE_FILE" ]]; then
    echo "Error: 未找到断点状态文件："
    echo "  $STATE_FILE"
    exit 1
  fi

  # shellcheck disable=SC1090
  source "$STATE_FILE"

  STATE_BRANCH_NAME="$BRANCH_NAME"
  STATE_UPDATE_DATE="$UPDATE_DATE"
  STATE_FULL="$FULL"
  STATE_BASE_BRANCH="$BASE_BRANCH"
  STATE_MANIFEST_PATH="$MANIFEST_PATH"
  TOTAL_BATCHES="${TOTAL_BATCHES:-0}"
  LAST_COMMITTED_BATCH="${LAST_COMMITTED_BATCH:-0}"
  LAST_PUSHED_BATCH="${LAST_PUSHED_BATCH:-0}"
}

prepare_new_state() {
  ensure_state_paths
  if [[ -e "$STATE_DIR" ]]; then
    echo "Error: 断点状态目录已存在："
    echo "  $STATE_DIR"
    echo "说明该分支名之前已经用过。"
    echo "你可以："
    echo "  1) RESUME=1 BRANCH_NAME=$BRANCH_NAME bash $0"
    echo "  2) 或者换一个新分支名重跑"
    exit 1
  fi
  mkdir -p "$STATE_DIR" "$BATCH_DIR"
}

stage_and_commit_batch() {
  local batch_file="$1"
  local batch_index="$2"
  local batch_count="$3"
  local batch_bytes="$4"
  local -a entries=()
  local -a pathspecs=()
  local entry

  mapfile -t entries < "$batch_file"
  [[ ${#entries[@]} -gt 0 ]] || return 0

  for entry in "${entries[@]}"; do
    pathspecs+=("$(entry_pathspec "$entry")")
  done

  echo "--- Batch $batch_index/$batch_count ---"
  echo "Approx size: $(human_size "$batch_bytes")"
  echo "Entries: ${#entries[@]}"
  print_entries_summary "$batch_file"

  git add -A -- "${pathspecs[@]}"

  if git diff --cached --quiet -- "${pathspecs[@]}"; then
    echo "Nothing staged in this batch, skipped."
    echo
    return 1
  fi

  git --no-pager diff --cached --shortstat -- "${pathspecs[@]}" || true
  git commit -m "${COMMIT_PREFIX} ${batch_index}/${batch_count}"
  LAST_COMMITTED_BATCH="$batch_index"
  save_state
  return 0
}

push_current_branch() {
  if branch_has_upstream; then
    git push
  else
    git push -u origin "$BRANCH_NAME"
  fi
}

finish_after_push_if_needed() {
  if (( LAST_COMMITTED_BATCH > LAST_PUSHED_BATCH )); then
    LAST_PUSHED_BATCH="$LAST_COMMITTED_BATCH"
    save_state
  fi
}

build_batches_from_entries_file() {
  local -a work_entries=()
  mapfile -t work_entries < "$ENTRIES_FILE"

  if [[ ${#work_entries[@]} -eq 0 ]]; then
    echo "No candidate entries found under resource/images."
    exit 0
  fi

  TOTAL_BATCHES=0
  local current_batch_bytes=0
  local current_batch_items=0
  local current_batch_file=""
  local entry size

  rm -rf "$BATCH_DIR"
  mkdir -p "$BATCH_DIR"

  new_batch() {
    TOTAL_BATCHES=$((TOTAL_BATCHES + 1))
    current_batch_file="$BATCH_DIR/batch_${TOTAL_BATCHES}.lst"
    : > "$current_batch_file"
    current_batch_bytes=0
    current_batch_items=0
  }

  new_batch

  for entry in "${work_entries[@]}"; do
    [[ -n "$entry" ]] || continue
    size="$(entry_size_bytes "$entry")"

    if (( current_batch_items > 0 && current_batch_bytes + size > MAX_BATCH_BYTES )); then
      printf '%s\n' "$current_batch_bytes" > "${current_batch_file}.bytes"
      new_batch
    fi

    printf '%s\n' "$entry" >> "$current_batch_file"
    current_batch_bytes=$((current_batch_bytes + size))
    current_batch_items=$((current_batch_items + 1))
  done

  printf '%s\n' "$current_batch_bytes" > "${current_batch_file}.bytes"
  save_state

  echo "Planned batches: $TOTAL_BATCHES"
  local i bytes count
  for i in $(seq 1 "$TOTAL_BATCHES"); do
    bytes="$(cat "$BATCH_DIR/batch_${i}.lst.bytes")"
    count="$(wc -l < "$BATCH_DIR/batch_${i}.lst")"
    echo "  Batch $i/$TOTAL_BATCHES: ${count} entries, approx $(human_size "$bytes")"
  done
  echo
}

prepare_entries_for_new_run() {
  local -a selected_entries=()
  local -a work_entries=()

  if [[ "$FULL" != "1" ]]; then
    if [[ -f "$MANIFEST_PATH" ]]; then
      mapfile -t selected_entries < <(read_manifest_entries "$MANIFEST_PATH")
    fi
    if [[ ${#selected_entries[@]} -eq 0 ]]; then
      echo "Manifest 模式下没有读取到任何条目。"
      echo "你可以先运行 import/flatten 脚本的 --apply，让它们写入改动清单；"
      echo "或者临时全量同步：FULL=1 bash $0"
      exit 0
    fi
  fi

  cd "$REPO_ROOT"

  echo "=== Full repo status (reference only) ==="
  git --no-pager status --short || true
  echo

  echo "=== Switch to base branch ==="
  git fetch origin --prune || true
  git switch "$BASE_BRANCH"
  echo

  if git rev-parse --verify "$BRANCH_NAME" >/dev/null 2>&1; then
    echo "Error: Branch already exists:"
    echo "  $BRANCH_NAME"
    echo "若要续传，请使用："
    echo "  RESUME=1 BRANCH_NAME=$BRANCH_NAME bash $0"
    exit 1
  fi

  echo "=== Create new branch ==="
  git switch -c "$BRANCH_NAME"
  echo

  echo "=== Sync resource/images ==="
  mkdir -p "$TARGET_IMAGES"
  if [[ "$FULL" == "1" ]]; then
    rsync -a --delete --info=progress2 "$WIN_IMAGES/" "$TARGET_IMAGES/"
  else
    echo "Entries to sync: ${#selected_entries[@]}"
    local entry
    for entry in "${selected_entries[@]}"; do
      sync_entry "$entry"
    done
  fi
  echo
  echo "Sync finished."
  echo

  if [[ "$FULL" == "1" ]]; then
    mapfile -t work_entries < <(collect_changed_entries_from_git)
  else
    work_entries=("${selected_entries[@]}")
  fi

  if [[ ${#work_entries[@]} -eq 0 ]]; then
    echo "No candidate entries found under resource/images."
    exit 0
  fi

  printf '%s\n' "${work_entries[@]}" > "$ENTRIES_FILE"
  build_batches_from_entries_file
}

resume_existing_run() {
  mkdir -p "$STATE_ROOT"
  CURRENT_BRANCH_FILE="$STATE_ROOT/current_branch.txt"
  load_state

  FULL="$STATE_FULL"
  BASE_BRANCH="$STATE_BASE_BRANCH"
  MANIFEST_PATH="$STATE_MANIFEST_PATH"
  UPDATE_DATE="$STATE_UPDATE_DATE"
  COMMIT_PREFIX="更新图库（${UPDATE_DATE}）"
  PR_TITLE="图库更新 ${UPDATE_DATE}"

  echo "=== Resume mode ==="
  echo "State dir:         $STATE_DIR"
  echo "Branch:            $BRANCH_NAME"
  echo "Base branch:       $BASE_BRANCH"
  echo "Mode:              $([[ "$FULL" == "1" ]] && echo 'FULL' || echo 'MANIFEST')"
  echo "Last committed:    $LAST_COMMITTED_BATCH/$TOTAL_BATCHES"
  echo "Last pushed:       $LAST_PUSHED_BATCH/$TOTAL_BATCHES"
  echo

  cd "$REPO_ROOT"
  git fetch origin --prune || true
  git switch "$BRANCH_NAME"
  echo

  if (( LAST_COMMITTED_BATCH > LAST_PUSHED_BATCH )); then
    echo "检测到有本地已提交但未确认推送的批次，先尝试补推当前分支..."
    if push_current_branch; then
      finish_after_push_if_needed
      echo "补推成功。"
      echo
    else
      echo "补推失败。请稍后再次执行相同的 RESUME 命令。"
      exit 1
    fi
  fi
}

run_batches_from_state() {
  local start_batch=$((LAST_PUSHED_BATCH + 1))
  local i batch_file batch_bytes

  if (( TOTAL_BATCHES <= 0 )); then
    echo "Error: 状态文件中的 TOTAL_BATCHES 无效。"
    exit 1
  fi

  if (( start_batch > TOTAL_BATCHES )); then
    echo "所有批次都已推送完成。"
    echo
  else
    echo "=== Commit and push batches ==="
    for i in $(seq "$start_batch" "$TOTAL_BATCHES"); do
      batch_file="$BATCH_DIR/batch_${i}.lst"
      batch_bytes="$(cat "${batch_file}.bytes")"

      if stage_and_commit_batch "$batch_file" "$i" "$TOTAL_BATCHES" "$batch_bytes"; then
        if push_current_branch; then
          LAST_PUSHED_BATCH="$i"
          save_state
        else
          echo
          echo "Push failed on batch $i/$TOTAL_BATCHES."
          echo "稍后可继续执行："
          echo "  RESUME=1 BRANCH_NAME=$BRANCH_NAME bash $0"
          exit 1
        fi
      fi
      echo
    done
  fi

  if [[ "$FULL" != "1" && "$CLEAR_MANIFEST" == "1" ]]; then
    : > "$MANIFEST_PATH"
    echo "Manifest cleared: $MANIFEST_PATH"
    echo
  fi

  echo "=== Done ==="
  echo "Branch:    $BRANCH_NAME"
  echo "PR title:  $PR_TITLE"
  echo "Date note: $UPDATE_DATE"
  echo "State dir: $STATE_DIR"
  echo
  echo "Now open GitHub in your browser and create a PR manually."
}

echo "=== Check paths ==="
echo "Windows repo root: $WIN_REPO_ROOT"
echo "Windows source:    $WIN_IMAGES"
echo "WSL repo root:     $REPO_ROOT"
echo "WSL target:        $TARGET_IMAGES"
echo "Manifest:          $MANIFEST_PATH"
echo "State root:        $STATE_ROOT"
echo "Mode:              $([[ "$FULL" == "1" ]] && echo 'FULL' || echo 'MANIFEST')"
echo "Resume:            $RESUME"
echo "Base branch:       $BASE_BRANCH"
echo "Batch limit:       ${MAX_BATCH_MB} MiB"
echo "Branch name:       $BRANCH_NAME"
echo

if [[ ! -d "$WIN_IMAGES" ]]; then
  echo "Error: Windows images directory not found:"
  echo "  $WIN_IMAGES"
  exit 1
fi

if [[ ! -d "$REPO_ROOT/.git" && ! -f "$REPO_ROOT/.git" ]]; then
  echo "Error: Not a git repository:"
  echo "  $REPO_ROOT"
  exit 1
fi

if [[ "$RESUME" == "1" ]]; then
  resume_existing_run
else
  prepare_new_state
  prepare_entries_for_new_run
fi

run_batches_from_state
