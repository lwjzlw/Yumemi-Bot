#!/usr/bin/env python3
"""Small dotenv helper for manage_bot.

Only use this for non-secret operational toggles. It preserves unrelated lines
and never prints the whole env file.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def normalize_bool(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in TRUE_VALUES:
        return "true"
    if lowered in FALSE_VALUES:
        return "false"
    raise SystemExit(f"invalid boolean value: {value!r}")


def line_key(raw_line: str) -> str | None:
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    key = line.split("=", 1)[0].strip()
    if key.startswith("export "):
        key = key.removeprefix("export ").strip()
    return key or None


def strip_inline_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
            continue
        if char == "#" and quote is None:
            return value[:index].rstrip()
    return value.strip()


def read_value(path: Path, key: str, default: str = "") -> str:
    if not path.exists():
        return default
    for raw_line in reversed(path.read_text(encoding="utf-8").splitlines()):
        if line_key(raw_line) != key:
            continue
        value = strip_inline_comment(raw_line.split("=", 1)[1])
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value
    return default


def write_value(path: Path, key: str, value: str) -> None:
    if not KEY_RE.match(key):
        raise SystemExit(f"invalid env key: {key!r}")

    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    replaced = False
    output: list[str] = []
    for raw_line in lines:
        if line_key(raw_line) == key:
            output.append(f"{key}={value}")
            replaced = True
        else:
            output.append(raw_line)

    if not replaced:
        if output and output[-1].strip():
            output.append("")
        output.append(f"{key}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Read or update non-secret Yumemi bot env toggles.")
    parser.add_argument("env_file", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)

    get_parser = subparsers.add_parser("get")
    get_parser.add_argument("key")
    get_parser.add_argument("default", nargs="?", default="")

    set_bool_parser = subparsers.add_parser("set-bool")
    set_bool_parser.add_argument("key")
    set_bool_parser.add_argument("value")

    args = parser.parse_args()

    if args.command == "get":
        print(read_value(args.env_file, args.key, args.default))
        return

    if args.command == "set-bool":
        value = normalize_bool(args.value)
        write_value(args.env_file, args.key, value)
        print(f"{args.key}={value}")


if __name__ == "__main__":
    main()
