from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SUPPORTED_SUFFIXES = {".py", ".sh", ".ps1", ".bat", ".cmd"}
DEFAULT_REGISTRY_NAME = "tools_registry.json"

DEFAULT_REGISTRY: dict[str, Any] = {
    "tools": [
        {
            "name": "import-images",
            "path": "import_temp_images.py",
            "description": "把 resource/temp 中的图片按角色导入图库，自动去重，并记录 manifest。",
            "aliases": ["import", "temp-import"],
            "default_args": [],
        },
        {
            "name": "flatten-images",
            "path": "flatten_and_rename_images.py",
            "description": "把角色目录下的子文件夹图片提到根层，并只对新增/异常命名图片做增量编号。",
            "aliases": ["flatten", "rename-images"],
            "default_args": [],
        },
        {
            "name": "check-images",
            "path": "check_image_folders.py",
            "description": "检查图库文件夹完整性，并生成报告与 CSV。",
            "aliases": ["check", "image-check"],
            "default_args": [],
        },
        {
            "name": "update-images",
            "path": "update_images_batched.sh",
            "description": "按 manifest 或全量模式把图库同步到 WSL 仓库并分批 git push。",
            "aliases": ["push-images", "sync-images"],
            "default_args": [],
        },
        {
            "name": "make-image-folders",
            "path": "make_image_folders.py",
            "description": "根据 character_data.json 自动补齐 resource/images 下的角色文件夹。",
            "aliases": ["mkfolders", "make-folders"],
            "default_args": [],
        },
        {
            "name": "shuffle-keyprophecy",
            "path": "shuffle_keyprophecy_txt.py",
            "description": "打乱 KeyProphecy 的若干 txt 文件，并自动备份。",
            "aliases": ["shuffle", "shuffle-txt"],
            "default_args": [],
        },
    ],
    "workflows": [
        {
            "name": "images-preview",
            "description": "先预览导入、整理、检查图库，不实际改动文件。",
            "steps": [
                {"tool": "import-images", "args": []},
                {"tool": "flatten-images", "args": []},
                {"tool": "check-images", "args": []},
            ],
        },
        {
            "name": "images-apply",
            "description": "执行导入与整理，然后做一次默认阈值检查。",
            "steps": [
                {"tool": "import-images", "args": ["--apply"]},
                {"tool": "flatten-images", "args": ["--apply"]},
                {"tool": "check-images", "args": []},
            ],
        },
        {
            "name": "images-push",
            "description": "执行导入与整理，然后按 manifest 模式同步并 push。",
            "steps": [
                {"tool": "import-images", "args": ["--apply"]},
                {"tool": "flatten-images", "args": ["--apply"]},
                {"tool": "update-images", "args": []},
            ],
        },
        {
            "name": "images-full-push",
            "description": "不走 manifest，直接走全量同步并 push。",
            "steps": [
                {"tool": "update-images", "args": [], "env": {"FULL": "1"}},
            ],
        },
    ],
}


@dataclass
class ToolDef:
    name: str
    path: Path
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    default_args: list[str] = field(default_factory=list)
    interpreter: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None


@dataclass
class WorkflowStep:
    tool: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None


@dataclass
class WorkflowDef:
    name: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)


class AssistantError(RuntimeError):
    pass


