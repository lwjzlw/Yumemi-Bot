from pathlib import Path
import argparse
import hashlib
import re
import shutil
import sys
import uuid
from datetime import datetime

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
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
        existing = {line.strip() for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()}
    manifest_path.write_text("\n".join(sorted(existing | set(entries))) + "\n", encoding="utf-8")


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTS


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def collect_images(char_dir: Path, recursive: bool) -> list[Path]:
    iterator = char_dir.rglob("*") if recursive else char_dir.iterdir()
    return sorted((p for p in iterator if is_image_file(p)), key=lambda p: str(p.relative_to(char_dir)).lower())


def numeric_key(path: Path, char_name: str) -> tuple[int, int | str, str]:
    match = re.fullmatch(rf"{re.escape(char_name)}_(\d+)", path.stem)
    if match:
        return (0, int(match.group(1)), path.suffix.lower())
    return (1, path.name.lower(), path.suffix.lower())


def image_number(path: Path, char_name: str) -> int | None:
    match = re.fullmatch(rf"{re.escape(char_name)}_(\d+)", path.stem)
    if match and path.parent.name == char_name:
        return int(match.group(1))
    return None


def delete_empty_subdirs(root: Path) -> int:
    deleted = 0
    subdirs = sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: (-len(p.relative_to(root).parts), str(p)))
    for path in subdirs:
        try:
            path.rmdir()
            deleted += 1
        except OSError:
            pass
    return deleted


