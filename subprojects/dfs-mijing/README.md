# dfs-mijing（觅境 · 照片地点推断）

> DFS（Derived From Skill）制品，由 Skill 规约编译生成，独立运行，不依赖 Agent 宿主。

## 这是什么

- `SKILL.md`：人类可读的任务规约（目标、输入输出、流程、边界）
- `dfs.json`：机器契约（来源声明、模型绑定与鉴权、UI 形态、IO Schema、工具白名单）
- `plan.json`：编译产物（运行计划，运行期只读）
- `dfs.local.json`：本机手动设置（模型端点、鉴权），**不入库**

输入一张照片，输出现场可核对的定位结论：地点名称、证据等级、逐条证据。规约的核心约束是**只写画面里看到的东西**，不编造街景比对、地图核实和经纬度。

## 三条硬性规范

1. **来源声明**：`source.provenance` 覆盖 `SKILL.md`，origin 为 `original`。
2. **独立 UI**：`ui.kind = "web"`，表单由 `io.input_schema` 自动生成。
3. **模型可手动设置**：`model.model` 预设为空，必须由使用者自行绑定；`auth = "none"` 允许空 API Key。

## 先配置模型（必做）

本制品**不预置任何模型与端点**，未配置直接运行会在启动前失败。三种配置方式任选其一：

```bash
# 方式一：写入 dfs.local.json（不入库，推荐）
python dfs.py model subprojects/dfs-mijing \
  --provider openai-compatible \
  --base-url http://127.0.0.1:11434/v1 \
  --model qwen3 --auth none

# 方式二：环境变量
export DFS_BASE_URL=http://127.0.0.1:11434/v1
export DFS_MODEL=qwen3
export DFS_API_KEY=""        # 本地无鉴权端点可留空

# 方式三：云端端点（需要 Key，鉴权走环境变量，不落盘）
export DFS_API_KEY="<your-key>"
python dfs.py model subprojects/dfs-mijing \
  --provider openai-compatible \
  --base-url https://api.example.com/v1 \
  --model <model-id> --auth bearer
```

配置完成后必须重新编译，换模型即换制品：

```bash
python dfs.py build subprojects/dfs-mijing
```

## 怎么用

```bash
# 在仓库根目录执行
python dfs.py validate subprojects/dfs-mijing
python dfs.py inspect  subprojects/dfs-mijing
python dfs.py run      subprojects/dfs-mijing --input subprojects/dfs-mijing/input.example.json

# 独立界面
python dfs.py serve  subprojects/dfs-mijing     # 浏览器
python dfs.py window subprojects/dfs-mijing     # 独立窗口
```

## 能力边界

- 本制品的计划只包含模型推理步骤，**不产经纬度**；`lat` / `lon` 由外部取证流程补齐。
- 需要照片取证链（EXIF、以图搜图、地名检索、卫星图比对）时，使用完整项目，而不是本制品。
- 无候选获得画面支撑时输出 `status: "unlocatable"`，不降级猜测。