class ToolsAssistant:
    def __init__(self, tools_dir: Path, registry_path: Path):
        self.tools_dir = tools_dir.resolve()
        self.registry_path = registry_path.resolve()
        self.registry_raw = self._load_registry_raw()
        self.tools = self._load_tools()
        self.workflows = self._load_workflows()

    @staticmethod
    def find_project_root(start: Path) -> Path:
        for path in [start, *start.parents]:
            if (path / "tools").exists() and (path / "resource").exists():
                return path
        raise FileNotFoundError("未找到项目根目录（需要同时包含 tools/ 和 resource/）。")

    @classmethod
    def from_script_location(cls, script_path: Path, registry_override: str | None = None) -> "ToolsAssistant":
        project_root = cls.find_project_root(script_path.resolve().parent)
        tools_dir = project_root / "tools"
        registry_path = Path(registry_override).expanduser().resolve() if registry_override else tools_dir / DEFAULT_REGISTRY_NAME
        return cls(tools_dir=tools_dir, registry_path=registry_path)

    def reload(self) -> None:
        self.registry_raw = self._load_registry_raw()
        self.tools = self._load_tools()
        self.workflows = self._load_workflows()

    def _load_registry_raw(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"tools": [], "workflows": []}
        with open(self.registry_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise AssistantError(f"注册表格式错误：{self.registry_path} 顶层必须是对象。")
        data.setdefault("tools", [])
        data.setdefault("workflows", [])
        return data

    def save_registry(self) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_path, "w", encoding="utf-8-sig") as f:
            json.dump(self.registry_raw, f, ensure_ascii=False, indent=2)
            f.write("\n")

    def _scan_tool_files(self) -> dict[str, Path]:
        found: dict[str, Path] = {}
        for p in sorted(self.tools_dir.iterdir(), key=lambda x: x.name.lower()):
            if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES:
                found[p.name] = p
        return found

    def _infer_interpreter(self, path: Path) -> str | None:
        suffix = path.suffix.lower()
        if suffix == ".py":
            return "python"
        if suffix == ".sh":
            return "bash"
        if suffix == ".ps1":
            return "powershell"
        if suffix in {".bat", ".cmd"}:
            return "cmd"
        return None

    def _load_tools(self) -> dict[str, ToolDef]:
        scanned = self._scan_tool_files()
        result: dict[str, ToolDef] = {}
        alias_seen: dict[str, str] = {}

        for filename, path in scanned.items():
            stem = path.stem
            tool = ToolDef(
                name=stem,
                path=path,
                description="",
                aliases=[],
                default_args=[],
                interpreter=self._infer_interpreter(path),
                env={},
                cwd=None,
            )
            result[stem] = tool
            alias_seen[stem] = stem
            alias_seen[filename] = stem

        for item in self.registry_raw.get("tools", []):
            if not isinstance(item, dict):
                continue
            path_value = str(item.get("path", "")).strip()
            name = str(item.get("name", "")).strip()
            if not name or not path_value:
                continue

            path = Path(path_value)
            if not path.is_absolute():
                path = (self.tools_dir / path).resolve()
            interpreter = item.get("interpreter")
            if interpreter is None:
                interpreter = self._infer_interpreter(path)

            tool = ToolDef(
                name=name,
                path=path,
                description=str(item.get("description", "")).strip(),
                aliases=[str(x).strip() for x in item.get("aliases", []) if str(x).strip()],
                default_args=[str(x) for x in item.get("default_args", [])],
                interpreter=interpreter,
                env={str(k): str(v) for k, v in dict(item.get("env", {})).items()},
                cwd=str(item.get("cwd")).strip() if item.get("cwd") else None,
            )
            result[name] = tool
            alias_seen[name] = name
            alias_seen[path.name] = name
            alias_seen[path.stem] = name
            for alias in tool.aliases:
                if alias in alias_seen and alias_seen[alias] != name:
                    raise AssistantError(f"别名冲突：{alias!r} 同时指向 {alias_seen[alias]!r} 和 {name!r}")
                alias_seen[alias] = name

        self.alias_map = alias_seen
        return result

    def _load_workflows(self) -> dict[str, WorkflowDef]:
        result: dict[str, WorkflowDef] = {}
        for item in self.registry_raw.get("workflows", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            steps: list[WorkflowStep] = []
            for raw_step in item.get("steps", []):
                if not isinstance(raw_step, dict):
                    continue
                tool = str(raw_step.get("tool", "")).strip()
                if not tool:
                    continue
                steps.append(
                    WorkflowStep(
                        tool=tool,
                        args=[str(x) for x in raw_step.get("args", [])],
                        env={str(k): str(v) for k, v in dict(raw_step.get("env", {})).items()},
                        cwd=str(raw_step.get("cwd")).strip() if raw_step.get("cwd") else None,
                    )
                )
            result[name] = WorkflowDef(
                name=name,
                description=str(item.get("description", "")).strip(),
                steps=steps,
            )
        return result

    def resolve_tool(self, name_or_alias: str) -> ToolDef:
        key = name_or_alias.strip()
        if not key:
            raise AssistantError("工具名不能为空。")
        canonical = self.alias_map.get(key, key)
        tool = self.tools.get(canonical)
        if not tool:
            raise AssistantError(f"未找到工具：{name_or_alias}")
        return tool

    def get_display_name(self, tool: ToolDef) -> str:
        rel = self.safe_relpath(tool.path)
        return f"{tool.name}  ({rel})"

    def safe_relpath(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.tools_dir.parent))
        except Exception:
            return str(path)

    def list_unregistered_files(self) -> list[Path]:
        registered_paths: set[Path] = set()
        for item in self.registry_raw.get("tools", []):
            if not isinstance(item, dict):
                continue
            path_value = str(item.get("path", "")).strip()
            if not path_value:
                continue
            path = Path(path_value)
            if not path.is_absolute():
                path = (self.tools_dir / path).resolve()
            registered_paths.add(path)

        files: list[Path] = []
        for p in sorted(self.tools_dir.iterdir(), key=lambda x: x.name.lower()):
            if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES and p.resolve() not in registered_paths:
                files.append(p.resolve())
        return files

    def _validate_new_tool_entry(self, entry: dict[str, Any], replace: bool = False) -> None:
        name = str(entry.get("name", "")).strip()
        path_value = str(entry.get("path", "")).strip()
        aliases = [str(x).strip() for x in entry.get("aliases", []) if str(x).strip()]

        if not name:
            raise AssistantError("工具 name 不能为空。")
        if not path_value:
            raise AssistantError("工具 path 不能为空。")

        path = Path(path_value)
        if not path.is_absolute():
            path = (self.tools_dir / path).resolve()
        if not path.exists():
            raise AssistantError(f"脚本不存在：{path}")

        existing_tools = [x for x in self.registry_raw.get("tools", []) if isinstance(x, dict)]
        for item in existing_tools:
            item_name = str(item.get("name", "")).strip()
            if item_name == name and not replace:
                raise AssistantError(f"注册表里已存在同名工具：{name}")
            if item_name == name and replace:
                continue

            item_path_value = str(item.get("path", "")).strip()
            item_path = Path(item_path_value)
            if item_path_value and not item_path.is_absolute():
                item_path = (self.tools_dir / item_path).resolve()
            if item_path_value and item_path.resolve() == path.resolve():
                raise AssistantError(f"注册表里已存在相同 path 的工具：{item_name} -> {item_path}")

            used_names = {item_name, *[str(a).strip() for a in item.get("aliases", []) if str(a).strip()]}
            for alias in aliases:
                if alias in used_names:
                    raise AssistantError(f"别名冲突：{alias!r} 已被工具 {item_name!r} 使用")
            if name in used_names:
                raise AssistantError(f"名称冲突：{name!r} 已作为工具 {item_name!r} 的别名存在")

    def add_tool_entry(self, entry: dict[str, Any], replace: bool = False) -> None:
        self.registry_raw.setdefault("tools", [])
        self._validate_new_tool_entry(entry, replace=replace)

        name = str(entry.get("name", "")).strip()
        new_tools: list[dict[str, Any]] = []
        replaced = False
        for item in self.registry_raw.get("tools", []):
            if isinstance(item, dict) and str(item.get("name", "")).strip() == name:
                if replace:
                    new_tools.append(entry)
                    replaced = True
                else:
                    new_tools.append(item)
            else:
                new_tools.append(item)
        if replace and not replaced:
            new_tools.append(entry)
        if not replace:
            new_tools.append(entry)

        self.registry_raw["tools"] = new_tools
        self.save_registry()
        self.reload()

    def build_command(self, tool: ToolDef, extra_args: list[str] | None = None) -> tuple[list[str], Path | None, dict[str, str]]:
        if not tool.path.exists():
            raise AssistantError(f"脚本不存在：{tool.path}")

        extra_args = extra_args or []
        args = [*tool.default_args, *extra_args]
        env = os.environ.copy()
        env.update(tool.env)

        cwd = None
        if tool.cwd:
            cwd_path = Path(tool.cwd)
            if not cwd_path.is_absolute():
                cwd_path = (self.tools_dir.parent / cwd_path).resolve()
            cwd = cwd_path

        interp = tool.interpreter or self._infer_interpreter(tool.path)
        if interp == "python":
            cmd = [sys.executable, str(tool.path), *args]
        elif interp == "bash":
            bash = shutil.which("bash")
            if not bash:
                raise AssistantError("当前环境找不到 bash，无法运行 .sh 脚本。请在 WSL/Git Bash 中运行，或为该工具指定其他解释器。")
            cmd = [bash, str(tool.path), *args]
        elif interp == "powershell":
            pwsh = shutil.which("pwsh") or shutil.which("powershell")
            if not pwsh:
                raise AssistantError("当前环境找不到 PowerShell，无法运行 .ps1 脚本。")
            cmd = [pwsh, "-ExecutionPolicy", "Bypass", "-File", str(tool.path), *args]
        elif interp == "cmd":
            if os.name != "nt":
                raise AssistantError(".bat/.cmd 脚本通常需要在 Windows 下运行；当前不是 Windows 环境。")
            cmd = [str(tool.path), *args]
        else:
            cmd = [str(tool.path), *args]

        return cmd, cwd, env

    def print_tools(self, verbose: bool = False) -> None:
        print(f"tools 目录：{self.tools_dir}")
        print(f"注册表：{self.registry_path}{'（未创建）' if not self.registry_path.exists() else ''}")
        print()
        for name in sorted(self.tools):
            tool = self.tools[name]
            aliases = ", ".join(tool.aliases) if tool.aliases else "-"
            desc = tool.description or "（无描述）"
            print(f"- {name}")
            print(f"  路径: {self.safe_relpath(tool.path)}")
            print(f"  别名: {aliases}")
            print(f"  说明: {desc}")
            if verbose:
                print(f"  解释器: {tool.interpreter or '-'}")
                print(f"  默认参数: {tool.default_args if tool.default_args else []}")
                print(f"  默认环境变量: {tool.env if tool.env else {}}")
            print()

    def print_tool_info(self, tool_name: str) -> None:
        tool = self.resolve_tool(tool_name)
        cmd, cwd, env = self.build_command(tool, [])
        print(f"名称：{tool.name}")
        print(f"路径：{tool.path}")
        print(f"别名：{', '.join(tool.aliases) if tool.aliases else '-'}")
        print(f"说明：{tool.description or '（无描述）'}")
        print(f"解释器：{tool.interpreter or '-'}")
        print(f"默认参数：{tool.default_args if tool.default_args else []}")
        print(f"工作目录：{cwd if cwd else '当前目录'}")
        extra_env = {k: v for k, v in env.items() if k in tool.env}
        print(f"默认环境变量：{extra_env if extra_env else {}}")
        print(f"示例命令：{shell_join(cmd)}")

    def print_workflows(self) -> None:
        if not self.workflows:
            print("当前没有定义 workflow。")
            return
        for name in sorted(self.workflows):
            wf = self.workflows[name]
            print(f"- {wf.name}")
            print(f"  说明: {wf.description or '（无描述）'}")
            for idx, step in enumerate(wf.steps, start=1):
                tail = " ".join(shlex.quote(x) for x in step.args) if step.args else ""
                env_text = f" env={step.env}" if step.env else ""
                print(f"  {idx}. {step.tool}{(' ' + tail) if tail else ''}{env_text}")
            print()

    def print_unregistered_files(self) -> None:
        files = self.list_unregistered_files()
        if not files:
            print("当前 tools 目录下没有未注册脚本。")
            return
        print("以下脚本已自动发现，但尚未写入 tools_registry.json：")
        print()
        for idx, path in enumerate(files, start=1):
            rel = self.safe_relpath(path)
            print(f"[{idx}] {rel}")
        print()
        print("可以用 add-tool 命令或菜单里的“新增注册表条目”把它们正式登记进去。")

    def run_tool(self, tool_name: str, extra_args: list[str], dry_run: bool = False, extra_env: dict[str, str] | None = None, cwd_override: str | None = None) -> int:
        tool = self.resolve_tool(tool_name)
        cmd, cwd, env = self.build_command(tool, extra_args)
        if extra_env:
            env.update(extra_env)
        if cwd_override:
            cwd = Path(cwd_override).expanduser().resolve()

        print(f"[运行] {self.get_display_name(tool)}")
        print(f"命令: {shell_join(cmd)}")
        print(f"工作目录: {cwd if cwd else Path.cwd()}")
        if extra_env:
            print(f"附加环境变量: {extra_env}")
        print()

        if dry_run:
            return 0

        completed = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env)
        return int(completed.returncode)

    def run_workflow(self, name: str, passthrough_args: list[str], dry_run: bool = False) -> int:
        wf = self.workflows.get(name)
        if not wf:
            raise AssistantError(f"未找到 workflow：{name}")
        if passthrough_args:
            print("注意：workflow 模式下，额外参数会附加到最后一步。")
            print()
        for idx, step in enumerate(wf.steps, start=1):
            step_args = list(step.args)
            if idx == len(wf.steps) and passthrough_args:
                step_args.extend(passthrough_args)
            print(f"===== workflow {wf.name}: step {idx}/{len(wf.steps)} =====")
            rc = self.run_tool(step.tool, step_args, dry_run=dry_run, extra_env=step.env, cwd_override=step.cwd)
            if rc != 0:
                print(f"步骤失败，返回码：{rc}")
                return rc
            print()
        return 0

    def init_registry(self, force: bool = False) -> None:
        if self.registry_path.exists() and not force:
            raise AssistantError(f"注册表已存在：{self.registry_path}\n如需覆盖，请使用 --force。")
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_path, "w", encoding="utf-8-sig") as f:
            json.dump(DEFAULT_REGISTRY, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"已写入注册表模板：{self.registry_path}")

    def prompt_add_tool_entry(self) -> None:
        print("开始新增注册表条目。留空可使用默认值；输入 q 可取消。")
        print()

        files = self.list_unregistered_files()
        chosen_path: Path | None = None
        if files:
            print("可选的未注册脚本：")
            for idx, path in enumerate(files, start=1):
                print(f"[{idx}] {self.safe_relpath(path)}")
            print("[0] 手动输入路径")
            raw = input("请选择脚本编号 [1]: ").strip()
            if raw.lower() in {"q", "quit", "exit"}:
                print("已取消。")
                return
            if not raw:
                raw = "1"
            if raw != "0":
                try:
                    idx = int(raw)
                except ValueError:
                    print("编号无效，已取消。")
                    return
                if idx < 1 or idx > len(files):
                    print("编号超出范围，已取消。")
                    return
                chosen_path = files[idx - 1]

        if chosen_path is None:
            path_text = input("请输入脚本路径（相对 tools/ 或绝对路径）: ").strip()
            if path_text.lower() in {"q", "quit", "exit"}:
                print("已取消。")
                return
            if not path_text:
                print("未输入路径，已取消。")
                return
            chosen_path = Path(path_text)
            if not chosen_path.is_absolute():
                chosen_path = (self.tools_dir / chosen_path).resolve()

        default_name = chosen_path.stem
        rel_path = self.safe_relpath(chosen_path)
        path_for_registry = chosen_path.name if chosen_path.parent.resolve() == self.tools_dir.resolve() else rel_path

        name = input(f"工具名 [{default_name}]: ").strip()
        if name.lower() in {"q", "quit", "exit"}:
            print("已取消。")
            return
        if not name:
            name = default_name

        description = input("说明（可留空）: ").strip()
        if description.lower() in {"q", "quit", "exit"}:
            print("已取消。")
            return

        aliases_text = input("别名（逗号分隔，可留空）: ").strip()
        if aliases_text.lower() in {"q", "quit", "exit"}:
            print("已取消。")
            return
        aliases = [x.strip() for x in aliases_text.split(",") if x.strip()] if aliases_text else []

        default_args_text = input("默认参数（按 shell 风格输入，可留空）: ").strip()
        if default_args_text.lower() in {"q", "quit", "exit"}:
            print("已取消。")
            return
        default_args = shlex.split(default_args_text) if default_args_text else []

        interpreter_default = self._infer_interpreter(chosen_path) or ""
        interpreter = input(f"解释器 [自动推断: {interpreter_default or '无'}]（可留空）: ").strip()
        if interpreter.lower() in {"q", "quit", "exit"}:
            print("已取消。")
            return
        interpreter = interpreter or None

        entry: dict[str, Any] = {
            "name": name,
            "path": path_for_registry,
            "description": description,
            "aliases": aliases,
            "default_args": default_args,
        }
        if interpreter:
            entry["interpreter"] = interpreter

        print()
        print("即将写入以下条目：")
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        confirm = input("确认写入？[Y/n]: ").strip().lower()
        if confirm in {"n", "no"}:
            print("已取消。")
            return

        self.add_tool_entry(entry, replace=False)
        print(f"已新增工具条目：{name}")
        print(f"注册表位置：{self.registry_path}")

    def interactive_menu(self) -> int:
        while True:
            print("=" * 72)
            print("Yumemi-Bot tools 助手")
            print(f"项目 tools 目录: {self.tools_dir}")
            print()
            print("[1] 列出所有工具")
            print("[2] 列出所有 workflow")
            print("[3] 查看工具详情")
            print("[4] 运行某个工具")
            print("[5] 运行某个 workflow")
            print("[6] 新增注册表条目")
            print("[7] 查看未注册脚本")
            print("[8] 生成/覆盖注册表模板")
            print("[q] 退出")
            choice = input("请选择: ").strip().lower()
            print()

            if choice in {"q", "quit", "exit"}:
                print("已退出。")
                return 0

            if choice == "1":
                self.print_tools(verbose=False)
                continue

            if choice == "2":
                self.print_workflows()
                continue

            if choice == "3":
                name = input("请输入工具名/别名/文件名: ").strip()
                if not name:
                    print("未输入工具名。\n")
                    continue
                self.print_tool_info(name)
                print()
                continue

            if choice == "4":
                name = input("请输入工具名/别名/文件名: ").strip()
                if not name:
                    print("未输入工具名。\n")
                    continue
                arg_line = input("请输入额外参数（可留空，按 shell 风格分词）: ").strip()
                dry = input("是否 dry-run？[y/N]: ").strip().lower() in {"y", "yes"}
                rc = self.run_tool(name, shlex.split(arg_line), dry_run=dry)
                print(f"返回码: {rc}\n")
                continue

            if choice == "5":
                name = input("请输入 workflow 名称: ").strip()
                if not name:
                    print("未输入 workflow 名称。\n")
                    continue
                arg_line = input("附加到最后一步的额外参数（可留空）: ").strip()
                dry = input("是否 dry-run？[y/N]: ").strip().lower() in {"y", "yes"}
                rc = self.run_workflow(name, shlex.split(arg_line), dry_run=dry)
                print(f"返回码: {rc}\n")
                continue

            if choice == "6":
                self.prompt_add_tool_entry()
                print()
                continue

            if choice == "7":
                self.print_unregistered_files()
                print()
                continue

            if choice == "8":
                force = input("若已存在是否覆盖？[y/N]: ").strip().lower() in {"y", "yes"}
                self.init_registry(force=force)
                print()
                continue

            print("无效选项，请重试。\n")


