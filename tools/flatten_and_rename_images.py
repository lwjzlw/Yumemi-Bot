from pathlib import Path
import shutil
import sys
import uuid
import argparse
import re

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
NAME_NUM_TEMPLATE = r"^{name}_(\d+)$"


def find_project_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / "resource" / "images").exists():
            return path
    raise FileNotFoundError("未找到 resource/images，请确认脚本位于 Yumemi-Bot 项目目录内。")


def get_manifest_path(project_root: Path, custom_path: str | None = None) -> Path:
    if custom_path:
        return Path(custom_path).expanduser().resolve()
    git_dir = project_root / ".git"
    if git_dir.is_dir():
        return git_dir / "yumemi_image_update_manifest.txt"
    return project_root / ".yumemi_image_update_manifest.txt"


def append_manifest_entries(manifest_path: Path, entries: list[str]):
    if not entries:
        return
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            existing = {line.strip() for line in f if line.strip()}
    merged = sorted(existing | set(entries))
    with open(manifest_path, "w", encoding="utf-8") as f:
        for item in merged:
            f.write(item + "\n")


def is_image_file(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in IMAGE_EXTS


def unique_temp_name(dest_dir: Path, suffix: str, occupied_names: set[str] | None = None, prefix: str = "__tmp__") -> Path:
    while True:
        candidate = dest_dir / f"{prefix}{uuid.uuid4().hex}{suffix.lower()}"
        if candidate.exists():
            continue
        if occupied_names is not None and candidate.name in occupied_names:
            continue
        return candidate


def collect_nested_images(char_dir: Path):
    nested = []
    for p in char_dir.rglob("*"):
        if is_image_file(p) and p.parent != char_dir:
            nested.append(p)
    return sorted(nested, key=lambda x: (len(x.relative_to(char_dir).parts), str(x.relative_to(char_dir))))


def collect_root_images(char_dir: Path):
    files = [p for p in char_dir.iterdir() if is_image_file(p)]
    return sorted(files, key=lambda x: x.name.lower())


def build_name_pattern(char_name: str):
    return re.compile(NAME_NUM_TEMPLATE.format(name=re.escape(char_name)))


def evaluate_empty_subdirs_after_flatten(char_dir: Path):
    subdirs = [p for p in char_dir.rglob("*") if p.is_dir() and p != char_dir]
    subdirs = sorted(subdirs, key=lambda x: (-len(x.relative_to(char_dir).parts), str(x)))

    deleted = []
    not_deleted = []
    deleted_set = set()

    for d in subdirs:
        has_remaining_content = False
        for child in d.iterdir():
            if child.is_file() and child.suffix.lower() in IMAGE_EXTS:
                continue
            if child.is_dir() and child in deleted_set:
                continue
            has_remaining_content = True
            break

        if has_remaining_content:
            not_deleted.append(d)
        else:
            deleted.append(d)
            deleted_set.add(d)

    return deleted, not_deleted


def delete_empty_subdirs_after_flatten(char_dir: Path):
    deleted, not_deleted = evaluate_empty_subdirs_after_flatten(char_dir)
    for d in deleted:
        try:
            d.rmdir()
        except Exception:
            if d in deleted:
                deleted.remove(d)
            not_deleted.append(d)
    return deleted, sorted(not_deleted, key=lambda x: (len(x.relative_to(char_dir).parts), str(x)))


def plan_root_state(char_dir: Path):
    moved = []
    move_collisions = []
    records = []

    root_images = collect_root_images(char_dir)
    occupied_names = {p.name for p in root_images}

    for p in root_images:
        records.append({
            "source": p,
            "planned_root_name": p.name,
            "will_move": False,
        })

    nested_images = collect_nested_images(char_dir)
    for src in nested_images:
        preferred_dest = char_dir / src.name
        if preferred_dest.name in occupied_names or preferred_dest.exists():
            dest = unique_temp_name(char_dir, src.suffix, occupied_names=occupied_names, prefix="__flatten__")
            move_collisions.append((src, dest))
        else:
            dest = preferred_dest

        occupied_names.add(dest.name)
        moved.append((src, dest))
        records.append({
            "source": src,
            "planned_root_name": dest.name,
            "will_move": True,
        })

    return records, moved, move_collisions


def plan_incremental_renames(char_dir: Path, records: list[dict]):
    char_name = char_dir.name
    pattern = build_name_pattern(char_name)

    kept_numbers = set()
    rename_candidates = []

    for rec in sorted(records, key=lambda x: x["planned_root_name"].lower()):
        stem = Path(rec["planned_root_name"]).stem
        m = pattern.match(stem)
        if m:
            num = int(m.group(1))
            if num not in kept_numbers:
                kept_numbers.add(num)
                rec["final_name"] = rec["planned_root_name"]
                rec["needs_rename"] = False
                continue
        rename_candidates.append(rec)

    def next_available_number(used_numbers: set[int]) -> int:
        n = 1
        while n in used_numbers:
            n += 1
        return n

    rename_pairs = []
    for rec in sorted(rename_candidates, key=lambda x: x["planned_root_name"].lower()):
        new_num = next_available_number(kept_numbers)
        kept_numbers.add(new_num)
        suffix = Path(rec["planned_root_name"]).suffix.lower()
        final_name = f"{char_name}_{new_num}{suffix}"
        rec["final_name"] = final_name
        rec["needs_rename"] = final_name != rec["planned_root_name"]
        if rec["needs_rename"]:
            rename_pairs.append((rec["planned_root_name"], final_name))

    return rename_pairs


def apply_plan(char_dir: Path, records: list[dict], moved: list[tuple[Path, Path]], apply: bool):
    if apply:
        for src, dest in moved:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
        subdirs_deleted, subdirs_not_deleted = delete_empty_subdirs_after_flatten(char_dir)
    else:
        subdirs_deleted, subdirs_not_deleted = evaluate_empty_subdirs_after_flatten(char_dir)

    rename_pairs = []
    rename_conflicts = []

    for rec in records:
        if rec.get("needs_rename"):
            current_path = char_dir / rec["planned_root_name"]
            final_path = char_dir / rec["final_name"]
            if final_path.exists() and final_path.name != current_path.name:
                rename_conflicts.append((current_path, final_path))
                continue
            if apply:
                current_path.rename(final_path)
            rename_pairs.append((rec["planned_root_name"], rec["final_name"]))

    return rename_pairs, rename_conflicts, subdirs_deleted, subdirs_not_deleted


def process_character_dir(char_dir: Path, apply: bool):
    records, moved, move_collisions = plan_root_state(char_dir)
    planned_rename_pairs = plan_incremental_renames(char_dir, records)
    rename_pairs, rename_conflicts, subdirs_deleted, subdirs_not_deleted = apply_plan(char_dir, records, moved, apply)

    return {
        "char_dir": char_dir,
        "moved": moved,
        "move_collisions": move_collisions,
        "subdirs_deleted": subdirs_deleted,
        "subdirs_not_deleted": subdirs_not_deleted,
        "rename_pairs": rename_pairs if apply else planned_rename_pairs,
        "rename_conflicts": rename_conflicts,
    }


def main():
    parser = argparse.ArgumentParser(description="整理角色图片文件夹：提取子文件夹图片，并仅对新增/异常命名图片做增量编号")
    parser.add_argument("--apply", action="store_true", help="真正执行修改。默认仅预览。")
    parser.add_argument("--only", nargs="*", default=None, help="只处理指定角色文件夹名，可写多个。")
    parser.add_argument("--manifest", default=None, help="改动清单输出位置；默认写入 .git/yumemi_image_update_manifest.txt")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent

    try:
        project_root = find_project_root(script_dir)
    except Exception as e:
        print(f"错误：{e}")
        sys.exit(1)

    images_dir = project_root / "resource" / "images"
    manifest_path = get_manifest_path(project_root, args.manifest)
    char_dirs = sorted([p for p in images_dir.iterdir() if p.is_dir()], key=lambda x: x.name)

    if args.only:
        only_set = set(args.only)
        char_dirs = [p for p in char_dirs if p.name in only_set]
        missing = sorted(only_set - {p.name for p in char_dirs})
        if missing:
            print("以下指定文件夹不存在：")
            for name in missing:
                print(f"  {name}")

    print("=" * 60)
    print(f"项目根目录：{project_root}")
    print(f"图片目录：{images_dir}")
    print(f"模式：{'执行模式 (--apply)' if args.apply else '预览模式'}")
    print(f"改动清单：{manifest_path}")
    print("=" * 60)

    total_moved = 0
    total_renamed = 0
    total_deleted_dirs = 0
    total_not_deleted_dirs = 0
    touched_folders = []

    for char_dir in char_dirs:
        result = process_character_dir(char_dir, args.apply)

        moved_count = len(result["moved"])
        renamed_count = len(result["rename_pairs"])
        deleted_count = len(result["subdirs_deleted"])
        not_deleted_count = len(result["subdirs_not_deleted"])

        if moved_count == 0 and renamed_count == 0 and deleted_count == 0 and not_deleted_count == 0:
            continue

        touched_folders.append(char_dir.name)
        total_moved += moved_count
        total_renamed += renamed_count
        total_deleted_dirs += deleted_count
        total_not_deleted_dirs += not_deleted_count

        print(f"\n[{char_dir.name}]")
        print(f"  移出子文件夹图片：{moved_count}")
        print(f"  增量重命名图片：{renamed_count}")
        print(f"  删除空子文件夹：{deleted_count}")
        print(f"  未删除子文件夹：{not_deleted_count}")

        if result["move_collisions"]:
            print("  重名移动已自动改为临时名：")
            for src, dst in result["move_collisions"][:10]:
                print(f"    {src.relative_to(char_dir)}  ->  {dst.name}")
            if len(result["move_collisions"]) > 10:
                print(f"    ... 共 {len(result['move_collisions'])} 项")

        if result["rename_pairs"]:
            print("  本次将编号/修正命名：")
            for src_name, dst_name in result["rename_pairs"][:10]:
                print(f"    {src_name}  ->  {dst_name}")
            if len(result["rename_pairs"]) > 10:
                print(f"    ... 共 {len(result['rename_pairs'])} 项")

        if result["subdirs_not_deleted"]:
            print("  未删除的子文件夹（通常因为还有非图片文件或其他内容）：")
            for d in result["subdirs_not_deleted"][:10]:
                print(f"    {d.relative_to(char_dir)}")
            if len(result["subdirs_not_deleted"]) > 10:
                print(f"    ... 共 {len(result['subdirs_not_deleted'])} 项")

    if args.apply and touched_folders:
        append_manifest_entries(manifest_path, touched_folders)

    print("\n" + "=" * 60)
    print("完成")
    print("=" * 60)
    print(f"有改动的角色文件夹：{len(touched_folders)}")
    print(f"移出子文件夹图片总数：{total_moved}")
    print(f"增量重命名图片总数：{total_renamed}")
    print(f"删除空子文件夹总数：{total_deleted_dirs}")
    print(f"未删除子文件夹总数：{total_not_deleted_dirs}")

    if args.apply:
        if touched_folders:
            print(f"已写入改动清单：{manifest_path}")
        else:
            print("没有实际改动，未写入改动清单。")
    else:
        print("\n当前是预览模式，没有实际修改文件。")
        print("确认无误后运行：python .\\tools\\flatten_and_rename_images.py --apply")


if __name__ == "__main__":
    main()
