# 架构说明

## 1. 四层结构

```
规约层 → 编译层 → 运行层 → 证据层
```

| 层 | 输入 | 输出 | 参与方 | 确定性 |
| --- | --- | --- | --- | --- |
| 规约层 | 人的意图 | `SKILL.md` + `dfs.json` | 人 | 高（人工确定） |
| 编译层 | 规约 | `plan.json` | 模型 + schema 校验 | 中（模型生成，校验兜底） |
| 运行层 | 计划 + 输入 | 结果 + 证据 | 运行时 + 模型（节点内） | 高（计划已锁定） |
| 证据层 | 执行过程 | `evidence.jsonl`、`result.json` | 运行时 | 高（只追加） |

## 2. 制品生命周期

```
new  →  编写 SKILL.md / dfs.json  →  validate  →  build（编译）
                                        ↓
                                     plan.json
                                        ↓
                              run（可重复，可并行）
                                        ↓
                                runs/<运行ID>/
```

关键规则：

1. **`plan.json` 一旦产出即视为制品的一部分**，可以直接入库、评审、版本化。
2. **运行期不得修改计划**：任何「临时加一步」的想法都属于编译期的问题，必须回到 build。
3. **规约变更必须触发重新编译**：`dfs.json` 里记录 `source` 摘要；运行时若发现规约摘要与计划中的 `source_digest` 不一致，拒绝执行（fail closed）。

## 3. 计划的执行语义

`plan.json` 的 `steps` 是一个**有序数组**，默认顺序执行。步骤类型：

| kind | 作用 | 必需字段 | 约束 |
| --- | --- | --- | --- |
| `llm` | 节点内推理：渲染提示模板 → 调用绑定模型 → 文本产物入上下文 | `id`、`prompt`、`output` | 只能使用已绑定模型；不得调用工具 |
| `check` | 校验：对上下文中的值做断言 | `id`、`op`、`ref` | 失败即中止，不降级 |
| `tool` | 执行白名单内的安全工具 | `id`、`tool`、`args`、`output` | `tool` 必须在 `dfs.json.tools` 白名单内 |

上下文（context）结构：

```
context = {
  "input":   { ...外部输入... },
  "steps":   { "<step-id>": <该步骤产物> },
  "inputs":  { ...Step 输出可直接以 id 引用... }   # 渲染时合并
}
```

模板语法：`{{input.name}}`、`{{step_id}}`、`{{input}}`（整体 JSON）。若整个字段只有一个占位符，则保留原生类型（对象/数组/数字），否则按字符串插值。

## 4. 失败策略

运行时统一遵循 **fail closed**：

| 失败点 | 行为 | 证据 |
| --- | --- | --- |
| `dfs.json` 不合法 / 缺字段 | 拒绝加载 | 无 |
| Skill 文件缺失或摘要不匹配 | 拒绝执行 | 无 |
| `plan.json` 超 `max_steps`、含白名单外工具 | 拒绝执行 | 无 |
| 某步骤执行异常 | 中止后续步骤 | 已完成的步骤全部落盘 |
| 输出不满足 `io.output_schema` | 中止并标记 `output_invalid` | 结果落盘便于排查 |
| 模型端点不可达 | 中止，不自动降级到其他模型 | 记录请求元信息 |

明确拒绝的降级行为：**不自动改用备用模型、不自动跳过失败步骤、不自动放宽 schema**。降级会破坏「同类输入产出同级结果」的前提，与 DFS 的目标冲突。

## 5. 证据层

每次运行写入 `<制品>/runs/<UTC 时间戳>-<计划短哈希>/`：

| 文件 | 内容 |
| --- | --- |
| `evidence.jsonl` | 每步一行：`step`、`kind`、`ts`、`status`、`prompt_sha256`、`output_sha256`、`duration_ms` |
| `result.json` | 最终输出 + 是否通过 schema 校验 |
| `artifacts/` | 各 `llm` 步骤的原始文本产物（便于人工复核） |

不写入证据的内容：API Key、完整提示词原文（只存哈希，避免规约内容外泄）。

## 6. 模型绑定

`dfs.json.model` 声明绑定关系：

```json
{
  "provider": "openai-compatible",
  "model": "qwen3-35b-instruct",
  "base_url": "https://api.example.com/v1",
  "auth": "bearer",
  "temperature": 0.2,
  "max_tokens": 1024
}
```

- 配置优先级：**CLI 参数 > 环境变量 `DFS_*` > `dfs.local.json` > `dfs.json`**；
- `dfs.local.json` 是本机手动设置（`dfs model` 写入），不入库，改它不需要重新编译；
- `auth=none` 时允许空 API Key（本地无鉴权端点），`auth=bearer` 缺 Key 直接失败；
- `provider` 为 `mock` 时，运行时使用计划中记录的 `mock_output` 做离线回放，仅用于 CI 与链路自检；`build` 阶段显式拒绝 mock。
- 绑定关系属于制品的一部分：换模型等于换制品，需要重新编译与重新验收。

## 7. 与 Agent 宿主的边界

DFS 制品**可以**被 Agent 调用（作为一个普通工具暴露），但制品内部不依赖宿主：

- 不读取宿主对话历史；
- 不接受宿主的工具注册表；
- 不继承宿主的系统提示；
- 输入输出仅由 `io.input_schema` / `io.output_schema` 决定。

这保证同一制品在不同宿主、不同调用方下行为一致。
