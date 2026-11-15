"""内置 Web UI：每个制品自带一份独立界面，零依赖，仅绑定本机回环地址。

规范：
1. 表单由 io.input_schema 推导，不手写字段；
2. 运行走与 CLI 相同的 runner.run_once，证据落盘位置一致；
3. 默认 127.0.0.1，不对外网暴露；
4. 允许空 API Key（auth=none 的本地端点可直接在界面里跑）。
"""

from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .manifest import ContractError, load_capsule
from .runner import run_once
from .uigen import coerce_input, default_values, describe_fields

PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · DFS</title>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin: 0; font: 14px/1.6 -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
         background: #f6f7f9; color: #1f2328; }
  .wrap { max-width: 780px; margin: 0 auto; padding: 28px 20px 60px; }
  header { border-bottom: 1px solid #e3e6ea; padding-bottom: 14px; margin-bottom: 18px; }
  h1 { font-size: 20px; margin: 0 0 6px; letter-spacing: .2px; }
  .meta { color: #6b7280; font-size: 12.5px; }
  .badge { display: inline-block; padding: 1px 8px; border-radius: 999px; background: #eef1f5;
           color: #374151; font-size: 12px; margin-right: 6px; }
  .card { background: #fff; border: 1px solid #e3e6ea; border-radius: 10px; padding: 18px 20px; }
  .field { margin-bottom: 14px; }
  .field label { display: block; font-weight: 600; margin-bottom: 5px; font-size: 13px; }
  .req { color: #b42318; margin-left: 3px; }
  .hint { color: #8a9199; font-size: 12px; margin-top: 4px; }
  input[type=text], input[type=number], select, textarea {
    width: 100%; padding: 8px 10px; border: 1px solid #d5d9df; border-radius: 7px;
    font: inherit; background: #fff; }
  textarea { min-height: 84px; resize: vertical; }
  input[type=checkbox] { width: 16px; height: 16px; }
  button { margin-top: 8px; padding: 9px 18px; border: 0; border-radius: 8px;
           background: #1f2937; color: #fff; font: inherit; cursor: pointer; }
  button:disabled { opacity: .55; cursor: default; }
  .out { margin-top: 16px; }
  pre { background: #0f172a; color: #e5e7eb; padding: 14px; border-radius: 9px;
        overflow: auto; font-size: 13px; margin: 8px 0 0; }
  .err { border-color: #f0c5c1; background: #fff5f4; color: #8f2020; }
  .foot { margin-top: 14px; color: #8a9199; font-size: 12px; word-break: break-all; }
  code { background: #eef1f5; padding: 1px 5px; border-radius: 4px; font-size: 12.5px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>__TITLE__</h1>
    <div class="meta">
      <span class="badge">DFS 制品</span>
      <span class="badge">__NAME__</span>
      <span class="badge">v__VERSION__</span>
      <span class="badge">来源 __ORIGINS__</span>
      <div style="margin-top:6px">__MODEL__</div>
    </div>
  </header>

  <div class="card">
    <div id="form"></div>
    <button id="run">运行</button>
    <div class="foot" id="hint">表单字段来自 <code>io.input_schema</code>；输出按 <code>io.output_schema</code> 校验后返回。</div>
  </div>

  <div class="out" id="out"></div>
</div>

<script>
const FIELDS = __FIELDS__;
const DEFAULTS = __DEFAULTS__;

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([k, v]) => { if (v !== null && v !== undefined) node.setAttribute(k, v); });
  (children || []).forEach(c => node.appendChild(typeof c === "string" ? document.createTextNode(c) : c));
  return node;
}

function buildForm() {
  const holder = document.getElementById("form");
  FIELDS.forEach(f => {
    const wrap = el("div", { class: "field" });
    const label = el("label", { for: "f_" + f.name }, [f.label]);
    if (f.required) label.appendChild(el("span", { class: "req" }, ["*"]));
    wrap.appendChild(label);

    let input;
    if (f.enum && f.enum.length) {
      input = el("select", { id: "f_" + f.name });
      input.appendChild(el("option", { value: "" }, ["（请选择）"]));
      f.enum.forEach(v => input.appendChild(el("option", { value: v }, [String(v)])));
    } else if (f.type === "boolean") {
      input = el("input", { id: "f_" + f.name, type: "checkbox", style: "width:auto" });
    } else if (f.multiline) {
      input = el("textarea", { id: "f_" + f.name, placeholder: f.placeholder || "" });
    } else {
      input = el("input", {
        id: "f_" + f.name,
        type: (f.type === "integer" || f.type === "number") ? "number" : "text",
        step: f.type === "integer" ? "1" : (f.type === "number" ? "any" : null),
        placeholder: f.placeholder || ""
      });
    }
    if (f.description) wrap.appendChild(el("div", { class: "hint" }, [f.description]));
    if (f.multiline) wrap.appendChild(el("div", { class: "hint" }, [f.type === "array" ? "每行一个，或用逗号分隔" : ""]));
    wrap.appendChild(input);
    holder.appendChild(wrap);

    if (DEFAULTS[f.name] !== undefined) {
      if (f.type === "boolean") input.checked = !!DEFAULTS[f.name];
      else input.value = DEFAULTS[f.name];
    }
  });
}

function collect() {
  const values = {};
  FIELDS.forEach(f => {
    const input = document.getElementById("f_" + f.name);
    values[f.name] = f.type === "boolean" ? input.checked : input.value;
  });
  return values;
}

function show(kind, payload) {
  const out = document.getElementById("out");
  out.innerHTML = "";
  const card = el("div", { class: "card" + (kind === "err" ? " err" : "") });
  card.appendChild(el("div", { class: "hint" }, [kind === "err" ? "执行失败（已按 fail closed 中止）" : "执行结果"]));
  const pre = el("pre", {}, [JSON.stringify(payload.output !== undefined ? payload.output : payload.error, null, 2)]);
  card.appendChild(pre);
  if (payload.run_dir) card.appendChild(el("div", { class: "foot" }, ["运行目录：" + payload.run_dir]));
  out.appendChild(card);
}

document.getElementById("run").addEventListener("click", async () => {
  const btn = document.getElementById("run");
  btn.disabled = true; btn.textContent = "运行中…";
  try {
    const resp = await fetch("/api/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(collect()) });
    const payload = await resp.json();
    show(payload.ok ? "ok" : "err", payload);
  } catch (e) {
    show("err", { error: String(e) });
  } finally {
    btn.disabled = false; btn.textContent = "运行";
  }
});

buildForm();
</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "DFS-UI/0.1"
    capsule_root: Path = Path(".")

    def log_message(self, fmt: str, *args) -> None:  # 安静模式
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/":
            capsule = load_capsule(self.capsule_root)
            origins = ", ".join(sorted({skill.origin for skill in capsule.skills}))
            model = capsule.resolve_model()
            key_state = "空 Key 可用" if model.get("auth") == "none" else ("Key 已设置" if model.get("api_key") else "未设置 Key")
            page = (
                PAGE.replace("__TITLE__", capsule.ui["title"])
                .replace("__NAME__", capsule.name)
                .replace("__VERSION__", capsule.version)
                .replace("__ORIGINS__", origins)
                .replace(
                    "__MODEL__",
                    f"模型：{model.get('provider')} / {model.get('model')}"
                    f"（auth={model.get('auth')}，{key_state}）",
                )
                .replace("__FIELDS__", json.dumps(describe_fields(capsule.input_schema), ensure_ascii=False))
                .replace("__DEFAULTS__", json.dumps(default_values(capsule.input_schema), ensure_ascii=False))
            )
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            return
        if route == "/api/spec":
            capsule = load_capsule(self.capsule_root)
            self._send_json(
                200,
                {
                    "capsule": capsule.summary(),
                    "fields": describe_fields(capsule.input_schema),
                    "defaults": default_values(capsule.input_schema),
                },
            )
            return
        self._send_json(404, {"ok": False, "error": f"未知路径: {route}"})

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route != "/api/run":
            self._send_json(404, {"ok": False, "error": f"未知路径: {route}"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            if not isinstance(payload, dict):
                raise ValueError("请求体必须是 JSON 对象")
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"ok": False, "error": f"请求体不合法: {exc}"})
            return

        try:
            capsule = load_capsule(self.capsule_root)
            input_data = coerce_input(payload, capsule.input_schema)
            result = run_once(self.capsule_root, input_data)
            self._send_json(200, {"ok": True, "output": result["output"], "run_dir": result["run_dir"]})
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": f"输入不符合 schema: {exc}"})
        except ContractError as exc:
            self._send_json(400, {"ok": False, "error": f"契约校验失败: {exc}"})
        except Exception as exc:  # 执行期失败：原样回报，不降级
            self._send_json(500, {"ok": False, "error": str(exc)})


def make_server(capsule_root: str | Path, host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    root_path = Path(capsule_root).expanduser().resolve()
    handler = type("DFSHandler", (_Handler,), {"capsule_root": root_path})
    return ThreadingHTTPServer((host, port), handler)


def serve(capsule_root: str | Path, host: str = "127.0.0.1", port: int = 8787, open_browser: bool = False) -> None:
    httpd = make_server(capsule_root, host=host, port=port)
    url = f"http://{host}:{httpd.server_address[1]}/"
    print(f"[ok] Web UI 已启动: {url}")
    print("     停止：Ctrl+C")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[--] 已停止 Web UI")
    finally:
        httpd.server_close()
