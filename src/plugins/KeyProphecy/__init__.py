import json
import hashlib
import random
import threading
import time
from datetime import datetime
from pathlib import Path

import nonebot
from nonebot import get_driver, get_plugin_config, logger
from nonebot.exception import FinishedException
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message,
    MessageSegment,
)
from nonebot.adapters.onebot.v11.exception import ActionFailed, ApiNotAvailable, NetworkError
from nonebot.params import CommandArg

from .config import PluginConfig
from .prophecy import Prophecy
from src.utils.character_data import (
    CharacterProfile,
    get_character_profile,
    get_character_profile_from_text,
    list_character_images,
    warmup_character_resource_cache,
)
from src.utils.error_history import extract_exception_details, record_recent_error

__plugin_meta__ = PluginMetadata(
    name="KeyProphecy",
    description="",
    usage="",
    config=PluginConfig,
)

config = get_plugin_config(PluginConfig)
superusers = {str(user_id) for user_id in get_driver().config.superusers}
PROPHECY_SEND_TIMEOUT = 45.0
PROPHECY_ERROR_MESSAGE = "占卜时出了点小故障，请再试一次……"
ROB_WIFE_DENOMINATOR = 500
ROB_WIFE_SUCCESS_WINDOW_SECONDS = 4 * 60 * 60
ROB_WIFE_SUCCESS_PATH = Path(config.character_json_path).resolve().parent / "rob_wife_success.json"
ROB_WIFE_SUCCESS_LOCK = threading.Lock()
BotMessage = Message | MessageSegment

warmup_stats = warmup_character_resource_cache(config.character_json_path, config.image_base_folder)
logger.info(
    "KeyProphecy resource cache warmed up: "
    f"{int(warmup_stats['character_count'])} characters, "
    f"{int(warmup_stats['image_character_count'])} image folders, "
    f"{warmup_stats['total_ms']} ms total"
)


def is_probable_napcat_send_timeout(error: ActionFailed) -> bool:
    return getattr(error, "retcode", None) == 1200 and "Timeout:" in str(error)


