# dfs_runtime

DFS 的最小运行时。零第三方依赖，Python 3.10+。

## 模块

| 模块 | 职责 |
| --- | --- |
| `manifest.py` | 加载 `dfs.json` + `SKILL.md` + `dfs.local.json`，来源校验、契约校验、模型解析 |
| `compiler.py` | 调模型把规约编译成 `plan.json`，并校验越界 |
| `executor.py` | 按计划确定性执行，模板渲染、校验、证据落盘 |
| `runner.py` | 单次运行封装，CLI / Web / 窗口共用同一路径 |
| `adapters.py` | 模型适配器：`openai-compatible` / `mock`；鉴权 `bearer` / `none` |
| `uigen.py` | `input_schema` → 表单描述与类型转换 |
| `webui.py` | 内置 Web UI（零依赖，默认仅回环） |
| `appwindow.py` | 窗口模式：浏览器 app 窗口（Edge/Chrome `--app=`） |
| `winui.py` | 可选原生窗口（tkinter，需系统 Tcl/Tk） |
| `tools.py` | 白名单内置工具：`now` / `sha256` / `read_text` / `write_text` / `count_lines` |
| `validation.py` | JSON Schema 子集校验（支持本地 `$ref`、`oneOf`） |

## 命令

```
python dfs.py validate <制品目录>
python dfs.py inspect  <制品目录>
python dfs.py build    <制品目录> [--provider ...] [--model ...] [--base-url ...] [--auth ...]
python dfs.py run      <制品目录> [--input input.json]
python dfs.py serve    <制品目录> [--port] [--host] [--open]
python dfs.py window   <制品目录> [--native] [--check]
python dfs.py model    <制品目录> [--show | --provider --model --base-url --auth --clear]
python dfs.py new      <制品名> [--title ...] [--ui web|window|none]
```

退出码：`0` 成功、`2` 契约失败、`3` 执行失败、`4` 模型调用失败、`5` 文件缺失、`6` 窗口能力不可用、`7` 系统层失败。

## 环境变量

| 变量 | 作用 | 优先级 |
| --- | --- | --- |
| `DFS_MODEL` | 模型标识 | 高于 `dfs.local.json` 与 `dfs.json` |
| `DFS_BASE_URL` | 模型端点 | 同上 |
| `DFS_AUTH` | 鉴权方式 `bearer` / `none` | 同上 |
| `DFS_API_KEY` | 模型密钥 | 仅环境变量与本地覆盖文件，不写入 `dfs.json` |
| `DFS_BROWSER` | 指定窗口模式使用的浏览器可执行文件 | 仅窗口模式 |

## 明确不做

- 不自动切换备用模型（换模型即换制品，需要重新编译与验收）
- 不自动跳过失败步骤
- 不自动放宽 schema
- 不提供 shell / 网络 / 删除类工具
- Web UI 不监听公网地址、不带账号体系
