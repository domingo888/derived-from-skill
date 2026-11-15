# __CAPSULE__

> DFS（Derived From Skill）制品，由 Skill 规约编译生成，独立运行，不依赖 Agent 宿主。

## 这是什么

- `SKILL.md`：人类可读的任务规约（目标、输入输出、流程、边界）
- `dfs.json`：机器契约（来源声明、模型绑定与鉴权、UI 形态、IO Schema、工具白名单）
- `plan.json`：编译产物（运行计划，运行期只读）
- `dfs.local.json`：本机手动设置（模型端点、鉴权），**不入库**

## 三条硬性规范

1. **来源声明**：`source.provenance` 必须覆盖每个 Skill 文件；外部来源要填 `upstream_url`（见 `spec/provenance.md`）。
2. **独立 UI**：`ui.kind` 必填，`web` 或 `window`；表单由 `io.input_schema` 自动生成（见 `docs/ui-spec.md`）。
3. **模型可手动设置**：`dfs model` 改绑定，`auth=none` 时允许空 API Key（见 `docs/model-binding.md`）。

## 怎么用

```bash
# 在仓库根目录执行
python dfs.py validate subprojects/__CAPSULE__
python dfs.py build    subprojects/__CAPSULE__ --provider openai-compatible --base-url <端点> --model <模型>
python dfs.py run      subprojects/__CAPSULE__ --input subprojects/__CAPSULE__/input.example.json

# 独立界面
python dfs.py serve    subprojects/__CAPSULE__     # 浏览器
python dfs.py window   subprojects/__CAPSULE__     # 独立窗口

# 手动指定模型（本地端点可空 Key）
python dfs.py model subprojects/__CAPSULE__ --provider openai-compatible \
  --base-url http://127.0.0.1:11434/v1 --model qwen3 --auth none
```

## 边界

- 只处理本规约定义的一类任务
- 不具备跨 Skill 调度、不具备规约外自主规划
- 换模型等于换制品：需重新编译并重新验收