def shell_join(cmd: list[str]) -> str:
    return " ".join(shlex.quote(x) for x in cmd)


def parse_key_value_pairs(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise AssistantError(f"环境变量格式错误：{item!r}，应写成 KEY=VALUE")
        k, v = item.split("=", 1)
        k = k.strip()
        if not k:
            raise AssistantError(f"环境变量名不能为空：{item!r}")
        result[k] = v
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Yumemi-Bot tools 助手：统一列出、查询、运行 tools 目录下的脚本，并支持 workflow。",
        epilog=(
            "常用示例:\n"
            "  python tools/tools_assistant.py\n"
            "  python tools/tools_assistant.py menu\n"
            "  python tools/tools_assistant.py list\n"
            "  python tools/tools_assistant.py unregistered\n"
            "  python tools/tools_assistant.py add-tool\n"
            "  python tools/tools_assistant.py run import-images -- --apply\n"
            "  python tools/tools_assistant.py workflow images-push\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--registry", default=None, help=f"注册表路径。默认是 tools/{DEFAULT_REGISTRY_NAME}")

    subparsers = parser.add_subparsers(dest="command")

    p_init = subparsers.add_parser("init-registry", help="生成一个可编辑的 tools_registry.json 模板")
    p_init.add_argument("--force", action="store_true", help="若注册表已存在，则覆盖。")

    p_list = subparsers.add_parser("list", help="列出当前可用工具")
    p_list.add_argument("--verbose", action="store_true", help="显示解释器、默认参数等详细信息。")

    subparsers.add_parser("workflows", help="列出当前定义的 workflows")
    subparsers.add_parser("menu", help="进入交互式菜单")
    subparsers.add_parser("unregistered", help="列出 tools 目录中尚未写入注册表的脚本")

    p_add = subparsers.add_parser("add-tool", help="向 tools_registry.json 追加一个工具条目")
    p_add.add_argument("--path", default=None, help="脚本路径；相对路径默认相对于 tools/。不填则进入交互选择。")
    p_add.add_argument("--name", default=None, help="工具名；默认取脚本 stem。")
    p_add.add_argument("--description", default="", help="工具说明。")
    p_add.add_argument("--alias", action="append", default=[], help="工具别名，可重复使用。")
    p_add.add_argument("--default-arg", action="append", default=[], help="默认参数，可重复使用。")
    p_add.add_argument("--interpreter", default=None, help="解释器；如 python/bash/powershell/cmd。")

    p_info = subparsers.add_parser("info", help="查看某个工具的详细信息")
    p_info.add_argument("tool", help="工具名、别名、文件名或文件 stem")

    p_run = subparsers.add_parser("run", help="运行某个工具")
    p_run.add_argument("tool", help="工具名、别名、文件名或文件 stem")
    p_run.add_argument("args", nargs=argparse.REMAINDER, help="传给该工具的额外参数；若以 -- 开头，建议写成 run tool -- ...")
    p_run.add_argument("--dry-run", action="store_true", help="只打印命令，不实际执行。")
    p_run.add_argument("--cwd", default=None, help="临时覆盖工作目录。")
    p_run.add_argument("--env", action="append", default=[], help="临时附加环境变量，格式 KEY=VALUE，可多次使用。")

    p_wf = subparsers.add_parser("workflow", help="按预定义步骤连续运行多个工具")
    p_wf.add_argument("name", help="workflow 名称")
    p_wf.add_argument("args", nargs=argparse.REMAINDER, help="附加到 workflow 最后一步的额外参数")
    p_wf.add_argument("--dry-run", action="store_true", help="只打印命令，不实际执行。")

    return parser


def strip_remainder_leading_dashdash(values: list[str]) -> list[str]:
    if values and values[0] == "--":
        return values[1:]
    return values


def main() -> int:
    parser = build_parser()
    if len(sys.argv) == 1:
        parser.print_help()
        return 0

    args = parser.parse_args()

    try:
        if not args.command:
            parser.print_help()
            return 0

        assistant = ToolsAssistant.from_script_location(Path(__file__), registry_override=args.registry)

        if args.command == "init-registry":
            assistant.init_registry(force=args.force)
            return 0

        if args.command == "list":
            assistant.print_tools(verbose=args.verbose)
            return 0

        if args.command == "workflows":
            assistant.print_workflows()
            return 0

        if args.command == "menu":
            return assistant.interactive_menu()

        if args.command == "unregistered":
            assistant.print_unregistered_files()
            return 0

        if args.command == "add-tool":
            if not args.path:
                assistant.prompt_add_tool_entry()
                return 0
            path = Path(args.path)
            if not path.is_absolute():
                path = (assistant.tools_dir / path).resolve()
            entry: dict[str, Any] = {
                "name": args.name or path.stem,
                "path": path.name if path.parent.resolve() == assistant.tools_dir.resolve() else assistant.safe_relpath(path),
                "description": args.description or "",
                "aliases": list(args.alias),
                "default_args": list(args.default_arg),
            }
            if args.interpreter:
                entry["interpreter"] = args.interpreter
            assistant.add_tool_entry(entry, replace=False)
            print(f"已新增工具条目：{entry['name']}")
            print(f"注册表位置：{assistant.registry_path}")
            return 0

        if args.command == "info":
            assistant.print_tool_info(args.tool)
            return 0

        if args.command == "run":
            extra_args = strip_remainder_leading_dashdash(args.args)
            extra_env = parse_key_value_pairs(args.env)
            return assistant.run_tool(args.tool, extra_args, dry_run=args.dry_run, extra_env=extra_env, cwd_override=args.cwd)

        if args.command == "workflow":
            extra_args = strip_remainder_leading_dashdash(args.args)
            return assistant.run_workflow(args.name, extra_args, dry_run=args.dry_run)

        raise AssistantError(f"未知命令：{args.command}")
    except AssistantError as e:
        print(f"错误：{e}")
        return 2
    except KeyboardInterrupt:
        print("\n已取消。")
        return 130
    except Exception as e:
        print(f"未处理异常：{e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
