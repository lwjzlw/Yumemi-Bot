import json
import threading
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from nonebot.adapters.onebot.v11.exception import ActionFailed, ApiNotAvailable, NetworkError

from .paths import RECENT_ERROR_LOG_PATH

MAX_RECENT_ERRORS = 5
_ERROR_LOG_LOCK = threading.Lock()


def _normalize_detail_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _load_recent_errors(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []

    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def list_recent_errors(limit: int = MAX_RECENT_ERRORS) -> list[dict[str, Any]]:
    path = Path(RECENT_ERROR_LOG_PATH)
    with _ERROR_LOG_LOCK:
        errors = _load_recent_errors(path)
    if limit <= 0:
        return []
    return errors[-limit:][::-1]


def record_recent_error(
    *,
    command: str,
    reason: str,
    raw_input: str = "",
    details: Mapping[str, Any] | None = None,
) -> None:
    path = Path(RECENT_ERROR_LOG_PATH)
    payload = {
        "timestamp": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
        "command": command.strip() or "未知命令",
        "raw_input": raw_input.strip(),
        "reason": reason.strip() or "未知错误",
    }

    normalized_details: dict[str, str] = {}
    if details:
        for key, value in details.items():
            normalized_value = _normalize_detail_value(value)
            if normalized_value:
                normalized_details[str(key)] = normalized_value
    if normalized_details:
        payload["details"] = normalized_details

    with _ERROR_LOG_LOCK:
        history = _load_recent_errors(path)
        history.append(payload)
        history = history[-MAX_RECENT_ERRORS:]
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(history, file, ensure_ascii=False, indent=2)


def extract_exception_details(error: Exception) -> dict[str, str]:
    details = {"error": repr(error)}

    if isinstance(error, ActionFailed):
        retcode = getattr(error, "retcode", None)
        message = getattr(error, "message", "")
        wording = getattr(error, "wording", "")
        if retcode is not None:
            details["retcode"] = str(retcode)
        if message:
            details["message"] = str(message)
        if wording and wording != message:
            details["wording"] = str(wording)
    return details


def describe_exception_reason(action: str, error: Exception) -> str:
    if isinstance(error, NetworkError):
        return f"{action}时网络异常"
    if isinstance(error, ApiNotAvailable):
        return f"{action}时 OneBot API 不可用"
    if isinstance(error, ActionFailed):
        wording = " ".join(
            str(part).strip()
            for part in (
                getattr(error, "wording", ""),
                getattr(error, "message", ""),
            )
            if str(part).strip()
        )
        lowered_wording = wording.lower()
        if "转发消息" in wording:
            return f"{action}时转发消息发送失败"
        if any(keyword in wording for keyword in ("禁止", "限制", "风控", "拦截", "封禁", "屏蔽", "不允许")):
            return f"{action}被 QQ 或平台侧拦截"
        if any(keyword in wording for keyword in ("图片", "文件", "上传")):
            return f"{action}时图片或文件发送失败"
        if "timeout" in lowered_wording or getattr(error, "retcode", None) == 1200:
            return f"{action}时 NapCat 或 OneBot 返回失败"
        return f"{action}时接口返回失败"
    return f"{action}时发生异常"
