from __future__ import annotations

import html
import ipaddress
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.utils.paths import PROJECT_ROOT


MEMORY_KINDS = {"key_character", "key_meme", "group_member"}
CONFIDENCE_LEVELS = {"draft", "verified", "uncertain"}
DEFAULT_TIMEZONE = "Asia/Shanghai"
SEARCH_PAGE_FETCH_LIMIT = 160000

KNOWN_WEATHER_LOCATIONS = {
    "北京": (39.9042, 116.4074, "北京市", DEFAULT_TIMEZONE),
    "北京市": (39.9042, 116.4074, "北京市", DEFAULT_TIMEZONE),
    "北京海淀": (39.9593, 116.2985, "北京市海淀区", DEFAULT_TIMEZONE),
    "北京市海淀": (39.9593, 116.2985, "北京市海淀区", DEFAULT_TIMEZONE),
    "海淀": (39.9593, 116.2985, "北京市海淀区", DEFAULT_TIMEZONE),
    "海淀区": (39.9593, 116.2985, "北京市海淀区", DEFAULT_TIMEZONE),
}

WEATHER_CODE_TEXT = {
    0: "晴",
    1: "大致晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "中等毛毛雨",
    55: "较强毛毛雨",
    56: "冻毛毛雨",
    57: "较强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "较强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "小阵雨",
    81: "中等阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴大冰雹",
}


