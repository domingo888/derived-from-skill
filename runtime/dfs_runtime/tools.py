"""内置安全工具集。

设计原则：
1. 默认白名单为空，制品必须显式声明 tools 才能使用；
2. 文件类工具只能落在制品目录或本次运行目录内，禁止路径穿越；
3. 不提供 shell、网络、删除类工具。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from pathlib import Path


class ToolError(Exception):
    pass


def _safe_path(base: Path, relative: str) -> Path:
    candidate = (base / relative).resolve()
    if candidate != base and base not in candidate.parents:
        raise ToolError(f"路径越出允许范围: {relative}")
    return candidate


def tool_now(args: dict, capsule, run_dir: Path) -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def tool_sha256(args: dict, capsule, run_dir: Path) -> str:
    text = args.get("text")
    if not isinstance(text, str):
        raise ToolError("sha256 需要参数 text（string）")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tool_read_text(args: dict, capsule, run_dir: Path) -> str:
    relative = args.get("path")
    if not isinstance(relative, str) or not relative:
        raise ToolError("read_text 需要参数 path（string）")
    path = _safe_path(capsule.root, relative)
    if not path.exists():
        raise ToolError(f"文件不存在: {relative}")
    return path.read_text(encoding="utf-8")


def tool_write_text(args: dict, capsule, run_dir: Path) -> str:
    relative = args.get("path")
    content = args.get("content")
    if not isinstance(relative, str) or not relative:
        raise ToolError("write_text 需要参数 path（string）")
    if not isinstance(content, str):
        raise ToolError("write_text 需要参数 content（string）")
    path = _safe_path(run_dir / "artifacts", relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def tool_count_lines(args: dict, capsule, run_dir: Path) -> int:
    relative = args.get("path")
    if not isinstance(relative, str) or not relative:
        raise ToolError("count_lines 需要参数 path（string）")
    path = _safe_path(capsule.root, relative)
    if not path.exists():
        raise ToolError(f"文件不存在: {relative}")
    return len(path.read_text(encoding="utf-8").splitlines())


REGISTRY = {
    "now": tool_now,
    "sha256": tool_sha256,
    "read_text": tool_read_text,
    "write_text": tool_write_text,
    "count_lines": tool_count_lines,
}


def run_tool(name: str, args: dict, capsule, run_dir: Path):
    if name not in REGISTRY:
        raise ToolError(f"未注册的工具: {name}（可用: {', '.join(sorted(REGISTRY))}）")
    return REGISTRY[name](args, capsule, run_dir)
