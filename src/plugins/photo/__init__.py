import os
import random
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
import json
import ast
import math

import nonebot
from nonebot import get_driver, get_plugin_config, logger
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message,
    MessageSegment,
)
from nonebot.adapters.onebot.v11.exception import ActionFailed, ApiNotAvailable, NetworkError
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata

from src.utils.character_data import (
    CharacterProfile,
    get_character_profile,
    get_character_profile_from_text,
    load_character_data,
    load_image_index,
    list_character_images,
    normalize_lookup_text,
    warmup_character_resource_cache,
)
from src.utils.error_history import (
    describe_exception_reason,
    extract_exception_details,
    record_recent_error,
)
from src.utils.paths import GAME_ALIAS_PATH

from .config import PluginConfig

__plugin_meta__ = PluginMetadata(
    name="photo",
    description="本地图库随机返图",
    usage="支持 #图片 / #涩图 角色名 [数量]",
    config=PluginConfig,
)

config = get_plugin_config(PluginConfig)
PHOTO_SEND_TIMEOUT = 45.0
PHOTO_MAX_COUNT = 9
PHOTO_RATE_LIMIT = 3
PHOTO_RATE_WINDOW_SECONDS = 3600
PHOTO_PERMISSION_UNLIMITED = 0
PHOTO_PERMISSION_LIMITED = 1
PHOTO_PERMISSION_DISABLED = 2

photo_usage_records: dict[str, deque[tuple[float, int]]] = defaultdict(deque)
RANDOM_QUERY_ALIASES = {"随机", "random", "rand", "随便"}


def positive_config_int(name: str, default: int) -> int:
    try:
        value = int(getattr(config, name, default) or default)
    except (TypeError, ValueError):
        return default
    return max(1, value)


def photo_max_count() -> int:
    return positive_config_int("photo_max_count", PHOTO_MAX_COUNT)


def photo_rate_limit() -> int:
    return positive_config_int("photo_rate_limit", PHOTO_RATE_LIMIT)


def photo_single_request_limit() -> int:
    return positive_config_int("photo_single_request_limit", photo_rate_limit())


@dataclass(frozen=True)
class PhotoSelection:
    title_line: str
    image_files: list[str]
    requested_count: int
    count: int


warmup_stats = warmup_character_resource_cache(
    json_path=config.character_json_path,
    image_base_folder=config.image_base_folder,
)
logger.info(
    "Photo resource cache warmed up: "
    f"{int(warmup_stats['image_character_count'])} image folders, "
    f"{warmup_stats['total_ms']} ms total"
)


def load_game_aliases() -> dict[str, tuple[str, ...]]:
    if not GAME_ALIAS_PATH.is_file():
        return {}
    with open(GAME_ALIAS_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)
    aliases: dict[str, tuple[str, ...]] = {}
    for canonical_name, alias_list in data.items():
        if not isinstance(alias_list, list):
            continue
        aliases[canonical_name] = tuple(str(alias) for alias in alias_list if str(alias).strip())
    return aliases


def build_game_image_index() -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    character_data = load_character_data(config.character_json_path)
    image_index = load_image_index(config.image_base_folder)
    game_images: dict[str, list[str]] = defaultdict(list)
    all_images: list[str] = []

    for character_name, info in character_data.items():
        image_paths = list(image_index.get(character_name, ()))
        if not image_paths:
            continue
        game_name = str(info.get("game_name", "")).strip()
        if game_name:
            game_images[game_name].extend(image_paths)
        all_images.extend(image_paths)

    normalized_game_images = {
        game_name: tuple(sorted(dict.fromkeys(image_paths)))
        for game_name, image_paths in game_images.items()
    }
    normalized_all_images = tuple(sorted(dict.fromkeys(all_images)))
    return normalized_game_images, normalized_all_images


GAME_ALIASES = load_game_aliases()
GAME_IMAGE_INDEX, ALL_IMAGE_PATHS = build_game_image_index()


def is_probable_napcat_send_timeout(error: ActionFailed) -> bool:
    return getattr(error, "retcode", None) == 1200 and "Timeout:" in str(error)