def unique_backup_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    index = 2
    while True:
        candidate = path.with_name(f"{stem}__{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def backup_duplicates(project_root: Path, duplicates: list[tuple[Path, Path]]) -> tuple[Path | None, int]:
    if not duplicates:
        return None, 0
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = project_root / "resource" / "temp" / f"_dedupe_backup_{stamp}"
    copied = 0
    report_lines = [
        "dedupe backup",
        "duplicate 文件会从正式图库删除；original 文件保留在正式图库。",
        "",
    ]
    for duplicate, original in duplicates:
        char_name = duplicate.parent.name
        char_dir = backup_root / char_name
        char_dir.mkdir(parents=True, exist_ok=True)
        duplicate_out = unique_backup_path(char_dir / f"duplicate__{duplicate.name}")
        original_out = unique_backup_path(char_dir / f"original__{original.name}")
        shutil.copy2(duplicate, duplicate_out)
        if original.exists():
            shutil.copy2(original, original_out)
        copied += 1
        report_lines.append(f"{char_name}: {duplicate.name} == {original.name}")
    (backup_root / "README.txt").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return backup_root, copied


def build_plan(char_dir: Path, recursive: bool, dedupe: bool):
    char_name = char_dir.name
    image_files = collect_images(char_dir, recursive)
    seen_hashes: dict[str, Path] = {}
    kept: list[Path] = []
    duplicates: list[tuple[Path, Path]] = []

    for path in sorted(image_files, key=lambda p: numeric_key(p, char_name)):
        if dedupe:
            digest = file_sha256(path)
            if digest in seen_hashes:
                duplicates.append((path, seen_hashes[digest]))
                continue
            seen_hashes[digest] = path
        kept.append(path)

    renames: list[tuple[Path, Path]] = []
    numbered: dict[int, Path] = {}
    pending: list[Path] = []
    for path in kept:
        number = image_number(path, char_name)
        if number is None or number in numbered:
            pending.append(path)
        else:
            numbered[number] = path

    planned_numbers = set(numbered)
    next_append = max(planned_numbers, default=0) + 1

    # 非规范命名或子目录图片追加到末尾，不扰动现有编号。
    for path in sorted(pending, key=lambda p: numeric_key(p, char_name)):
        while next_append in planned_numbers:
            next_append += 1
        target = char_dir / f"{char_name}_{next_append}{path.suffix.lower()}"
        if path != target:
            renames.append((path, target))
        planned_numbers.add(next_append)
        next_append += 1

    # 补编号空洞时，只移动末尾图片填洞，避免把空洞后的所有文件整体前移。
    if planned_numbers:
        missing_numbers = [n for n in range(1, max(planned_numbers) + 1) if n not in planned_numbers]
        available_tail_numbers = sorted((n for n in planned_numbers if n > 0), reverse=True)
        for missing in missing_numbers:
            tail = next((n for n in available_tail_numbers if n > missing), None)
            if tail is None:
                break
            src = numbered.get(tail)
            if src is None:
                continue
            target = char_dir / f"{char_name}_{missing}{src.suffix.lower()}"
            if src != target:
                renames.append((src, target))
            planned_numbers.remove(tail)
            planned_numbers.add(missing)
            available_tail_numbers.remove(tail)
            numbered[missing] = src
            numbered.pop(tail, None)

    return kept, duplicates, renames


def apply_plan(char_dir: Path, duplicates: list[tuple[Path, Path]], renames: list[tuple[Path, Path]], recursive: bool):
    for duplicate, _original in duplicates:
        duplicate.unlink()

    temp_moves: list[tuple[Path, Path, Path]] = []
    occupied = {p.name for p in char_dir.iterdir() if p.is_file()}
    for src, dst in renames:
        tmp = char_dir / f"__normalize__{uuid.uuid4().hex}{src.suffix.lower()}"
        while tmp.exists() or tmp.name in occupied:
            tmp = char_dir / f"__normalize__{uuid.uuid4().hex}{src.suffix.lower()}"
        src.rename(tmp)
        temp_moves.append((tmp, src, dst))
        occupied.discard(src.name)
        occupied.add(tmp.name)

    for tmp, _src, dst in temp_moves:
        if dst.exists():
            raise FileExistsError(f"目标文件已存在，无法覆盖：{dst}")
        tmp.rename(dst)

    deleted_dirs = delete_empty_subdirs(char_dir) if recursive else 0
    return deleted_dirs


def main():
    parser = argparse.ArgumentParser(description="规范化 resource/images 下角色图片命名为 角色名_n.ext，可重排编号空洞。")
    parser.add_argument("--apply", action="store_true", help="真正执行修改。默认仅预览。")
    parser.add_argument("--only", nargs="*", default=None, help="只处理指定角色文件夹名，可写多个。")
    parser.add_argument("--recursive", action="store_true", help="递归吸收角色目录子文件夹中的图片。")
    parser.add_argument("--dedupe", action="store_true", help="按 SHA256 删除同一角色目录内重复图片。")
    parser.add_argument("--manifest", default=None, help="改动清单输出位置；默认写入 .git/yumemi_image_update_manifest.txt")
    args = parser.parse_args()

    try:
        project_root = find_project_root(Path(__file__).resolve().parent)
    except Exception as exc:
        print(f"错误：{exc}")
        sys.exit(1)

    images_dir = project_root / "resource" / "images"
    manifest_path = get_manifest_path(project_root, args.manifest)
    char_dirs = sorted((p for p in images_dir.iterdir() if p.is_dir()), key=lambda p: p.name)

    if args.only:
        only_set = set(args.only)
        existing = {p.name for p in char_dirs}
        missing = sorted(only_set - existing)
        if missing:
            print("以下指定文件夹不存在：")
            for name in missing:
                print(f"  {name}")
        char_dirs = [p for p in char_dirs if p.name in only_set]

    print("=" * 60)
    print(f"项目根目录：{project_root}")
    print(f"图片目录：{images_dir}")
    print(f"模式：{'执行模式 (--apply)' if args.apply else '预览模式'}")
    print(f"递归吸收子目录：{'是' if args.recursive else '否'}")
    print(f"删除重复图片：{'是' if args.dedupe else '否'}")
    print(f"改动清单：{manifest_path}")
    print("=" * 60)

    touched: list[str] = []
    total_duplicates = 0
    total_renames = 0
    total_deleted_dirs = 0
    all_duplicates: list[tuple[Path, Path]] = []

    for char_dir in char_dirs:
        kept, duplicates, renames = build_plan(char_dir, args.recursive, args.dedupe)
        if not duplicates and not renames:
            continue

        touched.append(char_dir.name)
        total_duplicates += len(duplicates)
        total_renames += len(renames)
        all_duplicates.extend(duplicates)

        print(f"\n[{char_dir.name}]")
        print(f"  保留图片：{len(kept)}")
        print(f"  删除重复：{len(duplicates)}")
        print(f"  规范命名：{len(renames)}")

        for duplicate, original in duplicates[:10]:
            print(f"    duplicate: {duplicate.relative_to(char_dir)} == {original.relative_to(char_dir)}")
        if len(duplicates) > 10:
            print(f"    ... 共 {len(duplicates)} 张重复图")

        for src, dst in renames[:20]:
            print(f"    rename: {src.relative_to(char_dir)} -> {dst.name}")
        if len(renames) > 20:
            print(f"    ... 共 {len(renames)} 个重命名")

        if args.apply:
            plan_duplicates = duplicates if args.dedupe else []
            if args.dedupe and duplicates:
                backup_root, copied = backup_duplicates(project_root, duplicates)
                if backup_root:
                    print(f"  重复图备份：{backup_root}")
                    print(f"  已备份重复图组：{copied}")
            deleted_dirs = apply_plan(char_dir, plan_duplicates, renames, args.recursive)
            total_deleted_dirs += deleted_dirs
            if deleted_dirs:
                print(f"  删除空子目录：{deleted_dirs}")

    if args.apply and touched:
        append_manifest_entries(manifest_path, touched)

    print("\n" + "=" * 60)
    print("完成")
    print("=" * 60)
    print(f"有改动的角色文件夹：{len(touched)}")
    print(f"删除重复图片总数：{total_duplicates}")
    print(f"规范命名总数：{total_renames}")
    print(f"删除空子目录总数：{total_deleted_dirs}")
    if args.apply:
        if touched:
            print(f"已写入改动清单：{manifest_path}")
        else:
            print("没有实际改动，未写入改动清单。")
    else:
        print("当前是预览模式，没有实际修改文件。")
        print("确认无误后运行：python tools/normalize_image_names.py --apply")


if __name__ == "__main__":
    main()
