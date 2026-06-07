from pathlib import Path
import random
import sys

TARGET_FILES = [
    "heroine.txt",
    "littlethings.txt",
    "luckythings.txt",
]


def find_project_root(start: Path) -> Path:
    """
    从脚本所在目录开始，逐级向上寻找 Yumemi-Bot 项目根目录
    """
    for path in [start, *start.parents]:
        target_dir = path / "src" / "plugins" / "KeyProphecy" / "resource"
        if target_dir.exists():
            return path
    raise FileNotFoundError("未找到 src/plugins/KeyProphecy/resource，请确认脚本位于 Yumemi-Bot 项目目录内。")


def detect_newline(text: str) -> str:
    """
    检测原文件主要换行符
    """
    if "\r\n" in text:
        return "\r\n"
    if "\n" in text:
        return "\n"
    if "\r" in text:
        return "\r"
    return "\n"


def shuffle_txt_file(file_path: Path):
    raw = file_path.read_bytes()

    # 检测 UTF-8 BOM
    has_bom = raw.startswith(b"\xef\xbb\xbf")

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise UnicodeDecodeError(
            "utf-8", raw, 0, 1,
            f"{file_path} 不是 UTF-8/UTF-8-BOM 编码，请先确认编码。"
        )

    newline = detect_newline(text)
    ended_with_newline = text.endswith(("\r\n", "\n", "\r"))

    # splitlines() 不会凭空制造空行；原本的空行会作为空字符串保留下来
    lines = text.splitlines()

    # 生成备份
    backup_path = file_path.with_suffix(file_path.suffix + ".bak")
    backup_path.write_bytes(raw)

    # 打乱顺序
    random.shuffle(lines)

    # 重新拼接，保持行数与空行结构，不额外增加空行
    new_text = newline.join(lines)
    if ended_with_newline and lines:
        new_text += newline

    # 写回，保留是否有 BOM
    new_raw = new_text.encode("utf-8")
    if has_bom:
        new_raw = b"\xef\xbb\xbf" + new_raw

    file_path.write_bytes(new_raw)

    return len(lines), backup_path.name


def main():
    script_dir = Path(__file__).resolve().parent

    try:
        project_root = find_project_root(script_dir)
    except Exception as e:
        print(f"错误：{e}")
        sys.exit(1)

    resource_dir = project_root / "src" / "plugins" / "KeyProphecy" / "resource"

    print(f"项目根目录：{project_root}")
    print(f"目标目录：{resource_dir}")
    print()

    for name in TARGET_FILES:
        file_path = resource_dir / name
        if not file_path.exists():
            print(f"[跳过] 未找到文件：{file_path}")
            continue

        try:
            line_count, backup_name = shuffle_txt_file(file_path)
            print(f"[完成] {name}  已打乱，共 {line_count} 行，备份：{backup_name}")
        except Exception as e:
            print(f"[失败] {name}  ->  {e}")

    print("\n全部处理结束。")


if __name__ == "__main__":
    main()