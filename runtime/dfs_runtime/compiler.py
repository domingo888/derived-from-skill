"""编译层：Skill 规约 → 运行计划（plan.json）。

这是 DFS 唯一允许模型决定「流程怎么走」的阶段。
产出物必须通过 plan schema 与制品契约校验，任何越界即失败。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from .adapters import BaseAdapter, MockAdapter
from .manifest import Capsule, ContractError, load_schema
from .validation import validate_json

SYSTEM_PROMPT = """你是 DFS（Derived From Skill）的编译器。

你的唯一职责：把给定的 Skill 规约编译成一份可执行的运行计划（JSON）。

硬性规则：
1. 只输出一个 JSON 对象，不要输出解释、不要用 Markdown 代码块。
2. 计划必须完全遵循给定的 plan schema。
3. 步骤数量不得超过 max_steps。
4. 只能使用 tools_whitelist 中列出的工具；白名单为空时不得产生 tool 步骤。
5. 不要在计划中新增规约未要求的任务，不要引入规约之外的领域知识。
6. 每个 llm 步骤只做一件事，提示词中必须包含完成该步骤所需的全部信息。
7. 输出映射必须能产出 output_schema 要求的全部必填字段。
8. 无法在规约内完成时，输出一个只包含说明字段的对象：{"error": "原因"}。
"""


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ContractError(f"编译器未返回 JSON 对象: {cleaned[:200]}")
    candidate = cleaned[start : end + 1]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ContractError(f"编译器返回的 JSON 不合法: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError("编译器返回的顶层必须是 JSON 对象")
    return value


def validate_plan(plan: dict, capsule: Capsule) -> None:
    """计划与制品契约的一致性校验，全部 fail closed。"""
    try:
        validate_json(load_schema("plan.schema.json"), plan, "plan")
    except ValueError as exc:
        raise ContractError(f"plan 不符合 schema: {exc}") from exc

    if plan.get("capsule") != capsule.name:
        raise ContractError(f"plan.capsule={plan.get('capsule')!r} 与制品名 {capsule.name!r} 不一致")

    steps = plan.get("steps") or []
    if len(steps) > capsule.max_steps:
        raise ContractError(f"计划步骤数 {len(steps)} 超过 runtime.max_steps={capsule.max_steps}")

    seen: set[str] = set()
    for step in steps:
        step_id = step["id"]
        if step_id in seen:
            raise ContractError(f"步骤 id 重复: {step_id}")
        seen.add(step_id)
        if step["kind"] == "tool":
            if step["tool"] not in capsule.tools:
                raise ContractError(
                    f"计划使用了白名单外的工具 {step['tool']!r}（白名单: {capsule.tools or '空'}）"
                )

    for produced in [step.get("output") for step in steps if step.get("output")]:
        if produced in seen:
            raise ContractError(f"步骤输出名与步骤 id 冲突: {produced}")

    digest = plan.get("source_digest")
    if digest and digest != capsule.source_digest:
        raise ContractError(
            "计划编译时使用的规约与当前规约不一致（source_digest 不匹配），请重新 build"
        )


def build_plan(capsule: Capsule, adapter: BaseAdapter) -> dict:
    if isinstance(adapter, MockAdapter):
        raise ContractError(
            "provider=mock 不能用于 build：mock 只做离线回放。"
            "请改用 --provider openai-compatible 并提供端点与 Key"
        )

    plan_schema = load_schema("plan.schema.json")
    craft = {
        "capsule": capsule.name,
        "version": capsule.version,
        "max_steps": capsule.max_steps,
        "tools_whitelist": capsule.tools,
        "input_schema": capsule.input_schema,
        "output_schema": capsule.output_schema,
    }

    user_prompt = "\n\n".join(
        [
            "## 制品契约",
            "```json\n" + json.dumps(craft, ensure_ascii=False, indent=2) + "\n```",
            "## plan schema",
            "```json\n" + json.dumps(plan_schema, ensure_ascii=False, indent=2) + "\n```",
            "## Skill 规约",
            capsule.skill_text,
        ]
    )

    raw = adapter.chat(SYSTEM_PROMPT, user_prompt)
    plan = _extract_json(raw)

    if "error" in plan and "steps" not in plan:
        raise ContractError(f"编译器拒绕编译: {plan['error']}")

    plan.setdefault("source_digest", capsule.source_digest)
    described = adapter.describe()
    plan.setdefault(
        "compiled_by",
        {
            "provider": described.get("provider"),
            "model": described.get("model") or capsule.data["model"].get("model"),
            "mode": "model",
        },
    )
    plan.setdefault("notes", f"compiled at {datetime.now(timezone.utc).isoformat(timespec='seconds')}")

    validate_plan(plan, capsule)
    return plan