def resolve_explicit_permission(target_id: str, unlimited_ids: set[str], limited_ids: set[str], disabled_ids: set[str]) -> int | None:
    if target_id in disabled_ids:
        return PHOTO_PERMISSION_DISABLED
    if target_id in unlimited_ids:
        return PHOTO_PERMISSION_UNLIMITED
    if target_id in limited_ids:
        return PHOTO_PERMISSION_LIMITED
    return None


def get_default_permission() -> int:
    return PHOTO_PERMISSION_LIMITED


def resolve_photo_permission(user_id: str, group_id: str | None) -> int:
    admin_users = {str(user_id) for user_id in get_driver().config.superusers}
    admin_users.update(str(user_id) for user_id in config.photo_superusers)
    if user_id in admin_users:
        return PHOTO_PERMISSION_UNLIMITED

    unlimited_users = {str(user_id) for user_id in config.photo_unlimited_users}
    limited_users = {str(user_id) for user_id in config.photo_rate_limited_users}
    disabled_users = {str(user_id) for user_id in config.photo_disabled_users}

    unlimited_groups = {str(group_id) for group_id in config.photo_unlimited_groups}
    limited_groups = {str(group_id) for group_id in config.photo_rate_limited_groups}
    disabled_groups = {str(group_id) for group_id in config.photo_disabled_groups}
    allowed_users = {str(user_id) for user_id in config.photo_allowed_users}
    allowed_groups = {str(group_id) for group_id in config.photo_allowed_groups}

    if user_id in disabled_users:
        return PHOTO_PERMISSION_DISABLED
    if group_id is not None and group_id in disabled_groups:
        return PHOTO_PERMISSION_DISABLED

    if config.photo_restricted_mode:
        in_allowed_scope = user_id in allowed_users or (group_id is not None and group_id in allowed_groups)
        if not in_allowed_scope:
            return PHOTO_PERMISSION_DISABLED

    explicit_permissions: list[int] = []

    user_permission = resolve_explicit_permission(user_id, unlimited_users, limited_users, disabled_users)
    if user_permission is not None:
        explicit_permissions.append(user_permission)

    if group_id is not None:
        group_permission = resolve_explicit_permission(group_id, unlimited_groups, limited_groups, disabled_groups)
        if group_permission is not None:
            explicit_permissions.append(group_permission)

    if PHOTO_PERMISSION_DISABLED in explicit_permissions:
        return PHOTO_PERMISSION_DISABLED
    if PHOTO_PERMISSION_UNLIMITED in explicit_permissions:
        return PHOTO_PERMISSION_UNLIMITED
    if PHOTO_PERMISSION_LIMITED in explicit_permissions:
        return PHOTO_PERMISSION_LIMITED
    return get_default_permission()


def prune_photo_usage_records(user_id: str) -> deque[tuple[float, int]]:
    now = time.time()
    records = photo_usage_records[user_id]
    while records and now - records[0][0] >= PHOTO_RATE_WINDOW_SECONDS:
        records.popleft()
    return records


def get_photo_quota_state(user_id: str) -> tuple[int, int]:
    records = prune_photo_usage_records(user_id)
    used = sum(count for _, count in records)
    remaining = max(0, photo_rate_limit() - used)
    return used, remaining


def consume_photo_quota(user_id: str, count: int) -> None:
    prune_photo_usage_records(user_id)
    photo_usage_records[user_id].append((time.time(), count))