class ChatAgentRuntime:
    def __init__(
        self,
        memory_path: Path,
        session_id: str | None,
        speaker_name: str | None,
        user_id: str | None,
        allow_network: bool,
    ) -> None:
        self.memory_path = memory_path
        self.session_id = session_id or ""
        self.speaker_name = speaker_name or ""
        self.user_id = user_id or ""
        self.allow_network = allow_network

    def tool_specs(self) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = [
            {
                "type": "function",
                "function": {
                    "name": "local_time",
                    "description": "Return the current date and time. Use this for questions about today, now, current date, or time.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "timezone": {
                                "type": "string",
                                "description": "IANA timezone, default Asia/Shanghai.",
                            },
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_memory_entry",
                    "description": (
                        "Append a structured draft memory entry for Key characters, Key memes, "
                        "or group members. Use only for durable notes that should be saved."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "kind": {
                                "type": "string",
                                "enum": sorted(MEMORY_KINDS),
                            },
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                            "source": {"type": "string"},
                            "confidence": {
                                "type": "string",
                                "enum": sorted(CONFIDENCE_LEVELS),
                            },
                            "related_names": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["kind", "title", "content"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_memory_entries",
                    "description": "Search existing Yumemi chat-agent memory entries before adding a duplicate note.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "max_results": {"type": "integer", "minimum": 1, "maximum": 20},
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                },
            },
        ]

        if self.allow_network:
            specs.extend(
                [
                    {
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "description": "Search the public web for current sources or Key reference material.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string"},
                                    "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
                                },
                                "required": ["query"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "description": (
                                "Get current weather and a short forecast for a public location via Open-Meteo. "
                                "Use this for weather questions instead of guessing."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "location": {
                                        "type": "string",
                                        "description": "Location name, for example 北京海淀, 上海, Tokyo.",
                                    },
                                    "forecast_days": {
                                        "type": "integer",
                                        "minimum": 1,
                                        "maximum": 3,
                                    },
                                },
                                "required": ["location"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "fetch_url",
                            "description": "Fetch a public HTTP/HTTPS page and return readable text.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "url": {"type": "string"},
                                    "max_chars": {"type": "integer", "minimum": 500, "maximum": 20000},
                                },
                                "required": ["url"],
                                "additionalProperties": False,
                            },
                        },
                    },
                ]
            )
        return specs

    def execute_json(self, name: str, arguments_json: str) -> str:
        try:
            arguments = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as exc:
            return f"工具参数不是合法 JSON: {exc}"
        if not isinstance(arguments, dict):
            return "工具参数必须是 JSON object"
        try:
            return self.execute(name, arguments)
        except Exception as exc:  # noqa: BLE001
            return f"工具执行失败: {type(exc).__name__}: {exc}"

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "local_time":
            return self.local_time(str(arguments.get("timezone") or DEFAULT_TIMEZONE))
        if name == "write_memory_entry":
            return self.write_memory_entry(
                kind=str(arguments.get("kind") or ""),
                title=str(arguments.get("title") or ""),
                content=str(arguments.get("content") or ""),
                source=str(arguments.get("source") or ""),
                confidence=str(arguments.get("confidence") or "draft"),
                related_names=arguments.get("related_names") or [],
            )
        if name == "search_memory_entries":
            return self.search_memory_entries(
                query=str(arguments.get("query") or ""),
                max_results=int(arguments.get("max_results") or 5),
            )
        if name == "web_search" and self.allow_network:
            return self.web_search(
                query=str(arguments.get("query") or ""),
                max_results=int(arguments.get("max_results") or 5),
            )
        if name in {"get_weather", "weather"} and self.allow_network:
            return self.get_weather(
                location=str(arguments.get("location") or ""),
                forecast_days=int(arguments.get("forecast_days") or 1),
            )
        if name == "fetch_url" and self.allow_network:
            return self.fetch_url(
                url=str(arguments.get("url") or ""),
                max_chars=int(arguments.get("max_chars") or 6000),
            )
        return f"未知或未启用的工具: {name}"

    def local_time(self, timezone_name: str) -> str:
        timezone_name = timezone_name.strip() or DEFAULT_TIMEZONE
        try:
            tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            timezone_name = DEFAULT_TIMEZONE
            tz = ZoneInfo(DEFAULT_TIMEZONE)
        now = datetime.now(tz)
        return (
            f"timezone: {timezone_name}\n"
            f"iso: {now.isoformat(timespec='seconds')}\n"
            f"date: {now:%Y-%m-%d}\n"
            f"time: {now:%H:%M:%S}\n"
            f"weekday: {weekday_name(now.weekday())}"
        )

    def write_memory_entry(
        self,
        kind: str,
        title: str,
        content: str,
        source: str,
        confidence: str,
        related_names: object,
    ) -> str:
        kind = kind.strip()
        confidence = confidence.strip() or "draft"
        title = compact_text(title, 120)
        content = content.strip()
        source = compact_text(source, 500)
        if kind not in MEMORY_KINDS:
            return f"kind 必须是: {', '.join(sorted(MEMORY_KINDS))}"
        if confidence not in CONFIDENCE_LEVELS:
            confidence = "draft"
        if not title or not content:
            return "title 和 content 不能为空"
        if len(content) > 4000:
            return "content 过长，请压缩到 4000 字以内"
        if isinstance(related_names, list):
            names = [compact_text(str(item), 80) for item in related_names if str(item).strip()]
        else:
            names = []

        entry = {
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "kind": kind,
            "title": title,
            "content": content,
            "source": source,
            "confidence": confidence,
            "related_names": names[:20],
            "session_id": self.session_id,
            "speaker_name": self.speaker_name,
            "user_id": self.user_id,
        }
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        with self.memory_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        return f"已写入记忆条目: {self.memory_path} ({kind}: {title})"

    def search_memory_entries(self, query: str, max_results: int) -> str:
        query = query.strip().casefold()
        if not query:
            return "query 不能为空"
        if not self.memory_path.exists():
            return "暂无 chat-agent 记忆条目"

        rows: list[str] = []
        limit = max(1, min(max_results, 20))
        for line in self.memory_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if query not in line.casefold():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append(
                f"- {entry.get('kind')}: {entry.get('title')} "
                f"[{entry.get('confidence')}] {compact_text(str(entry.get('content') or ''), 240)}"
            )
            if len(rows) >= limit:
                break
        return "\n".join(rows) or "未找到匹配记忆条目"

    def fetch_url(self, url: str, max_chars: int) -> str:
        checked_url = validate_public_url(url)
        limit = max(500, min(max_chars, 20000))
        content_type, text = fetch_url_text(checked_url, limit)
        if "html" in content_type.casefold():
            text = html_to_text(text)
        if len(text) > limit:
            text = text[:limit] + f"\n... truncated at {limit} chars"
        return f"url: {checked_url}\ncontent_type: {content_type}\n\n{text}"

    def web_search(self, query: str, max_results: int) -> str:
        if not query.strip():
            return "query 不能为空"
        count = max(1, min(max_results, 10))
        attempts = [
            (
                "DuckDuckGo",
                f"https://duckduckgo.com/html/?{urllib.parse.urlencode({'q': query})}",
                parse_duckduckgo_results,
            ),
            (
                "Bing",
                f"https://www.bing.com/search?{urllib.parse.urlencode({'q': query, 'setlang': 'zh-CN'})}",
                parse_bing_results,
            ),
        ]
        errors: list[str] = []
        for source_name, search_url, parser in attempts:
            checked_url = validate_public_url(search_url)
            _, raw = fetch_url_text(checked_url, SEARCH_PAGE_FETCH_LIMIT)
            if is_network_error_text(raw):
                errors.append(f"{source_name}: {compact_text(raw, 240)}")
                continue
            results = parser(raw, count)
            if results:
                lines = [f"source: {source_name}"]
                lines.extend(f"{index + 1}. {title}\n{url}" for index, (title, url) in enumerate(results))
                return "\n".join(lines)
            errors.append(f"{source_name}: no parseable results")
        return "搜索失败；" + "；".join(errors)

    def get_weather(self, location: str, forecast_days: int) -> str:
        location = location.strip()
        if not location:
            return "location 不能为空"
        days = max(1, min(forecast_days, 3))
        latitude, longitude, resolved_name, timezone_name = resolve_weather_location(location)
        params = urllib.parse.urlencode(
            {
                "latitude": f"{latitude:.4f}",
                "longitude": f"{longitude:.4f}",
                "current": ",".join(
                    [
                        "temperature_2m",
                        "relative_humidity_2m",
                        "apparent_temperature",
                        "precipitation",
                        "weather_code",
                        "wind_speed_10m",
                    ]
                ),
                "daily": ",".join(
                    [
                        "weather_code",
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "precipitation_probability_max",
                    ]
                ),
                "timezone": timezone_name,
                "forecast_days": str(days),
            }
        )
        url = validate_public_url(f"https://api.open-meteo.com/v1/forecast?{params}")
        data = fetch_json(url, 40000)
        current = data.get("current") if isinstance(data, dict) else {}
        daily = data.get("daily") if isinstance(data, dict) else {}
        if not isinstance(current, dict):
            current = {}
        if not isinstance(daily, dict):
            daily = {}

        code = weather_code_value(current.get("weather_code"))
        rows = [
            f"location: {resolved_name}",
            f"coordinates: {latitude:.4f}, {longitude:.4f}",
            f"timezone: {timezone_name}",
            f"current_time: {current.get('time') or 'unknown'}",
            (
                "current: "
                f"{WEATHER_CODE_TEXT.get(code, '未知天气')}，"
                f"气温 {current.get('temperature_2m', '?')}°C，"
                f"体感 {current.get('apparent_temperature', '?')}°C，"
                f"湿度 {current.get('relative_humidity_2m', '?')}%，"
                f"降水 {current.get('precipitation', '?')} mm，"
                f"风速 {current.get('wind_speed_10m', '?')} km/h"
            ),
        ]

        dates = daily.get("time") if isinstance(daily.get("time"), list) else []
        max_t = daily.get("temperature_2m_max") if isinstance(daily.get("temperature_2m_max"), list) else []
        min_t = daily.get("temperature_2m_min") if isinstance(daily.get("temperature_2m_min"), list) else []
        rain = (
            daily.get("precipitation_probability_max")
            if isinstance(daily.get("precipitation_probability_max"), list)
            else []
        )
        codes = daily.get("weather_code") if isinstance(daily.get("weather_code"), list) else []
        if dates:
            rows.append("forecast:")
            for index, date_text in enumerate(dates[:days]):
                day_code = weather_code_value(codes[index] if index < len(codes) else None)
                rows.append(
                    f"- {date_text}: {WEATHER_CODE_TEXT.get(day_code, '未知天气')}，"
                    f"{value_at(min_t, index)}-{value_at(max_t, index)}°C，"
                    f"最大降水概率 {value_at(rain, index)}%"
                )
        rows.append("source: Open-Meteo")
        return "\n".join(rows)


