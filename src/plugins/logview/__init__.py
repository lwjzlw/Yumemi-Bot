import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import nonebot
from nonebot import get_driver, logger
from nonebot.adapters import Message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment
from nonebot.adapters.onebot.v11.exception import ActionFailed, ApiNotAvailable, NetworkError
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from src.utils.character_data import (
    CharacterProfile,
    get_character_profile,
    get_character_profile_from_text,
    list_character_images,
    normalize_lookup_text,
)
from src.utils.error_history import (
    describe_exception_reason,
    extract_exception_details,
    list_recent_errors,
    record_recent_error,
)

__plugin_meta__ = PluginMetadata(
    name="logview",
    description="管理员查看 bot / NapCat 日志与图片定位",
    usage="#日志 [报错|bot|napcat|全部] [行数] [角色名] [编号或文件名]",
)

DEFAULT_LOG_LINES = 60
DEFAULT_ERROR_LINES = 5
MAX_LOG_LINES = 200
TARGET_ALIASES = {
    "报错": "errors",
    "错误": "errors",
    "error": "errors",
    "errors": "errors",
    "all": "all",
    "全部": "all",
    "全部日志": "all",
    "日志": "all",
    "bot": "bot",
    "机器人": "bot",
    "napcat": "napcat",
    "qq": "napcat",
}


@dataclass(frozen=True)
class LogSource:
    key: str
    title: str
    journal_unit: str
    file_fallbacks: tuple[Path, ...] = ()


LOG_SOURCES = {
    "bot": LogSource(
        key="bot",
        title="Bot 日志",
        journal_unit="yumemi-bot.service",
    ),
    "napcat": LogSource(
        key="napcat",
        title="NapCat 日志",
        journal_unit="yumemi-napcat.service",
    ),
}

log_event = nonebot.on_command("日志", aliases={"log", "logs"}, priority=6, block=True)


def record_logview_error(
    *,
    raw_input: str,
    error: Exception,
    user_id: str = "",
    group_id: str = "",
    extra_details: dict[str, str] | None = None,
) -> None:
    details = {
        "user_id": user_id,
        "group_id": group_id,
        **extract_exception_details(error),
    }
    if extra_details:
        details.update(extra_details)
    record_recent_error(
        command="日志",
        raw_input=raw_input,
        reason=describe_exception_reason("日志", error),
        details=details,
    )


def is_admin(user_id: str) -> bool:
    return user_id in {str(item) for item in get_driver().config.superusers}


def clamp_log_lines(value: int) -> int:
    return max(1, min(value, MAX_LOG_LINES))


def split_plain_args(args_text: str) -> list[str]:
    return [token for token in args_text.strip().split() if token]


def resolve_log_target(token: str) -> str | None:
    return TARGET_ALIASES.get(normalize_lookup_text(token))


def parse_log_request(raw_text: str) -> tuple[list[str], int, str | None, str | None]:
    tokens = split_plain_args(raw_text)
    explicit_target_selected = False
    target = "errors" if not tokens else "all"
    lines = DEFAULT_ERROR_LINES if not tokens else DEFAULT_LOG_LINES

    if tokens:
        resolved_target = resolve_log_target(tokens[0])
        if resolved_target is not None:
            explicit_target_selected = True
            target = resolved_target
            tokens = tokens[1:]
            if target == "errors":
                lines = DEFAULT_ERROR_LINES

    if tokens and tokens[0].isdigit():
        lines = clamp_log_lines(int(tokens[0]))
        tokens = tokens[1:]

    character_query = None
    image_selector = None
    if len(tokens) >= 2:
        character_query = " ".join(tokens[:-1]).strip()
        image_selector = tokens[-1].strip()

    if character_query and image_selector and not explicit_target_selected:
        return [], lines, character_query, image_selector

    targets = ["bot", "napcat"] if target == "all" else [target]
    return targets, lines, character_query, image_selector


