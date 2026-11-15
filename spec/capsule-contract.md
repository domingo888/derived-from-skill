# 制品契约说明

一个 DFS 制品由三个文件构成：`SKILL.md`（规约）、`dfs.json`（机器契约）、`plan.json`（编译产物）。

- `dfs.json` 的 JSON Schema：[`runtime/dfs_runtime/schemas/manifest.schema.json`](../runtime/dfs_runtime/schemas/manifest.schema.json)
- `plan.json` 的 JSON Schema：[`runtime/dfs_runtime/schemas/plan.schema.json`](../runtime/dfs_runtime/schemas/plan.schema.json)

---

## 1. dfs.json 字段

| 字段 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `name` | ✅ | string | 制品标识，需与子项目目录名、`plan.json.capsule` 一致 |
| `title` | ❌ | string | 人类可读标题 |
| `version` | ✅ | string | 制品版本，建议语义化 |
| `source.kind` | ✅ | `"skill"` \| `"skill-set"` | 单一 Skill 或 Skill 组合 |
| `source.skills` | ✅ | string[] | 相对制品根目录的规约文件路径，至少一个 |
| `source.provenance` | ✅ | object[] | **来源声明**，与 `source.skills` 一一对应；字段见 [`provenance.md`](provenance.md) |
| `source.provenance[].file` | ✅ | string | 对应 `source.skills` 中的路径 |
| `source.provenance[].origin` | ✅ | enum | `original` \| `github` \| `clawhub` \| `local-import` \| `other` |
| `source.provenance[].upstream_url` | 条件 | string | `github` / `clawhub` / `other` 时必填 |
| `source.provenance[].digest` | ❌ | string | `sha256:<64>`；填写后强制校验内容一致性 |
| `model.provider` | ✅ | string | `openai-compatible` \| `mock` |
| `model.model` | ✅ | string | 绑定模型标识 |
| `model.base_url` | ❌ | string | 端点；可由 `dfs.local.json` 或 `DFS_BASE_URL` 覆盖 |
| `model.auth` | ❌ | enum | `bearer`（默认）\| `none`；`none` 允许空 Key |
| `model.api_key_env` | ❌ | string | 指定的密钥环境变量名，默认 `DFS_API_KEY` |
| `model.temperature` | ❌ | number | 默认 0.2 |
| `model.max_tokens` | ❌ | integer | 默认 1024 |
| `runtime.max_steps` | ❌ | integer | 计划步骤上限，默认 12；超出即拒绝执行 |
| `runtime.timeout_s` | ❌ | integer | 单步超时，默认 120 |
| `tools` | ❌ | string[] | 工具白名单，默认空（不允许任何工具） |
| `ui.kind` | ✅ | enum | `web` \| `window` \| `none`；见 [`../docs/ui-spec.md`](../docs/ui-spec.md) |
| `ui.title` | ❌ | string | 界面标题，默认取 `title` |
| `ui.host` | ❌ | string | 仅 web，默认 `127.0.0.1`，禁止对外 |
| `ui.port` | ❌ | integer | 仅 web，默认 8787 |
| `ui.width` / `ui.height` | ❌ | integer | 仅 window，默认 760×620 |
| `io.input_schema` | ✅ | object | 输入 JSON Schema |
| `io.output_schema` | ✅ | object | 输出 JSON Schema |

### 约束

1. `source.skills` 中每个文件必须存在，运行时按内容摘要参与一致性校验。
2. `source.provenance` 必须完整覆盖 `source.skills`：缺项、多项、重复项一律拒绝加载。
3. `provider: "mock"` 只能用于 `run` 的离线回放，`build` 阶段会被拒绝。
4. `model.auth` 为 `bearer` 时必须提供 Key；为 `none` 时允许空 Key（本地无鉴权端点）。
5. `dfs.json` 中**不存在** `api_key` 字段；密钥只能来自环境变量或 `dfs.local.json`（不入库）。
6. `tools` 为空时，计划中出现任何 `tool` 步骤都会被拒绝执行。
7. `ui.kind` 必填；`none` 仅限库型制品且须在 `ui.note` 说明理由。
8. `io.*_schema` 至少声明 `type: "object"`，推荐同时声明 `required` 与 `additionalProperties: false`。

---

## 2. plan.json 字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `plan_version` | ✅ | 固定为 `1` |
| `capsule` | ✅ | 必须与 `dfs.json.name` 一致 |
| `compiled_by` | ❌ | 编译来源：provider、model、mode（`model` \| `offline-fixture`） |
| `source_digest` | ❌ | 编译时规约摘要，用于一致性校验 |
| `steps` | ✅ | 有序步骤数组，长度 1…`runtime.max_steps` |
| `output` | ✅ | 输出映射：`{输出字段: 模板}` |
| `notes` | ❌ | 编译说明（人可读，不参与执行） |

### 步骤类型

```json
{"id": "extract", "kind": "llm", "prompt": "从输入中抽取字段：{{input.raw}}", "output": "fields", "mock_output": "{}"}

{"id": "guard", "kind": "check", "op": "nonempty", "ref": "fields"}

{"id": "stamp", "kind": "tool", "tool": "now", "args": {}, "output": "ts"}
```

| kind | 字段 | 说明 |
| --- | --- | --- |
| `llm` | `prompt`、`output`、可选 `mock_output` | 渲染模板后调用绑定模型，产出文本；`mock_output` 仅 `mock` 适配器使用 |
| `check` | `op`、`ref`、可选 `value` | `op` ∈ `nonempty` / `contains` / `regex` / `keys` / `equals` / `len_max` |
| `tool` | `tool`、`args`、`output` | 必须在 `dfs.json.tools` 白名单内 |

### 模板语法

- `{{input.x}}`：取输入字段
- `{{<step-id>}}`：取该步骤产物
- `{{input}}`：整体 JSON
- 单占位符整字段 → 保留原生类型；混合文本 → 字符串插值

---

## 3. 一致性校验（运行前）

`run` 在执行前会做四项检查，任一不通过即拒绝执行：

1. `plan.capsule == dfs.json.name`
2. `len(plan.steps) <= runtime.max_steps`
3. 所有 `tool` 步骤的 `tool` ∈ `dfs.json.tools`
4. 若 `plan.source_digest` 存在，必须等于当前 `source.skills` 内容摘要

第 4 项保证「规约改了但没重新编译」的情况不会静默发生。

---

## 4. 版本演进

- `plan_version` 变化时，运行时拒绝加载旧版本计划，必须重新编译；
- 制品版本（`version`）与计划版本无关：同一制品可以多次编译，保留不同 plan 做行为对比；
- 换模型即换制品能力边界，必须重新编译并重新验收，不可复用旧 plan。