def resolve_agent_memory_path(path_text: str) -> Path:
    path = Path(path_text).expanduser() if path_text else PROJECT_ROOT / "resource/chat_agent_memory.jsonl"
    return path if path.is_absolute() else PROJECT_ROOT / path


def weekday_name(index: int) -> str:
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return names[index] if 0 <= index < len(names) else "unknown"


def compact_text(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def validate_public_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("只允许 http/https URL")
    if not parsed.hostname:
        raise ValueError("URL 缺少 hostname")
    host = parsed.hostname.casefold()
    if host == "localhost" or host.endswith(".local"):
        raise ValueError("联网工具不访问 localhost 或 .local 地址")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved):
        raise ValueError("联网工具不访问内网、回环或保留 IP")
    return urllib.parse.urlunparse(parsed)


def resolve_weather_location(location: str) -> tuple[float, float, str, str]:
    normalized = re.sub(r"\s+", "", location.casefold())
    for key, value in KNOWN_WEATHER_LOCATIONS.items():
        if normalized == re.sub(r"\s+", "", key.casefold()):
            return value

    params = urllib.parse.urlencode(
        {
            "name": location,
            "count": "1",
            "language": "zh",
            "format": "json",
        }
    )
    url = validate_public_url(f"https://geocoding-api.open-meteo.com/v1/search?{params}")
    data = fetch_json(url, 20000)
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list) or not results:
        raise ValueError(f"没有找到地点: {location}")
    first = results[0]
    if not isinstance(first, dict):
        raise ValueError(f"地点解析结果格式异常: {location}")
    latitude = float(first["latitude"])
    longitude = float(first["longitude"])
    timezone_name = str(first.get("timezone") or DEFAULT_TIMEZONE)
    name_parts = [
        str(first.get("country") or ""),
        str(first.get("admin1") or ""),
        str(first.get("admin2") or ""),
        str(first.get("name") or location),
    ]
    resolved_name = " ".join(part for part in name_parts if part)
    return latitude, longitude, resolved_name, timezone_name