def run_command(command: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except Exception as error:
        return False, f"命令执行失败：{error!r}"

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        return False, stderr or f"命令返回了非零退出码：{result.returncode}"

    stdout = (result.stdout or "").strip()
    return True, stdout or "日志为空。"


def tail_file(path: Path, lines: int) -> tuple[bool, str]:
    if not path.is_file():
        return False, f"未找到日志文件：{path}"

    success, output = run_command(["tail", "-n", str(lines), str(path)])
    if success:
        return True, output
    return False, f"{path}\n{output}"


def get_log_output(source: LogSource, lines: int) -> str:
    journal_success, journal_output = run_command(
        ["journalctl", "--no-pager", "-n", str(lines), "-u", source.journal_unit]
    )
    if journal_success:
        return journal_output

    fallback_sections: list[str] = [
        f"journalctl 读取失败：{journal_output}",
    ]
    for file_path in source.file_fallbacks:
        file_success, file_output = tail_file(file_path, lines)
        title = f"文件回退：{file_path}"
        fallback_sections.append(f"[{title}]\n{file_output}")
        if file_success:
            return "\n\n".join(fallback_sections)

    return "\n\n".join(fallback_sections)


def resolve_character_for_log(query: str) -> CharacterProfile | None:
    profile = get_character_profile(query)
    if profile is not None:
        return profile

    normalized_query = query.strip()
    if normalized_query:
        profile = get_character_profile(normalized_query)
        if profile is not None:
            return profile

    profile = get_character_profile_from_text(query)
    if profile is not None:
        return profile

    if normalized_query:
        return get_character_profile_from_text(normalized_query)
    return None


def match_image_by_selector(profile: CharacterProfile, selector: str) -> tuple[str | None, str]:
    image_paths = list_character_images(profile.name)
    if not image_paths:
        return None, f"{profile.name} 当前没有可用本地图。"

    normalized_selector = normalize_lookup_text(selector)
    if not normalized_selector:
        return None, "图片编号或文件名不能为空。"

    if selector.isdigit():
        number = int(selector)
        expected_names = {
            normalize_lookup_text(f"{profile.name}_{number}"),
        }
        for image_path in image_paths:
            image_name = Path(image_path).stem
            if normalize_lookup_text(image_name) in expected_names:
                return image_path, f"按标准命名 `{profile.name}_{number}` 命中。"

        if 1 <= number <= len(image_paths):
            return image_paths[number - 1], f"未找到同名文件，按排序序号第 {number} 张返回。"

    exact_candidates = {normalized_selector}
    if "." in selector:
        exact_candidates.add(normalize_lookup_text(Path(selector).stem))

    for image_path in image_paths:
        image_file = Path(image_path)
        image_name = normalize_lookup_text(image_file.name)
        image_stem = normalize_lookup_text(image_file.stem)
        if image_name in exact_candidates or image_stem in exact_candidates:
            return image_path, f"按文件名 `{image_file.name}` 精确命中。"

    for image_path in image_paths:
        image_file = Path(image_path)
        normalized_name = normalize_lookup_text(image_file.name)
        normalized_stem = normalize_lookup_text(image_file.stem)
        if normalized_selector in normalized_name or normalized_selector in normalized_stem:
            return image_path, f"按文件名片段 `{selector}` 命中。"

    return None, f"没有在 {profile.name} 的图片目录里找到 `{selector}` 对应的图片。"


def format_recent_errors(lines: int) -> Message:
    recent_errors = list_recent_errors(lines)
    message = Message()
    if not recent_errors:
        message += MessageSegment.text("最近没有记录到报错。")
        return message

    message += MessageSegment.text(f"最近报错记录（最多显示 {len(recent_errors)} 条）：\n")
    for index, error in enumerate(recent_errors, start=1):
        message += MessageSegment.text(
            f"\n[{index}] 时间：{error.get('timestamp', '未知')}\n"
            f"指令：{error.get('command', '未知')}\n"
            f"输入：{error.get('raw_input', '') or '无'}\n"
            f"原因：{error.get('reason', '未知错误')}\n"
        )
        details = error.get("details", {})
        if isinstance(details, dict):
            for key, value in details.items():
                if value:
                    message += MessageSegment.text(f"{key}：{value}\n")
    return message


def build_forward_node(content: str | Message) -> MessageSegment:
    return MessageSegment.node_custom(
        user_id=os.getenv("QQ_NUMBER"),
        nickname=os.getenv("QQ_ID"),
        content=content,
    )


@log_event.handle()
async def _(event: GroupMessageEvent, args: Message = CommandArg()):
    user_id = str(event.get_user_id())
    group_id = str(event.group_id)
    if not is_admin(user_id):
        await log_event.finish("Permission denied.")

    raw_text = args.extract_plain_text().strip()
    targets, lines, character_query, image_selector = parse_log_request(raw_text)

    forward_nodes: list[MessageSegment] = []
    if targets or not (character_query and image_selector):
        summary = Message()
        if targets == ["errors"]:
            summary += MessageSegment.text(f"查看范围：最近报错\n显示条数：{lines}")
        elif targets:
            summary += MessageSegment.text(
                f"日志范围：{', '.join(targets)}\n"
                f"日志行数：{lines}"
            )
        if character_query and image_selector:
            summary += MessageSegment.text(f"\n图片定位：{character_query} / {image_selector}")
        forward_nodes.append(build_forward_node(summary))

    for target in targets:
        content = Message()
        if target == "errors":
            content += format_recent_errors(lines)
        else:
            source = LOG_SOURCES[target]
            log_output = get_log_output(source, lines)
            content += MessageSegment.text(f"[{source.title}]\n{log_output}")
        forward_nodes.append(build_forward_node(content))

    if character_query and image_selector:
        profile = resolve_character_for_log(character_query)
        image_message = Message()
        if profile is None:
            image_message += MessageSegment.text(f"没有识别到角色：{character_query}")
        else:
            image_path, reason = match_image_by_selector(profile, image_selector)
            display_name = profile.name
            if profile.matched_name and profile.matched_name != profile.name:
                display_name = f"{profile.name}（{profile.matched_name}）"
            image_message += MessageSegment.text(
                f"[图片定位]\n角色：{display_name}\n选择：{image_selector}\n{reason}"
            )
            if image_path is not None:
                image_message += MessageSegment.text(f"\n路径：{image_path}\n")
                image_message += MessageSegment.image(image_path)
                logger.info(
                    "LogView image resolved: "
                    f"user_id={user_id}, character={profile.name}, selector={image_selector}, image_path={image_path}"
                )
        forward_nodes.append(build_forward_node(image_message))

    try:
        await log_event.finish(forward_nodes)
    except (ActionFailed, ApiNotAvailable, NetworkError) as error:
        logger.warning(
            "LogView send failed: "
            f"user_id={user_id}, group_id={group_id}, raw_text={raw_text}, error={repr(error)}"
        )
        record_logview_error(
            raw_input=raw_text,
            error=error,
            user_id=user_id,
            group_id=group_id,
            extra_details={"targets": ",".join(targets) or "image_only"},
        )
        await log_event.finish("日志发送失败了，梦美已经把这次报错记下来了。")