def load_rob_wife_success_records(now: float) -> dict[str, float]:
    if not ROB_WIFE_SUCCESS_PATH.is_file():
        return {}

    try:
        with open(ROB_WIFE_SUCCESS_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(data, dict):
        return {}

    records: dict[str, float] = {}
    for user_id, timestamp in data.items():
        try:
            success_at = float(timestamp)
        except (TypeError, ValueError):
            continue
        if now - success_at < ROB_WIFE_SUCCESS_WINDOW_SECONDS:
            records[str(user_id)] = success_at
    return records


def save_rob_wife_success_records(records: dict[str, float]) -> None:
    ROB_WIFE_SUCCESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ROB_WIFE_SUCCESS_PATH, "w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2, sort_keys=True)


def consume_rob_wife_success_slot(user_id: str, lucky_point: int, success_roll: int) -> bool:
    if success_roll > lucky_point:
        return False

    now = time.time()
    with ROB_WIFE_SUCCESS_LOCK:
        records = load_rob_wife_success_records(now)
        if user_id in records:
            save_rob_wife_success_records(records)
            return False

        records[user_id] = now
        save_rob_wife_success_records(records)
    return True


def pick_prophecy_image(user_id: str, heroine: str, image_paths: list[str]) -> str:
    if not image_paths:
        return ""

    today = datetime.now().strftime("%Y-%m-%d")
    seed = int(hashlib.md5(f"{user_id}_{today}_{heroine}_image".encode()).hexdigest(), 16) % (2**32)
    random.seed(seed)
    return random.choice(image_paths)


def describe_luck(lucky_point: int) -> str:
    if lucky_point <= 10:
        return "大凶"
    if lucky_point <= 20:
        return "凶"
    if lucky_point <= 30:
        return "小凶"
    if lucky_point <= 50:
        return "平"
    if lucky_point <= 60:
        return "小吉"
    if lucky_point <= 80:
        return "吉"
    if lucky_point <= 99:
        return "大吉"
    return "头等奖！⭐️"


prophecy_event = nonebot.on_command(
    "今日运势",
    aliases={"抽签", "占卜", "key占卜"},
    priority=8,
    block=True,
)

rob_wife_event = nonebot.on_command(
    "抢",
    aliases={"抢老婆"},
    priority=8,
    block=True,
)


def record_keyprophecy_error(
    *,
    command: str,
    raw_input: str,
    reason: str,
    event: GroupMessageEvent,
    error: Exception,
) -> None:
    details = {
        "user_id": event.get_user_id(),
        "group_id": getattr(event, "group_id", ""),
    }
    details.update(extract_exception_details(error))
    record_recent_error(command=command, raw_input=raw_input, reason=reason, details=details)


def get_profile_image(user_id: str, profile: CharacterProfile) -> str:
    image_list = list_character_images(profile.name, config.image_base_folder)
    image_path = pick_prophecy_image(user_id, profile.name, image_list)
    if image_path and Path(image_path).is_file():
        logger.info(
            "KeyProphecy image matched: "
            f"user_id={user_id}, heroine={profile.name}, game={profile.game_name}, image_path={image_path}"
        )
        return image_path
    return ""


def build_wife_body(
    user_id: str,
    heroine: str,
    profile: CharacterProfile | None = None,
) -> BotMessage:
    profile = profile or get_character_profile(heroine, config.character_json_path)
    display_name = profile.name if profile is not None else heroine
    game_name = profile.game_name if profile is not None else "null"
    image_path = get_profile_image(user_id, profile) if profile is not None else ""

    msg = MessageSegment.text(f"🌟你今日的key社老婆为{game_name}中的{display_name}🌟")
    if image_path:
        msg += MessageSegment.image(image_path)
    return msg


def build_prophecy_body(
    user_id: str,
    prophecier: Prophecy,
    wife_profile: CharacterProfile | None = None,
) -> BotMessage:
    heroine = wife_profile.name if wife_profile is not None else prophecier.getHeroine()
    lucky_point = prophecier.getLuckyPoint()
    dos, donts = prophecier.getDosDonts()
    lucky_thing = prophecier.getLuckyThing()

    msg = MessageSegment.text(f"你的今日运势值为{lucky_point}：{describe_luck(lucky_point)}\n")
    msg += build_wife_body(user_id, heroine, wife_profile)
    msg += MessageSegment.text(f"✅宜: {dos[0]}、{dos[1]}、{dos[2]}\n")
    msg += MessageSegment.text(f"🈲忌: {donts[0]}、{donts[1]}、{donts[2]}\n")
    msg += MessageSegment.text(f"⭐占卜结果显示今天你会{lucky_thing}哦！")
    return msg


def build_prophecy_message(
    user_id: str,
    prophecier: Prophecy,
    *,
    wife_profile: CharacterProfile | None = None,
    rob_denied: bool = False,
) -> BotMessage:
    msg = MessageSegment.at(user_id)
    msg += MessageSegment.text(" \n不给你抢!\n" if rob_denied else " ")
    msg += build_prophecy_body(user_id, prophecier, wife_profile)
    return msg


def can_rob_wife(
    *,
    user_id: str,
    prophecier: Prophecy,
    is_admin: bool,
) -> bool:
    if is_admin:
        return True
    return consume_rob_wife_success_slot(
        user_id,
        prophecier.getLuckyPoint(),
        prophecier.getRobSuccessRoll(ROB_WIFE_DENOMINATOR),
    )


def build_wife_message(
    *,
    user_id: str,
    prophecier: Prophecy,
    requested_name: str,
    is_admin: bool,
) -> BotMessage:
    target_profile = None
    if requested_name:
        target_profile = get_character_profile_from_text(requested_name, config.character_json_path)

    if target_profile is not None and can_rob_wife(
        user_id=user_id,
        prophecier=prophecier,
        is_admin=is_admin,
    ):
        return build_prophecy_message(user_id, prophecier, wife_profile=target_profile)

    return build_prophecy_message(user_id, prophecier, rob_denied=True)


async def finish_with_prophecy_message(
    matcher,
    msg: BotMessage,
    *,
    command: str,
    raw_input: str,
    event: GroupMessageEvent,
    log_prefix: str,
    send_failure_reason: str,
) -> None:
    try:
        await matcher.finish(msg, _timeout=PROPHECY_SEND_TIMEOUT)
    except FinishedException:
        return
    except ActionFailed as e:
        if is_probable_napcat_send_timeout(e):
            logger.warning(
                f"{log_prefix} send likely succeeded but NapCat timed out while waiting for ack; "
                f"suppressing retry/log spam. user_id={event.get_user_id()}, "
                f"timeout={PROPHECY_SEND_TIMEOUT}, error={repr(e)}"
            )
            return
        raise
    except (ApiNotAvailable, NetworkError) as e:
        logger.warning(
            f"{log_prefix} send failed after a single attempt; not retrying. "
            f"user_id={event.get_user_id()}, timeout={PROPHECY_SEND_TIMEOUT}, error={repr(e)}"
        )
        record_keyprophecy_error(
            command=command,
            raw_input=raw_input,
            reason=send_failure_reason,
            event=event,
            error=e,
        )
        return


@prophecy_event.handle()
async def _(event: GroupMessageEvent, args: Message = CommandArg()):
    user_id = str(event.get_user_id())
    raw_input = args.extract_plain_text().strip()
    try:
        prophecier = Prophecy(user_id)
        msg = build_prophecy_message(user_id, prophecier)
    except Exception as e:
        logger.exception(f"KeyProphecy failed before sending message: user_id={user_id}, error={repr(e)}")
        record_keyprophecy_error(
            command="占卜",
            raw_input=raw_input,
            reason="占卜生成失败",
            event=event,
            error=e,
        )
        await prophecy_event.finish(PROPHECY_ERROR_MESSAGE, _timeout=10.0)

    await finish_with_prophecy_message(
        prophecy_event,
        msg,
        command="占卜",
        raw_input=raw_input,
        event=event,
        log_prefix="KeyProphecy",
        send_failure_reason="占卜结果发送失败",
    )


@rob_wife_event.handle()
async def _(event: GroupMessageEvent, args: Message = CommandArg()):
    user_id = str(event.get_user_id())
    requested_name = args.extract_plain_text().strip()
    try:
        prophecier = Prophecy(user_id)
        msg = build_wife_message(
            user_id=user_id,
            prophecier=prophecier,
            requested_name=requested_name,
            is_admin=user_id in superusers,
        )
    except Exception as e:
        logger.exception(f"Rob wife failed before sending message: user_id={user_id}, error={repr(e)}")
        record_keyprophecy_error(
            command="抢老婆",
            raw_input=requested_name,
            reason="抢老婆判定失败",
            event=event,
            error=e,
        )
        await rob_wife_event.finish(PROPHECY_ERROR_MESSAGE, _timeout=10.0)

    await finish_with_prophecy_message(
        rob_wife_event,
        msg,
        command="抢老婆",
        raw_input=requested_name,
        event=event,
        log_prefix="Rob wife",
        send_failure_reason="抢老婆结果发送失败",
    )
