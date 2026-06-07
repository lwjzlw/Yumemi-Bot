# make_image_folders.py
from pathlib import Path
import json
import sys


def find_project_root(start: Path) -> Path:
    """
    从脚本所在目录开始，逐级向上寻找包含 resource/character_data.json 的项目根目录
    """
    for path in [start, *start.parents]:
        json_path = path / "resource" / "character_data.json"
        if json_path.exists():
            return path
    raise FileNotFoundError("未找到 resource/character_data.json，请确认脚本位于 Yumemi-Bot 项目目录内。")


def main():
    script_dir = Path(__file__).resolve().parent

    try:
        project_root = find_project_root(script_dir)
    except FileNotFoundError as e:
        print(e)
        sys.exit(1)

    resource_dir = project_root / "resource"
    json_path = resource_dir / "character_data.json"
    images_dir = resource_dir / "images"

    # 兼容 UTF-8 BOM
    with open(json_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        print("character_data.json 顶层不是 dict，请检查格式。")
        sys.exit(1)

    images_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    existed = 0
    skipped = 0

    for name in data.keys():
        folder_name = str(name).strip()

        if not folder_name:
            skipped += 1
            continue

        folder_path = images_dir / folder_name

        if folder_path.exists():
            existed += 1
        else:
            folder_path.mkdir(parents=True, exist_ok=True)
            created += 1
            print(f"[新建] {folder_path}")

    print("\n完成。")
    print(f"项目根目录：{project_root}")
    print(f"角色总数：{len(data)}")
    print(f"新建文件夹：{created}")
    print(f"已存在文件夹：{existed}")
    print(f"跳过空名称：{skipped}")
    print(f"图片目录：{images_dir}")


if __name__ == "__main__":
    main()