# R3 模型绑定与手动设置规范（Model Binding）

> 一句话：**模型必须可手动指定；鉴权方式必须显式声明；`auth=none` 时允许空 API Key。**

DFS 制品离开模型只是一个流程骨架。因此「这个制品用哪个模型、怎么连、要不要鉴权」必须是**制品的一部分**，而不是运行环境的隐式状态。

---

## 1. 配置来源与优先级

```
CLI 参数  >  环境变量(DFS_*)  >  <制品>/dfs.local.json  >  <制品>/dfs.json
```

| 层 | 位置 | 用途 | 是否入库 |
| --- | --- | --- | --- |
| 制品契约 | `dfs.json.model` | 制品默认绑定，随制品分发 | ✅ 入库 |
| 本地覆盖 | `dfs.local.json` | 单机手动设置（换模型、换端点、本地无鉴权） | ❌ `.gitignore` 已排除 |
| 环境变量 | `DFS_MODEL` / `DFS_BASE_URL` / `DFS_AUTH` / `DFS_API_KEY` | CI、临时调试、密钥注入 | ❌ 不入库 |
| CLI 参数 | `--provider` / `--model` / `--base-url` / `--auth` | 一次性覆盖 | ❌ 不落盘 |

**优先级的设计意图**：让「最后一次临时指定」赢，同时保证「制品默认值」始终是可分发的基线。

---

## 2. 手动设置的推荐方式：`dfs model`

```bash
# 查看当前生效配置（会标注覆盖文件是否存在，Key 脱敏显示）
python dfs.py model subprojects/dfs-hello --show

# 指向本地无鉴权端点（允许空 Key）
python dfs.py model subprojects/dfs-hello \
  --provider openai-compatible \
  --base-url http://127.0.0.1:11434/v1 \
  --model qwen3 --auth none

# 指向需要鉴权的云端端点（Key 建议走环境变量，不写进文件）
python dfs.py model subprojects/dfs-hello \
  --provider openai-compatible --base-url https://api.example.com/v1 --model qwen3-35b

# 清除本地覆盖，回到 dfs.json 的默认绑定
python dfs.py model subprojects/dfs-hello --clear
```

`dfs.local.json` 只允许一个顶层键 `model`，其余字段一律拒绝，避免它变成「第二个不受约束的 manifest」。

---

## 3. 鉴权与空 Key 规则

| `model.auth` | Key 要求 | 适用 |
| --- | --- | --- |
| `bearer`（默认） | **必须**提供非空 Key，否则启动即失败 | 云端 OpenAI 兼容服务 |
| `none` | **允许为空**，请求不带 `Authorization` 头 | 本地/内网无鉴权端点（Ollama、LM Studio、LocalAI、vLLM、自建网关） |

明确不做的事：**`bearer` 缺 Key 时不静默降级为不带鉴权**。降级会让「配置错误」表现成「服务端 401」，排查成本远高于直接报错。

Key 的来源顺序：`DFS_API_KEY` → `model.api_key_env` 指定的变量名 → `dfs.local.json.model.api_key`（仅本地便利，不入库）。

---

## 4. 常见本地端点

| 运行时 | base_url | auth | 备注 |
| --- | --- | --- | --- |
| Ollama | `http://127.0.0.1:11434/v1` | `none` | 需确认模型已 `ollama pull` |
| LM Studio | `http://127.0.0.1:1234/v1` | `none` | 开启 Local Server |
| LocalAI | `http://127.0.0.1:8080/v1` | `none` 或自设 Key | 视部署配置 |
| vLLM | `http://127.0.0.1:8000/v1` | `none`（默认） | 生产常加网关鉴权 |

---

## 5. 换模型 = 换制品

模型的输出分布直接决定制品的产出质量。因此：

1. **换模型必须重新 build**（`build_plan` 会拒绝 mock，且 `compiled_by` 记录模型来源）；
2. 旧 `plan.json` 不可与新模型混用验收；
3. 制品版本号应随模型切换一并变更，便于回溯「这版是谁编译的」。

---

## 6. 密钥安全

- `dfs.json` **禁止**写明文 `api_key`（schema 里根本没有这个字段）；
- `dfs.local.json` 可写但已 `.gitignore`；
- 运行证据（`runs/`）只记录 `plan_digest`、`source_digest`、请求元信息，**不记录 Key、不记录完整提示词原文**（只存哈希）；
- `validate` / `model --show` 输出中 Key 一律脱敏。

---

## 7. 失败处理（fail closed）

| 情况 | 行为 |
| --- | --- |
| `base_url` 为空 | 报错，提示三种设置途径，不尝试默认地址 |
| `model` 为空 | 报错，提示用 `dfs model --model` 指定 |
| `auth=bearer` 且无 Key | 报错，提示设置环境变量或改 `auth=none` |
| 端点不可达 / HTTP 错误 / 超时 | 中止当前运行，证据保留已完成的步骤；**不自动换模型重试** |
| 响应结构异常 | 报错并给出响应片段（截断 200 字符） |