def fetch_json(checked_url: str, limit: int) -> dict[str, Any]:
    content_type, text = fetch_url_text(checked_url, limit)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"接口返回不是 JSON: content_type={content_type}, body={text[:500]}") from exc
    if not isinstance(data, dict):
        raise ValueError("接口返回 JSON 不是 object")
    return data


def value_at(values: list[Any], index: int) -> str:
    if index >= len(values) or values[index] is None:
        return "?"
    return str(values[index])


def weather_code_value(value: Any) -> int:
    if value is None:
        return -1
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def fetch_url_text(checked_url: str, limit: int) -> tuple[str, str]:
    request = urllib.request.Request(
        checked_url,
        headers={
            "User-Agent": "yumemi-chat-agent/0.1",
            "Accept": "text/html,text/plain,application/json;q=0.9,*/*;q=0.5",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", errors="replace")
        return "text/plain", f"HTTP {exc.code}: {detail}"
    except urllib.error.URLError as exc:
        return "text/plain", f"网络请求失败: {exc.reason}"
    return content_type, raw.decode("utf-8", errors="replace")


def html_to_text(source: str) -> str:
    source = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", source)
    source = re.sub(r"(?s)<br\s*/?>", "\n", source)
    source = re.sub(r"(?s)</p\s*>", "\n", source)
    source = re.sub(r"(?s)<.*?>", " ", source)
    source = html.unescape(source)
    lines = [" ".join(line.split()) for line in source.splitlines()]
    return "\n".join(line for line in lines if line)


def parse_duckduckgo_results(text: str, max_results: int) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for match in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', text, re.I | re.S):
        url = html.unescape(match.group(1))
        title = html_to_text(match.group(2))
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        if "uddg" in query:
            url = query["uddg"][0]
        if title and url:
            results.append((title, url))
        if len(results) >= max_results:
            break
    return results


def parse_bing_results(text: str, max_results: int) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    blocks = re.findall(
        r'<li[^>]*class="[^"]*\bb_algo\b[^"]*"[^>]*>(.*?)(?=<li[^>]*class="[^"]*\bb_algo\b|\Z)',
        text,
        re.I | re.S,
    )
    if not blocks:
        blocks = re.findall(r"<h2[^>]*>.*?</h2>", text, re.I | re.S)
    for block in blocks:
        match = re.search(r"<h2[^>]*>.*?<a\b[^>]*\bhref=\"([^\"]+)\"[^>]*>(.*?)</a>", block, re.I | re.S)
        if not match:
            match = re.search(r"<a\b[^>]*\bhref=\"([^\"]+)\"[^>]*>(.*?)</a>", block, re.I | re.S)
        if not match:
            continue
        url = html.unescape(match.group(1))
        title = html_to_text(match.group(2))
        if not title or not url:
            continue
        if not url.startswith(("http://", "https://")):
            continue
        if "bing.com" in urllib.parse.urlparse(url).netloc.casefold():
            continue
        item = (title, url)
        if item not in results:
            results.append(item)
        if len(results) >= max_results:
            return results
    return results


def is_network_error_text(text: str) -> bool:
    return text.startswith(("网络请求失败:", "HTTP 429:", "HTTP 403:", "HTTP 503:"))
