"""命令行入口：validate / inspect / build / run / serve / window / model / new。"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .adapters import AdapterError, build_adapter
from .compiler import build_plan, validate_plan
from .executor import RunError, _sha256
from .manifest import (
    LOCAL_OVERRIDE_NAME,
    ContractError,
    _mask,
    load_capsule,
    load_plan,
    read_json,
)
from .runner import run_once

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "template"


def _git_user() -> str:
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return (result.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _print_json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def cmd_validate(args: argparse.Namespace) -> int:
    capsule = load_capsule(args.capsule)
    print(f"[ok] 制品契约通过: {capsule.name}（{capsule.title}）v{capsule.version}")
    for skill in capsule.skills:
        upstream = skill.provenance.get("upstream_url") or "-"
        license_name = skill.provenance.get("license") or "-"
        print(f"     来源      : {skill.name} ← {skill.origin}（upstream={upstream}, license={license_name}）")
    model = capsule.resolve_model()
    key_state = "空 Key（auth=none）" if model.get("auth") == "none" else _mask(model.get("api_key"))
    print(f"     模型绑定  : {model.get('provider')} / {model.get('model')} @ {model.get('base_url') or '-'}")
    print(f"     鉴权      : auth={model.get('auth')}，Key={key_state}")
    print(f"     UI        : kind={capsule.ui['kind']}（{capsule.ui['title']}）")
    print(f"     步骤上限  : {capsule.max_steps}    工具白名单: {capsule.tools or '空'}")
    print(f"     规约摘要  : {capsule.source_digest[:22]}…")

    plan_path = capsule.root / "plan.json"
    if plan_path.exists():
        plan = load_plan(plan_path)
        validate_plan(plan, capsule)
        print(f"[ok] 运行计划通过: {len(plan['steps'])} 步 → {', '.join(s['id'] for s in plan['steps'])}")
    else:
        print("[--] 未找到 plan.json，运行前需先 build")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    capsule = load_capsule(args.capsule)
    _print_json(capsule.summary())
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    capsule = load_capsule(args.capsule)
    overrides = {
        "provider": args.provider,
        "model": args.model,
        "base_url": args.base_url,
        "auth": args.auth,
    }
    model_cfg = capsule.resolve_model(overrides)
    adapter = build_adapter(model_cfg, timeout_s=capsule.timeout_s)
    plan = build_plan(capsule, adapter)

    out_path = Path(args.out).expanduser().resolve() if args.out else capsule.root / "plan.json"
    out_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[ok] 编译完成 → {out_path}")
    print(f"     步骤 {len(plan['steps'])}: {', '.join(s['id'] for s in plan['steps'])}")
    print(f"     plan 摘要: {_sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True))[:22]}…")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    capsule = load_capsule(args.capsule)
    input_path = (
        Path(args.input).expanduser().resolve()
        if args.input
        else capsule.root / "input.example.json"
    )
    if not input_path.exists():
        raise ContractError(f"缺少输入文件: {input_path}（用 --input 指定）")
    input_data = read_json(input_path)

    result = run_once(capsule.root, input_data, plan_path=args.plan)
    print(f"[ok] 执行完成: {capsule.name}")
    print(f"     运行目录: {result['run_dir']}")
    print("     输出:")
    _print_json(result["output"])
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .webui import serve

    capsule = load_capsule(args.capsule)
    if capsule.ui["kind"] != "web":
        print(f"[warn] 该制品 ui.kind={capsule.ui['kind']}，仍按 Web 方式启动", file=sys.stderr)
    if capsule.ui.get("entry"):
        print(f"[warn] ui.entry={capsule.ui['entry']}：内置 Web UI 只提供 schema 驱动表单，自定义页面暂未接入", file=sys.stderr)

    host = args.host or capsule.ui["host"]
    port = args.port or int(capsule.ui["port"])
    serve(capsule.root, host=host, port=port, open_browser=args.open)
    return 0


def cmd_window(args: argparse.Namespace) -> int:
    from .appwindow import find_browser, open_window as open_app_window
    from .winui import check_available, open_window as open_native_window

    native_ok, native_detail = check_available()
    browser = find_browser()

    if args.check:
        print(f"[{'ok' if browser else '--'}] 窗口模式（app 窗口）: {browser or '未找到 Edge/Chrome，将退回默认浏览器'}")
        print(f"[{'ok' if native_ok else '--'}] 窗口模式（native tkinter）: {native_detail}")
        return 0 if (browser or native_ok) else 6

    capsule = load_capsule(args.capsule)
    if capsule.ui["kind"] != "window":
        print(f"[warn] 该制品 ui.kind={capsule.ui['kind']}，仍按窗口方式启动", file=sys.stderr)

    if args.native:
        if not native_ok:
            raise ContractError(f"native 窗口不可用: {native_detail}（可用默认 app 窗口模式）")
        open_native_window(capsule.root)
        return 0

    open_app_window(capsule.root, width=capsule.ui["width"], height=capsule.ui["height"])
    return 0


def cmd_model(args: argparse.Namespace) -> int:
    capsule = load_capsule(args.capsule)
    path = capsule.root / LOCAL_OVERRIDE_NAME

    changes = {
        "provider": args.provider,
        "model": args.model,
        "base_url": args.base_url,
        "auth": args.auth,
        "api_key": args.api_key,
    }
    has_change = any(value is not None for value in changes.values()) or args.clear

    if args.show or not has_change:
        model = capsule.resolve_model()
        _print_json(
            {
                "provider": model.get("provider"),
                "model": model.get("model"),
                "base_url": model.get("base_url", ""),
                "auth": model.get("auth"),
                "api_key": _mask(model.get("api_key")),
                "temperature": model.get("temperature"),
                "max_tokens": model.get("max_tokens"),
                "override_file": str(path) + ("（存在）" if path.exists() else "（未创建）"),
            }
        )
        print("     优先级: CLI 参数 > 环境变量(DFS_*) > dfs.local.json > dfs.json")
        return 0

    local = dict(capsule.local or {})
    model_cfg = {} if args.clear else dict(local.get("model") or {})
    for key, value in changes.items():
        if value is not None:
            model_cfg[key] = value

    if model_cfg:
        local["model"] = model_cfg
    else:
        local.pop("model", None)

    path.write_text(json.dumps(local, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[ok] 已写入本地模型设置: {path}")
    print("     该文件已被 .gitignore 排除，不会进入仓库；API Key 也不写入 dfs.json")
    effective = capsule.resolve_model()
    print(f"     生效配置: {effective.get('provider')} / {effective.get('model')}，auth={effective.get('auth')}")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    target = Path(args.parent).expanduser().resolve() / args.name
    if target.exists():
        raise ContractError(f"目标已存在: {target}")
    if not TEMPLATE_DIR.is_dir():
        raise ContractError(f"找不到模板目录: {TEMPLATE_DIR}")

    shutil.copytree(TEMPLATE_DIR, target)
    author = _git_user() or "unknown"
    today = datetime.now().date().isoformat()
    for path in target.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        text = (
            text.replace("__CAPSULE__", args.name)
            .replace("__TITLE__", args.title)
            .replace("__UI_KIND__", args.ui)
            .replace("__AUTHOR__", author)
            .replace("__TODAY__", today)
        )
        path.write_text(text, encoding="utf-8")

    print(f"[ok] 已创建制品骨架: {target}")
    print("     下一步：填 source.provenance → 写 SKILL.md 与 dfs.json → validate → build → run/serve/window")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dfs",
        description="DFS（Derived From Skill）最小运行时：把 Skill 规约编译成独立可运行的制品",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="校验制品契约（含来源声明与 UI 声明）")
    p_validate.add_argument("capsule", help="制品目录")
    p_validate.set_defaults(func=cmd_validate)

    p_inspect = sub.add_parser("inspect", help="输出制品摘要")
    p_inspect.add_argument("capsule", help="制品目录")
    p_inspect.set_defaults(func=cmd_inspect)

    p_build = sub.add_parser("build", help="编译 Skill 规约为运行计划")
    p_build.add_argument("capsule", help="制品目录")
    p_build.add_argument("--out", help="计划输出路径（默认 <制品>/plan.json）")
    p_build.add_argument("--provider", help="覆盖 model.provider")
    p_build.add_argument("--model", help="覆盖 model.model")
    p_build.add_argument("--base-url", dest="base_url", help="覆盖 model.base_url")
    p_build.add_argument("--auth", choices=["bearer", "none"], help="覆盖 model.auth")
    p_build.set_defaults(func=cmd_build)

    p_run = sub.add_parser("run", help="执行制品")
    p_run.add_argument("capsule", help="制品目录")
    p_run.add_argument("--input", help="输入 JSON（默认 input.example.json）")
    p_run.add_argument("--plan", help="计划文件（默认 <制品>/plan.json）")
    p_run.set_defaults(func=cmd_run)

    p_serve = sub.add_parser("serve", help="启动该制品的独立 Web UI")
    p_serve.add_argument("capsule", help="制品目录")
    p_serve.add_argument("--host", help="监听地址（默认取 ui.host，即 127.0.0.1）")
    p_serve.add_argument("--port", type=int, help="端口（默认取 ui.port）")
    p_serve.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    p_serve.set_defaults(func=cmd_serve)

    p_window = sub.add_parser("window", help="启动该制品的独立窗口 UI（app 窗口，或 --native 用 tkinter）")
    p_window.add_argument("capsule", nargs="?", help="制品目录")
    p_window.add_argument("--check", action="store_true", help="仅检测窗口能力是否可用")
    p_window.add_argument("--native", action="store_true", help="使用 tkinter 原生窗口（需系统 Tcl/Tk）")
    p_window.set_defaults(func=cmd_window)

    p_model = sub.add_parser("model", help="查看或手动设置该制品的模型（写入 dfs.local.json）")
    p_model.add_argument("capsule", help="制品目录")
    p_model.add_argument("--show", action="store_true", help="显示当前生效配置")
    p_model.add_argument("--provider", choices=["openai-compatible", "mock"])
    p_model.add_argument("--model")
    p_model.add_argument("--base-url", dest="base_url")
    p_model.add_argument("--auth", choices=["bearer", "none"])
    p_model.add_argument("--api-key", dest="api_key", help="写入本地覆盖文件（不会入库）")
    p_model.add_argument("--clear", action="store_true", help="清除本地模型覆盖")
    p_model.set_defaults(func=cmd_model)

    p_new = sub.add_parser("new", help="从模板新建制品")
    p_new.add_argument("name", help="制品名（小写字母、数字、连字符）")
    p_new.add_argument("--title", default="新建 DFS 制品", help="人类可读标题")
    p_new.add_argument("--ui", choices=["web", "window", "none"], default="web", help="UI 形态")
    p_new.add_argument("--parent", default="subprojects", help="创建位置（默认 ./subprojects）")
    p_new.set_defaults(func=cmd_new)

    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "command", None) == "window" and not args.check and not args.capsule:
        parser.error("window 需要提供制品目录，或使用 --check")
    try:
        return args.func(args)
    except ContractError as exc:
        print(f"[fail] 契约校验失败: {exc}", file=sys.stderr)
        return 2
    except RunError as exc:
        print(f"[fail] 执行失败: {exc}", file=sys.stderr)
        return 3
    except AdapterError as exc:
        print(f"[fail] 模型调用失败: {exc}", file=sys.stderr)
        return 4
    except FileNotFoundError as exc:
        print(f"[fail] 文件不存在: {exc}", file=sys.stderr)
        return 5
    except OSError as exc:
        print(f"[fail] 系统层失败: {exc}", file=sys.stderr)
        return 7
