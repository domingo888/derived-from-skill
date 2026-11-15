"""运行层：按 plan 确定性执行，并落盘证据。

运行期不做任何「重新规划」：流程结构由 plan 固化，
模型只在 llm 步骤内做节点推理。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from .adapters import BaseAdapter, MockAdapter
from .manifest import Capsule, ContractError
from .tools import ToolError, run_tool
from .validation import validate_json

PLACEHOLDER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


class RunError(Exception):
    """执行期失败：中止后续步骤，已完成步骤的证据保留。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _walk(value, dotted: str):
    node = value
    for part in [p for p in dotted.split(".") if p]:
        if isinstance(node, dict):
            if part not in node:
                raise RunError(f"上下文中不存在字段: {part}")
            node = node[part]
        elif isinstance(node, list):
            if not part.isdigit() or int(part) >= len(node):
                raise RunError(f"无法在数组上取索引: {part}")
            node = node[int(part)]
        else:
            raise RunError(f"无法在 {type(node).__name__} 上取字段: {part}")
    return node


def resolve(ref: str, context: dict):
    ref = ref.strip()
    if ref == "input":
        return context["input"]
    if ref.startswith("input."):
        return _walk(context["input"], ref[len("input.") :])
    if ref == "output_schema":
        return context["output_schema"]
    step_id, dot, rest = ref.partition(".")
    if step_id not in context["steps"]:
        raise RunError(f"引用了尚未产生的步骤: {step_id}")
    return _walk(context["steps"][step_id], rest) if dot else context["steps"][step_id]


def render_text(template: str, context: dict) -> str:
    def substitute(match: re.Match) -> str:
        value = resolve(match.group(1), context)
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    return PLACEHOLDER.sub(substitute, template)


def render_value(value, context: dict):
    if isinstance(value, str):
        whole = PLACEHOLDER.fullmatch(value.strip())
        if whole:
            return resolve(whole.group(1), context)
        return render_text(value, context)
    if isinstance(value, dict):
        return {key: render_value(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [render_value(item, context) for item in value]
    return value


_OPS = {"nonempty", "contains", "regex", "keys", "equals", "len_max"}


def run_check(step: dict, context: dict) -> bool:
    op = step["op"]
    if op not in _OPS:
        raise RunError(f"未知 check op: {op}")
    value = resolve(step["ref"], context)
    expected = render_value(step["value"], context) if "value" in step else None

    if op == "nonempty":
        passed = value not in (None, "", [], {})
    elif op == "contains":
        passed = str(expected) in str(value)
    elif op == "regex":
        passed = re.search(str(expected), str(value)) is not None
    elif op == "keys":
        wanted = expected if isinstance(expected, list) else [expected]
        passed = isinstance(value, dict) and all(key in value for key in wanted)
    elif op == "equals":
        passed = value == expected
    elif op == "len_max":
        try:
            passed = len(value) <= int(expected)
        except (TypeError, ValueError):
            raise RunError("len_max 的 value 必须是整数")
    else:  # pragma: no cover - 已被 _OPS 拦截
        passed = False

    if not passed:
        raise RunError(f"步骤 {step['id']} 校验失败（op={op}, ref={step['ref']}）")
    return True


def run_llm(step: dict, context: dict, adapter: BaseAdapter) -> str:
    prompt = render_text(step["prompt"], context)
    system = step.get("system") or ""

    if isinstance(adapter, MockAdapter):
        if "mock_output" not in step:
            raise RunError(
                f"mock 回放模式下步骤 {step['id']} 缺少 mock_output；"
                "真实执行请改用绑定模型"
            )
        raw = step["mock_output"]
        text = render_text(raw, context) if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
    else:
        text = adapter.chat(system, prompt)

    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False)
    return text


def execute(capsule: Capsule, plan: dict, input_data: dict, adapter: BaseAdapter, run_dir: Path) -> dict:
    try:
        validate_json(capsule.input_schema, input_data, "input")
    except ValueError as exc:
        raise ContractError(f"输入不符合 input_schema: {exc}") from exc

    run_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    evidence_path = run_dir / "evidence.jsonl"

    plan_digest = _sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True))
    meta = {
        "capsule": capsule.name,
        "version": capsule.version,
        "plan_digest": plan_digest,
        "source_digest": capsule.source_digest,
        "adapter": adapter.describe(),
        "started_at": _now(),
        "input_digest": _sha256(json.dumps(input_data, ensure_ascii=False, sort_keys=True)),
    }
    (run_dir / "run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    context = {"input": input_data, "steps": {}, "output_schema": capsule.output_schema}

    def log(record: dict) -> None:
        with evidence_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def finish(status: str, payload: dict) -> None:
        body = {"status": status, **payload, "finished_at": _now()}
        (run_dir / "result.json").write_text(
            json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    for step in plan["steps"]:
        step_id = step["id"]
        kind = step["kind"]
        started = time.perf_counter()
        record = {"step": step_id, "kind": kind, "ts": _now()}
        try:
            if kind == "llm":
                value = run_llm(step, context, adapter)
                (artifacts_dir / f"{step_id}.txt").write_text(value, encoding="utf-8")
                record["prompt_sha256"] = _sha256(render_text(step["prompt"], context))
            elif kind == "check":
                value = run_check(step, context)
            elif kind == "tool":
                if step["tool"] not in capsule.tools:
                    raise RunError(f"工具 {step['tool']} 不在白名单内")
                args = render_value(step["args"], context)
                value = run_tool(step["tool"], args, capsule, run_dir)
                record["tool"] = step["tool"]
            else:  # pragma: no cover - schema 已拦截
                raise RunError(f"未知步骤类型: {kind}")
        except (RunError, ToolError, ContractError) as exc:
            record.update({"status": "error", "error": str(exc)[:300],
                           "duration_ms": int((time.perf_counter() - started) * 1000)})
            log(record)
            finish("error", {"failed_step": step_id, "error": str(exc)})
            raise RunError(f"制品 {capsule.name} 在步骤 {step_id} 失败: {exc}") from exc
        except Exception as exc:  # 模型端点等外部异常
            record.update({"status": "error", "error": str(exc)[:300],
                           "duration_ms": int((time.perf_counter() - started) * 1000)})
            log(record)
            finish("error", {"failed_step": step_id, "error": str(exc)})
            raise RunError(f"制品 {capsule.name} 在步骤 {step_id} 失败: {exc}") from exc

        if step.get("output"):
            context["steps"][step["output"]] = value
        record.update(
            {
                "status": "ok",
                "duration_ms": int((time.perf_counter() - started) * 1000),
                "output_sha256": _sha256(json.dumps(value, ensure_ascii=False, sort_keys=True)),
            }
        )
        log(record)

    output = render_value(plan["output"], context)
    try:
        validate_json(capsule.output_schema, output, "output")
    except ValueError as exc:
        finish("output_invalid", {"output": output, "error": str(exc)})
        raise RunError(f"输出不符合 output_schema: {exc}") from exc

    finish("ok", {"output": output})
    return {"output": output, "run_dir": str(run_dir)}
