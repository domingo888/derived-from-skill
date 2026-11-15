"""内置窗口 UI：tkinter 实现，适合不适合开浏览器/需要单窗口交付的制品。

规范与 Web UI 一致：表单由 schema 推导、运行走 runner.run_once、仅本机使用。
"""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

from .manifest import load_capsule
from .runner import run_once
from .uigen import coerce_input, default_values, describe_fields


def check_available() -> tuple[bool, str]:
    try:
        import tkinter as tk
    except ImportError as exc:  # pragma: no cover
        return False, f"tkinter 不可用: {exc}"
    try:
        probe = tk.Tk()
        version = tk.TkVersion
        probe.withdraw()
        probe.destroy()
        return True, f"tkinter {version}"
    except Exception as exc:  # 无显示环境等
        return False, str(exc)


def open_window(capsule_root: str | Path) -> None:
    import tkinter as tk
    from tkinter import ttk

    capsule = load_capsule(capsule_root)
    ui = capsule.ui
    fields = describe_fields(capsule.input_schema)
    defaults = default_values(capsule.input_schema)

    window = tk.Tk()
    window.title(f"{ui['title']} · DFS")
    window.geometry(f"{ui['width']}x{ui['height']}")
    window.minsize(480, 420)

    header = ttk.Frame(window, padding=(16, 14, 16, 6))
    header.pack(fill="x")
    ttk.Label(header, text=ui["title"], font=("Segoe UI", 13, "bold")).pack(anchor="w")
    origins = ", ".join(sorted({skill.origin for skill in capsule.skills}))
    ttk.Label(
        header,
        text=f"DFS 制品 · {capsule.name} · v{capsule.version} · 来源 {origins}",
        foreground="#6b7280",
    ).pack(anchor="w")

    form = ttk.Frame(window, padding=(16, 6, 16, 6))
    form.pack(fill="x")

    variables: dict[str, object] = {}
    widgets: dict[str, object] = {}

    for row, field in enumerate(fields):
        label_text = field["label"] + (" *" if field["required"] else "")
        ttk.Label(form, text=label_text).grid(row=row * 2, column=0, sticky="w", pady=(6, 2))

        if field["enum"]:
            var = tk.StringVar(value=str(defaults.get(field["name"], "")))
            widget = ttk.Combobox(form, textvariable=var, values=field["enum"], state="readonly")
            widget.grid(row=row * 2 + 1, column=0, sticky="ew")
            variables[field["name"]] = var
        elif field["type"] == "boolean":
            var = tk.BooleanVar(value=bool(defaults.get(field["name"], False)))
            widget = ttk.Checkbutton(form, variable=var)
            widget.grid(row=row * 2 + 1, column=0, sticky="w")
            variables[field["name"]] = var
        elif field["multiline"]:
            widget = tk.Text(form, height=4, wrap="word")
            value = defaults.get(field["name"])
            if value:
                widget.insert("1.0", str(value))
            widget.grid(row=row * 2 + 1, column=0, sticky="ew")
            widgets[field["name"]] = widget
        else:
            var = tk.StringVar(value=str(defaults.get(field["name"], "")))
            widget = ttk.Entry(form, textvariable=var)
            widget.grid(row=row * 2 + 1, column=0, sticky="ew")
            variables[field["name"]] = var

        if field["description"]:
            ttk.Label(form, text=field["description"], foreground="#8a9199").grid(
                row=row * 3 + 2, column=0, sticky="w"
            )

    form.columnconfigure(0, weight=1)

    status = ttk.Label(window, text="", foreground="#6b7280", padding=(16, 4))
    status.pack(fill="x")

    output = tk.Text(window, height=10, wrap="word", background="#0f172a", foreground="#e5e7eb")
    output.pack(fill="both", expand=True, padx=16, pady=(0, 12))
    output.configure(state="disabled")

    results: queue.Queue = queue.Queue()

    def collect() -> dict:
        values: dict = {}
        for field in fields:
            name = field["name"]
            if field["type"] == "boolean":
                values[name] = bool(variables[name].get())
            elif name in widgets:
                values[name] = widgets[name].get("1.0", "end").strip()
            else:
                values[name] = variables[name].get()
        return values

    def show(text: str) -> None:
        output.configure(state="normal")
        output.delete("1.0", "end")
        output.insert("1.0", text)
        output.configure(state="disabled")

    def poll() -> None:
        try:
            kind, payload = results.get_nowait()
        except queue.Empty:
            window.after(150, poll)
            return
        button.configure(state="normal", text="运行")
        if kind == "ok":
            status.configure(text=f"完成 · {Path(payload['run_dir']).name}", foreground="#166534")
            show(json.dumps(payload["output"], ensure_ascii=False, indent=2))
        else:
            status.configure(text=f"失败：{payload}", foreground="#8f2020")
            show(str(payload))

    def worker(values: dict) -> None:
        try:
            capsule_now = load_capsule(capsule_root)
            input_data = coerce_input(values, capsule_now.input_schema)
            results.put(("ok", run_once(capsule_root, input_data)))
        except Exception as exc:  # 失败即回报，不降级
            results.put(("err", str(exc)))

    def on_run() -> None:
        button.configure(state="disabled", text="运行中…")
        status.configure(text="执行中…", foreground="#6b7280")
        threading.Thread(target=worker, args=(collect(),), daemon=True).start()
        window.after(150, poll)

    footer = ttk.Frame(window, padding=(16, 0, 16, 12))
    footer.pack(fill="x")
    button = ttk.Button(footer, text="运行", command=on_run)
    button.pack(side="left")
    ttk.Label(
        footer,
        text="字段来自 io.input_schema；输出按 io.output_schema 校验",
        foreground="#8a9199",
    ).pack(side="left", padx=10)

    window.mainloop()
