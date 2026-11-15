"""单次运行封装：CLI / Web UI / 窗口 UI 共用同一条执行路径。

三种入口必须走同一套契约与证据逻辑，避免「UI 能跑、CLI 不能跑」的分叉。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .adapters import build_adapter
from .compiler import validate_plan
from .executor import _sha256, execute
from .manifest import ContractError, load_capsule, load_plan

import json


def _plan_digest(plan: dict) -> str:
    return _sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True))[len("sha256:") :][:8]


def run_once(root: str | Path, input_data: dict, plan_path: str | Path | None = None) -> dict:
    capsule = load_capsule(root)
    plan_file = Path(plan_path).expanduser().resolve() if plan_path else capsule.root / "plan.json"
    if not plan_file.exists():
        raise ContractError(f"缺少运行计划: {plan_file}（先执行 dfs build，或使用离线示例计划）")

    plan = load_plan(plan_file)
    validate_plan(plan, capsule)

    adapter = build_adapter(capsule.resolve_model(), timeout_s=capsule.timeout_s)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = capsule.root / "runs" / f"{stamp}-{_plan_digest(plan)}"

    result = execute(capsule, plan, input_data, adapter, run_dir)
    result["capsule"] = capsule.name
    return result
