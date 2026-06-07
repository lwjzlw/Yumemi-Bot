from pathlib import Path
import json
import sys
import csv
import argparse

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
DEFAULT_SMALL_IMAGE_THRESHOLD_BYTES = 100 * 1024


def find_project_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        json_path = path / "resource" / "character_data.json"
        if json_path.exists():
            return path
    raise FileNotFoundError("未找到 resource/character_data.json，请确认脚本位于 Yumemi-Bot 项目目录内。")


def load_character_names(json_path: Path):
    with open(json_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("character_data.json 顶层不是 dict，请检查格式。")

    names = [str(k).strip() for k in data.keys() if str(k).strip()]
    return sorted(names)


def load_name_list(txt_path: Path):
    if not txt_path.exists():
        return set()

    with open(txt_path, "r", encoding="utf-8-sig") as f:
        names = {line.strip() for line in f if line.strip()}
    return names


def count_images_in_folder(folder: Path) -> int:
    count = 0
    for p in folder.iterdir():
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            count += 1
    return count


def iter_image_files(folder: Path):
    for p in folder.iterdir():
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            yield p


def format_kb(size_bytes: int) -> str:
    return f"{size_bytes / 1024:.1f} KB"


def main():
    parser = argparse.ArgumentParser(description="检查 Yumemi-Bot 图片文件夹完整性，并生成报告/CSV")
    parser.add_argument("--heroine-min", type=int, default=5, help="heroine 至少应有多少张图；少于该值时报告。默认 5。")
    parser.add_argument("--other-min", type=int, default=1, help="普通角色至少应有多少张图；少于该值时报告。默认 1，即只报告 0 张。")
    parser.add_argument("--small-kb", type=int, default=100, help="把小于多少 KB 的图片列入小图检查。默认 100。")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent

    try:
        project_root = find_project_root(script_dir)
    except Exception as e:
        print(f"错误：{e}")
        sys.exit(1)

    resource_dir = project_root / "resource"
    json_path = resource_dir / "character_data.json"
    images_dir = resource_dir / "images"

    keyprophecy_resource_dir = project_root / "src" / "plugins" / "KeyProphecy" / "resource"
    heroine_txt_path = keyprophecy_resource_dir / "heroine.txt"

    report_path = resource_dir / "image_folder_check_report.txt"
    csv_path = resource_dir / "image_folder_image_count.csv"
    small_csv_path = resource_dir / "image_small_files.csv"
    small_threshold_bytes = args.small_kb * 1024

    if not images_dir.exists():
        print(f"错误：图片目录不存在：{images_dir}")
        sys.exit(1)

    try:
        character_names = load_character_names(json_path)
    except Exception as e:
        print(f"读取 JSON 失败：{e}")
        sys.exit(1)

    heroine_names = load_name_list(heroine_txt_path)
    character_set = set(character_names)

    image_dirs = sorted([p for p in images_dir.iterdir() if p.is_dir()], key=lambda x: x.name)
    folder_names = [p.name for p in image_dirs]
    folder_set = set(folder_names)

    missing_folders = sorted(character_set - folder_set)
    extra_folders = sorted(folder_set - character_set)

    loose_files = sorted(
        [p.name for p in images_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    )

    folder_count_rows = []
    empty_folders = []
    need_attention_rows = []
    small_images = []

    for folder in image_dirs:
        img_count = count_images_in_folder(folder)
        is_heroine = folder.name in heroine_names
        min_required = args.heroine_min if is_heroine else args.other_min
        flagged = img_count < min_required

        if is_heroine:
            mark = f"⚠ heroine<{args.heroine_min}" if flagged else ""
        else:
            mark = f"⚠ other<{args.other_min}" if flagged else ""

        folder_count_rows.append((
            folder.name,
            img_count,
            "是" if is_heroine else "否",
            min_required,
            mark,
        ))

        if img_count == 0:
            empty_folders.append(folder.name)

        if flagged:
            need_attention_rows.append((folder.name, img_count, is_heroine, min_required))

        for img_file in iter_image_files(folder):
            size_bytes = img_file.stat().st_size
            if size_bytes < small_threshold_bytes:
                small_images.append((
                    folder.name,
                    img_file.name,
                    size_bytes,
                    f"{folder.name}/{img_file.name}",
                ))

    folder_count_rows_sorted = sorted(folder_count_rows, key=lambda x: (x[1], x[0]))
    need_attention_rows_sorted = sorted(need_attention_rows, key=lambda x: (x[1], x[0]))
    small_images_sorted = sorted(small_images, key=lambda x: (x[2], x[3].lower()))

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["文件夹名", "图片数", "是否heroine", "最少要求", "标记"])
        for row in folder_count_rows_sorted:
            writer.writerow(row)

    with open(small_csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["文件夹名", "图片文件名", "大小(bytes)", "大小", "相对路径"])
        for folder_name, file_name, size_bytes, rel_path in small_images_sorted:
            writer.writerow([folder_name, file_name, size_bytes, format_kb(size_bytes), rel_path])

    lines = []
    lines.append("Yumemi-Bot 图片库检查报告")
    lines.append("=" * 56)
    lines.append(f"项目根目录：{project_root}")
    lines.append(f"JSON 文件：{json_path}")
    lines.append(f"图片目录：{images_dir}")
    lines.append(f"heroine 列表：{heroine_txt_path}")
    lines.append(f"heroine 最少图片数：{args.heroine_min}")
    lines.append(f"普通角色最少图片数：{args.other_min}")
    lines.append(f"小图阈值：{args.small_kb} KB")
    lines.append("")
    lines.append(f"角色总数（character_data.json）：{len(character_names)}")
    lines.append(f"heroine 名单数：{len(heroine_names)}")
    lines.append(f"图片文件夹总数（images 一级子目录）：{len(image_dirs)}")
    lines.append(f"生成表格：{csv_path.name}")
    lines.append(f"小图表格：{small_csv_path.name}")
    lines.append("")

    lines.append("[一] JSON 中有，但缺少对应文件夹的角色")
    lines.extend(missing_folders if missing_folders else ["无"])
    lines.append("")

    lines.append("[二] images 中多出来的文件夹（不在 JSON 中）")
    lines.extend(extra_folders if extra_folders else ["无"])
    lines.append("")

    lines.append("[三] 空图片文件夹（图片数 = 0）")
    lines.extend(empty_folders if empty_folders else ["无"])
    lines.append("")

    lines.append("[四] 需要补图的文件夹")
    lines.append(f"规则：heroine 少于 {args.heroine_min} 张报告；普通角色少于 {args.other_min} 张报告。")
    if need_attention_rows_sorted:
        for name, count, is_heroine, min_required in need_attention_rows_sorted:
            tag = f"heroine<{min_required}" if is_heroine else f"other<{min_required}"
            lines.append(f"{name}\t{count}\t{tag}")
    else:
        lines.append("无")
    lines.append("")

    lines.append("[五] images 根目录下的散落图片文件")
    lines.extend(loose_files if loose_files else ["无"])
    lines.append("")

    lines.append(f"[六] 小于 {args.small_kb} KB 的图片")
    if small_images_sorted:
        for folder_name, file_name, size_bytes, rel_path in small_images_sorted:
            lines.append(f"{rel_path}\t{format_kb(size_bytes)}")
    else:
        lines.append("无")
    lines.append("")

    lines.append("[七] 全部文件夹图片数一览（按图片数升序）")
    for name, count, is_heroine_text, min_required, mark in folder_count_rows_sorted:
        if mark:
            lines.append(f"{name}\t{count}\t{is_heroine_text}\t最少={min_required}\t{mark}")
        else:
            lines.append(f"{name}\t{count}\t{is_heroine_text}\t最少={min_required}")

    with open(report_path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines))

    print("=" * 56)
    print("检查完成")
    print("=" * 56)
    print(f"项目根目录：{project_root}")
    print(f"heroine 最少图片数：{args.heroine_min}")
    print(f"普通角色最少图片数：{args.other_min}")
    print(f"小图阈值：{args.small_kb} KB")
    print(f"角色总数：{len(character_names)}")
    print(f"heroine 名单数：{len(heroine_names)}")
    print(f"图片文件夹总数：{len(image_dirs)}")
    print(f"缺少文件夹：{len(missing_folders)}")
    print(f"多余文件夹：{len(extra_folders)}")
    print(f"空文件夹：{len(empty_folders)}")
    print(f"需要补图的文件夹：{len(need_attention_rows_sorted)}")
    print(f"小于 {args.small_kb} KB 的图片：{len(small_images_sorted)}")
    print(f"散落图片文件：{len(loose_files)}")
    print("")
    print(f"报告文件：{report_path}")
    print(f"计数表格：{csv_path}")
    print(f"小图表格：{small_csv_path}")


if __name__ == "__main__":
    main()