def format_rate_limit_message(user_id: str) -> str:
    records = prune_photo_usage_records(user_id)
    _, remaining = get_photo_quota_state(user_id)
    if not records:
        return "梦美这里暂时有点忙，稍后再试试看吧。"

    next_release_seconds = max(1, int(PHOTO_RATE_WINDOW_SECONDS - (time.time() - records[0][0])))
    next_release_minutes = max(1, (next_release_seconds + 59) // 60)
    if remaining <= 0:
        return f"梦美这边每小时最多只能给你发 {photo_rate_limit()} 张图哦。你这小时已经看满了，约 {next_release_minutes} 分钟后再来吧。"
    return (
        f"你每小时最多只能讨要 {photo_rate_limit()} 张图哦。"
        f"现在还剩 {remaining} 张额度。"
    )


def format_user_send_failure_message(error: Exception) -> str:
    reason = describe_exception_reason("发送图片", error)
    if "拦截" in reason:
        return "图片被 QQ 或平台侧拦住了，梦美已经把报错记下来了。这次不扣额度。"
    if "接口返回失败" in reason:
        return "图片发送接口返回失败了，梦美已经把报错记下来了。这次不扣额度。"
    if isinstance(error, (ApiNotAvailable, NetworkError)):
        return "图片发送时网络有点不稳定，梦美已经把报错记下来了。这次不扣额度。"
    return "图片发送失败了，梦美先把这次报错记下来了。这次不扣额度。"


def format_title_line(query: str, standard_name: str, matched_name: str | None, game_name: str) -> str:
    normalized_query = normalize_lookup_text(query)
    normalized_standard_name = normalize_lookup_text(standard_name)
    normalized_matched_name = normalize_lookup_text(matched_name or "")

    title = f"{game_name} - {standard_name}" if game_name else standard_name
    if not matched_name:
        return title
    if normalized_query == normalized_standard_name:
        return title
    if normalized_matched_name and normalized_query == normalized_matched_name and matched_name != standard_name:
        return f"{title}（{matched_name}）"
    if matched_name != standard_name:
        return f"{title}（{query} -> {matched_name}）"
    return f"{title}（{query}）"


def format_collection_title(label: str, count: int) -> str:
    if count > 1:
        return f"{label} × {count}"
    return label


def evaluate_simple_count_expression(expression: str) -> int | None:
    normalized_expression = expression.strip().replace("x", "*").replace("X", "*")
    if not normalized_expression or not re.fullmatch(r"[\d\s+\-*/().]+", normalized_expression):
        return None

    try:
        parsed = ast.parse(normalized_expression, mode="eval")
    except SyntaxError:
        return None

    def eval_node(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return eval_node(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left = eval_node(node.left)
            right = eval_node(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if right == 0:
                raise ZeroDivisionError
            return left / right
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = eval_node(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        raise ValueError("unsupported expression")

    try:
        result = eval_node(parsed)
    except (ValueError, ZeroDivisionError):
        return None

    if not math.isfinite(result):
        return None
    return math.floor(result)


def extract_count(raw_text: str) -> tuple[int, int, str]:
    requested_count = 1
    text = raw_text
    match = re.search(r"(?<!\d)(\d{1,2})\s*(?:张|个|只|幅|p|P)?(?!\d)", raw_text)
    if match:
        requested_count = int(match.group(1))
        text = (raw_text[: match.start()] + " " + raw_text[match.end() :]).strip()
    sanitized_count = max(1, min(requested_count, photo_max_count()))
    return requested_count, sanitized_count, text


def extract_trailing_count(raw_text: str) -> tuple[int, int, str] | None:
    stripped_text = raw_text.strip()
    if not stripped_text:
        return None

    half_match = re.search(r"(?P<count>(?:half)|半)\s*(?:张|个|只|幅|p|P)?\s*$", stripped_text, flags=re.IGNORECASE)
    if half_match:
        text = stripped_text[: half_match.start("count")].strip()
        return 0, 1, text

    unit_match = re.search(r"(?P<count>\d{1,2})\s*(?:张|个|只|幅|p|P)\s*$", stripped_text)
    if unit_match:
        requested_count = int(unit_match.group("count"))
        text = stripped_text[: unit_match.start("count")].strip()
        return requested_count, max(1, min(requested_count, photo_max_count())), text

    trailing_expression_match = re.search(r"(?P<expr>\d[\d\s+\-*/().xX]{0,19})\s*$", stripped_text)
    if trailing_expression_match:
        parsed_count = evaluate_simple_count_expression(trailing_expression_match.group("expr"))
        if parsed_count is not None:
            text = stripped_text[: trailing_expression_match.start("expr")].strip()
            return parsed_count, max(1, min(parsed_count, photo_max_count())), text

    trailing_digit_match = re.search(r"(?<![A-Za-z])(?P<count>\d{1,2})\s*$", stripped_text)
    if trailing_digit_match:
        requested_count = int(trailing_digit_match.group("count"))
        text = stripped_text[: trailing_digit_match.start("count")].strip()
        return requested_count, max(1, min(requested_count, photo_max_count())), text

    return None


def strip_leading_request_fillers(raw_text: str) -> str:
    text = raw_text.strip()
    fillers = [
        "给我来",
        "给梦美",
        "给我",
        "我想看",
        "我想要",
        "想看",
        "想要",
        "来点",
        "来张",
        "来只",
        "来个",
        "来",
    ]
    changed = True
    while changed and text:
        changed = False
        for filler in fillers:
            if text.startswith(filler):
                text = text[len(filler) :].lstrip()
                changed = True
                break
    return text


def extract_leading_count(raw_text: str) -> tuple[int, int, str] | None:
    stripped_text = strip_leading_request_fillers(raw_text)
    if not stripped_text:
        return None

    half_match = re.match(r"(?P<count>(?:half)|半)\s*(?:张|个|只|幅|p|P)?\s*", stripped_text, flags=re.IGNORECASE)
    if half_match:
        text = stripped_text[half_match.end() :].strip()
        return 0, 1, text

    numeric_match = re.match(
        r"(?P<count>\d[\d\s+\-*/().xX]{0,19})(?:\s*(?:张|个|只|幅|p|P)\s*|\s+)",
        stripped_text,
    )
    if numeric_match:
        parsed_count = evaluate_simple_count_expression(numeric_match.group("count"))
        if parsed_count is not None:
            text = stripped_text[numeric_match.end() :].strip()
            return parsed_count, max(1, min(parsed_count, photo_max_count())), text

    return None


def normalize_query_text(raw_text: str) -> str:
    text = raw_text.strip()
    fillers = [
        "给我",
        "给梦美",
        "来点",
        "来张",
        "来一张",
        "想要",
        "想看",
        "让我看看",
        "我想看",
        "我想要",
        "今天想看",
        "今天想要",
        "发我",
        "发张",
        "发点",
        "整点",
        "看看",
        "照片",
        "图片",
        "涩图",
        "色图",
        "老婆",
        "的",
    ]
    for filler in fillers:
        text = text.replace(filler, " ")
    text = re.sub(r"[，。！？、,.!?；;:：~～/\\\\]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def choose_display_query(raw_query: str, normalized_query: str, profile: CharacterProfile) -> str:
    for candidate in [profile.name, profile.matched_name, *profile.aliases]:
        if not candidate:
            continue
        if normalize_lookup_text(candidate) in normalize_lookup_text(raw_query):
            return candidate
    if normalized_query:
        return normalized_query
    return raw_query.strip()


def resolve_game_name(raw_query: str) -> str | None:
    normalized_query = normalize_lookup_text(raw_query)
    if not normalized_query:
        return None

    best_match: tuple[int, str] | None = None
    for canonical_name, aliases in GAME_ALIASES.items():
        candidates = [canonical_name, *aliases]
        for candidate in candidates:
            normalized_candidate = normalize_lookup_text(candidate)
            if not normalized_candidate:
                continue
            if normalized_candidate == normalized_query:
                match_key = (0, canonical_name)
            elif normalized_candidate.startswith(normalized_query):
                match_key = (1, canonical_name)
            elif normalized_query in normalized_candidate:
                match_key = (2, canonical_name)
            else:
                continue
            if best_match is None or match_key < best_match:
                best_match = match_key
    if best_match is None:
        return None
    return best_match[1]


def resolve_photo_target(query_text: str) -> tuple[str, list[str]] | None:
    normalized_query_text = normalize_query_text(query_text)

    if normalized_query_text in RANDOM_QUERY_ALIASES or normalize_lookup_text(query_text) in RANDOM_QUERY_ALIASES:
        image_files = list(ALL_IMAGE_PATHS)
        if not image_files:
            return None
        return "随机图库", image_files

    profile, display_query = resolve_profile(query_text)
    if profile is None and normalized_query_text:
        profile, display_query = resolve_profile(normalized_query_text)

    if profile is not None:
        image_files = list_character_images(profile.name, config.image_base_folder)
        if not image_files:
            return None

        title_line = format_title_line(display_query, profile.name, profile.matched_name, profile.game_name)
        return title_line, image_files

    game_name = resolve_game_name(query_text)
    if game_name is None and normalized_query_text:
        game_name = resolve_game_name(normalized_query_text)

    if game_name is not None and game_name in GAME_IMAGE_INDEX:
        image_files = list(GAME_IMAGE_INDEX[game_name])
        if not image_files:
            return None
        return f"{game_name} 随机图集", image_files

    return None


def resolve_profile(raw_query: str) -> tuple[CharacterProfile | None, str]:
    direct_profile = get_character_profile(raw_query, config.character_json_path)
    if direct_profile is not None:
        return direct_profile, choose_display_query(raw_query, raw_query.strip(), direct_profile)

    normalized_query = normalize_query_text(raw_query)
    if normalized_query:
        normalized_direct_profile = get_character_profile(normalized_query, config.character_json_path)
        if normalized_direct_profile is not None:
            return normalized_direct_profile, normalized_query

    profile = get_character_profile_from_text(raw_query, config.character_json_path)
    if profile is not None:
        return profile, choose_display_query(raw_query, raw_query.strip(), profile)

    if normalized_query:
        fuzzy_profile = get_character_profile_from_text(normalized_query, config.character_json_path)
        if fuzzy_profile is not None:
            return fuzzy_profile, choose_display_query(raw_query, normalized_query, fuzzy_profile)

    return None, normalized_query


def pick_random_images(image_files: list[str], count: int) -> list[str]:
    if count <= 1:
        return [random.choice(image_files)]
    return random.sample(image_files, count)


def build_forward_node(content: str | Message) -> MessageSegment:
    return MessageSegment.node_custom(
        user_id=os.getenv("QQ_NUMBER"),
        nickname=os.getenv("QQ_ID"),
        content=content,
    )


def build_plain_photo_message(
    reply_message_id: int,
    title_line: str,
    image_paths: list[str],
) -> MessageSegment:
    fallback_msg = MessageSegment.reply(reply_message_id)
    fallback_msg += MessageSegment.text(f"{title_line}\n")
    for image_path in image_paths:
        fallback_msg += MessageSegment.image(image_path)
    return fallback_msg


def build_reply_text(reply_message_id: int, text: str) -> MessageSegment:
    return MessageSegment.reply(reply_message_id) + MessageSegment.text(text)


def validate_requested_count(requested_count: int) -> str | None:
    if requested_count <= 0:
        return "半只也太为难梦美啦，至少也要看一张吧。"
    single_limit = photo_single_request_limit()
    if requested_count > single_limit:
        return f"一次最多只能给你发 {single_limit} 张图哦；多要几张可以分几次来。"
    max_count = photo_max_count()
    if requested_count > max_count:
        return f"梦美觉得不能太贪心，不许一下子要那么多哦。最多只能看 {max_count} 张。"
    return None


def resolve_counted_target(raw_query: str) -> tuple[int, int, tuple[str, list[str]]] | None:
    for count_candidate in (extract_trailing_count(raw_query), extract_leading_count(raw_query)):
        if count_candidate is None:
            continue
        requested_count, count, query = count_candidate
        if not query:
            continue
        resolved_target = resolve_photo_target(query)
        if resolved_target is not None:
            return requested_count, count, resolved_target
    return None


def resolve_photo_selection(raw_query: str) -> tuple[PhotoSelection | None, str | None]:
    if not raw_query:
        return None, "梦美还不知道你想看谁哦。"

    counted_target = resolve_counted_target(raw_query)
    if counted_target is not None:
        requested_count, count, resolved_target = counted_target
    else:
        requested_count = 1
        count = 1
        resolved_target = resolve_photo_target(raw_query)

    if resolved_target is None:
        requested_count, count, query_without_count = extract_count(raw_query)
        count_error = validate_requested_count(requested_count)
        if count_error is not None:
            return None, count_error
        if not query_without_count:
            return None, "梦美知道你想多看几张了，不过还得先告诉我你想看谁哦。"
        resolved_target = resolve_photo_target(query_without_count)

    if resolved_target is None:
        return None, "梦美没有在本地图库里找到对应角色哦。"

    count_error = validate_requested_count(requested_count)
    if count_error is not None:
        return None, count_error

    title_line, image_files = resolved_target
    if not image_files:
        return None, "梦美这里暂时还没有可用图片哦。"
    if count > len(image_files):
        return None, f"梦美这里还没有这么多图哦，现在最多只能给你 {len(image_files)} 张。"
    if count > 1:
        title_line = format_collection_title(title_line, count)

    return PhotoSelection(title_line, image_files, requested_count, count), None


def build_forward_photo_nodes(
    reply_message_id: int,
    title_line: str,
    image_paths: list[str],
) -> list[MessageSegment]:
    reply = MessageSegment.reply(reply_message_id)
    nodes: list[MessageSegment] = [build_forward_node(reply + MessageSegment.text(f"{title_line}\n"))]
    for image_path in image_paths:
        nodes.append(build_forward_node(MessageSegment.image(image_path)))
    return nodes


def record_photo_send_error(
    *,
    raw_query: str,
    error: Exception,
    user_id: str,
    group_id: str | None,
    title_line: str,
    count: int,
    send_mode: str,
    image_paths: list[str],
) -> None:
    record_recent_error(
        command="图片",
        raw_input=raw_query,
        reason=describe_exception_reason("发送图片", error),
        details={
            "user_id": user_id,
            "group_id": group_id or "",
            "target": title_line,
            "count": count,
            "send_mode": send_mode,
            "image_paths": "\n".join(image_paths),
            **extract_exception_details(error),
        },
    )


def record_photo_runtime_error(
    *,
    raw_query: str,
    error: Exception,
    user_id: str,
    group_id: str | None,
    stage: str,
) -> None:
    record_recent_error(
        command="图片",
        raw_input=raw_query,
        reason=f"图片请求{stage}失败",
        details={
            "user_id": user_id,
            "group_id": group_id or "",
            "stage": stage,
            **extract_exception_details(error),
        },
    )


async def send_photo_selection(
    *,
    reply_message_id: int,
    raw_query: str,
    user_id: str,
    group_id: str | None,
    title_line: str,
    image_paths: list[str],
) -> bool:
    try:
        await photo_event.send(
            build_forward_photo_nodes(reply_message_id, title_line, image_paths),
            _timeout=PHOTO_SEND_TIMEOUT,
        )
        return True
    except ActionFailed as error:
        if is_probable_napcat_send_timeout(error):
            logger.warning(
                "Photo send likely succeeded but NapCat timed out while waiting for ack; "
                f"suppressing retry/log spam. user_id={user_id}, target={title_line}, "
                f"count={len(image_paths)}, error={repr(error)}"
            )
            return True

        record_photo_send_error(
            raw_query=raw_query,
            error=error,
            user_id=user_id,
            group_id=group_id,
            title_line=title_line,
            count=len(image_paths),
            send_mode="forward",
            image_paths=image_paths,
        )
        logger.warning(
            "Photo forward send failed; trying plain fallback. "
            f"user_id={user_id}, group_id={group_id}, target={title_line}, error={repr(error)}"
        )
    except (ApiNotAvailable, NetworkError) as error:
        logger.warning(
            "Photo forward send failed before fallback. "
            f"user_id={user_id}, group_id={group_id}, target={title_line}, error={repr(error)}"
        )
        record_photo_send_error(
            raw_query=raw_query,
            error=error,
            user_id=user_id,
            group_id=group_id,
            title_line=title_line,
            count=len(image_paths),
            send_mode="forward",
            image_paths=image_paths,
        )
        await photo_event.finish(build_reply_text(reply_message_id, format_user_send_failure_message(error)))

    fallback_msg = build_plain_photo_message(reply_message_id, title_line, image_paths)
    try:
        await photo_event.send(fallback_msg, _timeout=PHOTO_SEND_TIMEOUT)
        return True
    except (ActionFailed, ApiNotAvailable, NetworkError) as fallback_error:
        record_photo_send_error(
            raw_query=raw_query,
            error=fallback_error,
            user_id=user_id,
            group_id=group_id,
            title_line=title_line,
            count=len(image_paths),
            send_mode="plain_fallback",
            image_paths=image_paths,
        )
        await photo_event.finish(build_reply_text(reply_message_id, format_user_send_failure_message(fallback_error)))


photo_event = nonebot.on_command(
    "照片",
    aliases={"图片", "涩图", "色图", "来张图", "来张照片", "老婆", "涩涩"},
    priority=5,
    block=True,
)


@photo_event.handle()
async def _(event: GroupMessageEvent, args: Message = CommandArg()):
    user_id = str(event.get_user_id())
    group_id = str(event.group_id) if getattr(event, "group_id", None) is not None else None
    message_id = event.message_id
    raw_query = args.extract_plain_text().strip()
    permission_level = resolve_photo_permission(user_id, group_id)

    if permission_level == PHOTO_PERMISSION_DISABLED:
        return

    try:
        selection, error_message = resolve_photo_selection(raw_query)
    except Exception as error:
        logger.exception(
            "Photo request resolve failed: "
            f"user_id={user_id}, group_id={group_id}, raw_query={raw_query}, error={repr(error)}"
        )
        record_photo_runtime_error(
            raw_query=raw_query,
            error=error,
            user_id=user_id,
            group_id=group_id,
            stage="解析",
        )
        await photo_event.finish(build_reply_text(message_id, "图片请求处理时出了点小故障，梦美已经把报错记下来了。这次不扣额度。"))

    if selection is None:
        await photo_event.finish(build_reply_text(message_id, error_message or "梦美没有在本地图库里找到对应角色哦。"))

    if permission_level == PHOTO_PERMISSION_LIMITED:
        _, remaining = get_photo_quota_state(user_id)
        if selection.count > remaining:
            await photo_event.finish(build_reply_text(message_id, format_rate_limit_message(user_id)))

    try:
        picked_images = pick_random_images(selection.image_files, selection.count)
        missing_images = [image_path for image_path in picked_images if not os.path.isfile(image_path)]
    except Exception as error:
        logger.exception(
            "Photo image selection failed: "
            f"user_id={user_id}, group_id={group_id}, target={selection.title_line}, error={repr(error)}"
        )
        record_photo_runtime_error(
            raw_query=raw_query,
            error=error,
            user_id=user_id,
            group_id=group_id,
            stage="选图",
        )
        await photo_event.finish(build_reply_text(message_id, "图片挑选时出了点小故障，梦美已经把报错记下来了。这次不扣额度。"))

    if missing_images:
        await photo_event.finish(build_reply_text(message_id, "梦美翻到了一条失效的图片记录，等我整理一下图库。"))

    logger.info(
        "Photo images selected: "
        f"user_id={user_id}, group_id={group_id}, target={selection.title_line}, "
        f"requested_count={selection.requested_count}, send_count={selection.count}, "
        f"candidate_count={len(selection.image_files)}, images={picked_images}"
    )

    sent = await send_photo_selection(
        reply_message_id=message_id,
        raw_query=raw_query,
        user_id=user_id,
        group_id=group_id,
        title_line=selection.title_line,
        image_paths=picked_images,
    )
    if sent and permission_level == PHOTO_PERMISSION_LIMITED:
        consume_photo_quota(user_id, selection.count)
    await photo_event.finish()
