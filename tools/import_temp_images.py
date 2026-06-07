from pathlib import Path
import shutil
import sys
import re
import argparse
import hashlib
from collections import defaultdict

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
NAME_NUM_PATTERN = re.compile(r"^(?P<name>.+)_(?P<num>\d+)$")
CHUNK_SIZE = 1024 * 1024


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


def parse_target_name(stem: str, folder_names: set[str]):
    if stem in folder_names:
        return stem

    m = NAME_NUM_PATTERN.match(stem)
    if m:
        name = m.group("name")
        if name in folder_names:
            return name

    return None


def parse_target_name_from_parents(src: Path, temp_dir: Path, folder_names: set[str]):
    current = src.parent
    while True:
        if current == temp_dir:
            return None
        if current.name in folder_names:
            return current.name
        if temp_dir not in current.parents:
            return None
        current = current.parent


def collect_used_numbers(char_dir: Path, char_name: str):
    used = set()
    pattern = re.compile(rf"^{re.escape(char_name)}_(\d+)$")

    for p in char_dir.iterdir():
        if not is_image_file(p):
            continue
        m = pattern.match(p.stem)
        if m:
            used.add(int(m.group(1)))

    return used


def next_available_number(used_numbers: set[int]) -> int:
    n = 1
    while n in used_numbers:
        n += 1
    return n


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def build_hash_cache_for_folder(char_dir: Path):
    hashes = set()
    for p in char_dir.iterdir():
        if is_image_file(p):
            hashes.add(file_sha256(p))
    return hashes


def delete_empty_subdirs(root: Path):
    subdirs = [p for p in root.rglob("*") if p.is_dir()]
    subdirs = sorted(subdirs, key=lambda x: (-len(x.relative_to(root).parts), str(x)))
    deleted = []
    for d in subdirs:
        try:
            d.rmdir()
            deleted.append(d)
        except OSError:
            pass
    return deleted


def main():
    parser = argparse.ArgumentParser(description="将 resource/temp 中的图片导入到对应角色文件夹，并自动跳过重复内容")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不移动文件。默认直接执行。")
    parser.add_argument("--apply", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--manifest", default=None, help="改动清单输出位置；默认写入 .git/yumemi_image_update_manifest.txt")
    parser.add_argument("--keep-temp", action="store_true", help="执行模式下导入完成后，不删除 temp 中已空的子目录。")
    parser.add_argument("--delete-duplicates", action="store_true", help="执行模式下删除已确认与目标角色图库重复的 temp 图片。")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent

    try:
        project_root = find_project_root(script_dir)
    except Exception as e:
        print(f"错误：{e}")
        sys.exit(1)

    resource_dir = project_root / "resource"
    images_dir = resource_dir / "images"
    temp_dir = resource_dir / "temp"
    manifest_path = get_manifest_path(project_root, args.manifest)

    if not temp_dir.exists():
        print(f"错误：未找到 temp 目录：{temp_dir}")
        sys.exit(1)

    char_dirs = {p.name: p for p in images_dir.iterdir() if p.is_dir()}
    folder_names = set(char_dirs.keys())

    temp_images = sorted(
        [p for p in temp_dir.rglob("*") if is_image_file(p)],
        key=lambda x: str(x.relative_to(temp_dir)).lower()
    )

    print("=" * 60)
    print(f"项目根目录：{project_root}")
    print(f"图片目录：{images_dir}")
    print(f"临时目录：{temp_dir}")
    apply_changes = args.apply or not args.dry_run

    print(f"模式：{'预览模式 (--dry-run)' if args.dry_run else '执行模式'}")
    print(f"改动清单：{manifest_path}")
    print("=" * 60)

    if not temp_images:
        print("temp 中没有找到图片文件。")
        return

    updated_folders = defaultdict(int)
    skipped_no_folder = []
    skipped_duplicate = []
    used_numbers_cache = {}
    hash_cache = {}
    total_planned = 0

    for src in temp_images:
        target_name = parse_target_name_from_parents(src, temp_dir, folder_names)
        matched_by = "父目录"

        if target_name is None:
            target_name = parse_target_name(src.stem, folder_names)
            matched_by = "文件名"

        if target_name is None:
            skipped_no_folder.append(src)
            continue

        target_dir = char_dirs[target_name]

        if target_name not in used_numbers_cache:
            used_numbers_cache[target_name] = collect_used_numbers(target_dir, target_name)
        if target_name not in hash_cache:
            hash_cache[target_name] = build_hash_cache_for_folder(target_dir)

        src_hash = file_sha256(src)
        if src_hash in hash_cache[target_name]:
            skipped_duplicate.append((src, target_name, matched_by))
            if apply_changes and args.delete_duplicates:
                src.unlink()
            continue

        used_numbers = used_numbers_cache[target_name]
        new_num = next_available_number(used_numbers)
        used_numbers.add(new_num)

        new_name = f"{target_name}_{new_num}{src.suffix.lower()}"
        dst = target_dir / new_name

        updated_folders[target_name] += 1
        total_planned += 1
        hash_cache[target_name].add(src_hash)

        if apply_changes:
            shutil.move(str(src), str(dst))

    print(f"\n可导入图片总数：{total_planned}")

    if updated_folders:
        print(f"\n[有更新的文件夹] {len(updated_folders)} 个")
        for folder_name in sorted(updated_folders):
            print(f"  {folder_name}  (+{updated_folders[folder_name]})")
    else:
        print("\n[有更新的文件夹] 无")

    if skipped_duplicate:
        print(f"\n[跳过的重复图片] {len(skipped_duplicate)} 张")
        for src, target_name, matched_by in skipped_duplicate[:50]:
            print(f"  {src.relative_to(temp_dir)}  ->  {target_name}（按{matched_by}匹配，内容重复）")
        if len(skipped_duplicate) > 50:
            print(f"  ... 共 {len(skipped_duplicate)} 张")
    else:
        print("\n[跳过的重复图片] 无")

    if skipped_no_folder:
        print(f"\n[未被执行的图片] {len(skipped_no_folder)} 张")
        for p in skipped_no_folder[:100]:
            print(f"  {p.relative_to(temp_dir)}")
        if len(skipped_no_folder) > 100:
            print(f"  ... 共 {len(skipped_no_folder)} 张")
    else:
        print("\n[未被执行的图片] 无")

    print("\n" + "=" * 60)
    if apply_changes:
        if updated_folders:
            append_manifest_entries(manifest_path, sorted(updated_folders.keys()))
            print(f"已写入改动清单：{manifest_path}")
        if args.delete_duplicates and skipped_duplicate:
            print(f"已删除重复 temp 图片：{len(skipped_duplicate)}")
        if not args.keep_temp:
            deleted_dirs = delete_empty_subdirs(temp_dir)
            print(f"已删除空 temp 子目录：{len(deleted_dirs)}")
        print("执行完成。")
    else:
        print("当前是预览模式，没有实际移动文件。")
        print("确认无误后运行：python tools/import_temp_images.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
