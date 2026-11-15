"""窗口模式：本地服务 + 浏览器 app 模式，得到一个无标签栏的独立应用窗口。

为什么不用 tkinter：tkinter 依赖系统 Tcl/Tk，部分运行时缺失；
浏览器 app 模式（Edge / Chrome 的 --app=）在 Windows/macOS/Linux 上普遍可用，
且与 Web UI 共用同一套页面与执行路径，保证「窗口版」和「浏览器版」行为一致。

tkinter 作为可选增强保留在 winui.py，用 dfs window --native 调用。
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from .webui import make_server

_WINDOWS_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Chromium\Application\chrome.exe",
]

_POSIX_CANDIDATES = [
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/microsoft-edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
]


def find_browser() -> str | None:
    env_override = os.environ.get("DFS_BROWSER")
    if env_override and Path(env_override).exists():
        return env_override

    candidates = _WINDOWS_CANDIDATES if sys.platform.startswith("win") else _POSIX_CANDIDATES
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def open_window(capsule_root: str | Path, width: int = 760, height: int = 620, port: int = 0) -> None:
    httpd = make_server(capsule_root, host="127.0.0.1", port=port)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    browser = find_browser()

    if browser:
        print(f"[ok] 窗口 UI 已启动: {url}")
        print(f"     浏览器: {browser}")
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            subprocess.run(
                [browser, f"--app={url}", f"--window-size={width},{height}"],
                check=False,
            )
        except KeyboardInterrupt:
            pass
        finally:
            httpd.shutdown()
            httpd.server_close()
            print("[--] 窗口已关闭，服务停止")
        return

    print(f"[warn] 未找到 Edge/Chrome，改用默认浏览器打开: {url}", file=sys.stderr)
    print("       可用环境变量 DFS_BROWSER 指定浏览器可执行文件路径", file=sys.stderr)
    webbrowser.open(url)
    print("     关闭浏览器后按 Ctrl+C 停止服务")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[--] 已停止")
    finally:
        httpd.server_close()
