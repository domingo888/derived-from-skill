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

## 来源

本制品派生于 **[Oldcircle/geo-sleuth](https://github.com/Oldcircle/geo-sleuth)**（作者 Oldcircle，MIT）。

上游是一个 Agent Skill：用本地脚本做 photo 取证（EXIF、以图搜图、地名检索、卫星图比对），再由模型读图与组织报告。本制品只取它的**判断准则**，改写成可独立编译的 DFS 规约；脚本与运行时仍以上游为准。

## 相对上游的改进

以下改动均来自实测问题，不是设想：

1. **整图识图无命中时自动局部回搜**
   上游在整图无结果时完全依赖模型首轮候选，结果随模型波动。我们按主体紧裁剪回搜；宽幅斜航拍再补左右前景变体，找到来源即停止，避免无差别增加请求。

2. **修复来源证据丢失**
   上游 `intake` 摘要只保存原始 JSON 文件名，`links`、`text_head` 在汇总时丢失。现在逐个读回原始文件补齐，来源标题得以保留。

3. **自动标签全面降权**
   以图搜图的自动标签错得离谱（同一张图给过「无锡市鹅湖镇」和「松树」）。标签只作最低优先级线索，不参与整图识图投票，也不直接成为结论。

4. **短地名检索**
   模型读图后额外给出适合地图检索的最短地名（「福州三坊七巷南后街文儒坊入口」→「文儒坊」），避免长串被地名库模糊匹配到附近同名 POI。

5. **看图解读进入候选**
   上游只把解读当旁注。现在符合地名格式的解读结果会作为独立候选参与排序，并在地名检索失败时用短名重查。

6. **排序规则修正**
   卫星已判 `no` 的识图候选不再享受识图加分，否则一个被否掉的识图结果会压过画面里读到的牌匾地名。

7. **卫星核验去伪证据**
   只接受俯视可见的地物；天际线、背景远山、城市方位、地理常识一律不计。判 `yes` 至少需要 2 个具体地物，代码再兜底降级。

8. **街景不因卫星 `no` 被判死**
   平视街景与卫星俯视图本就难对应。此时若看图解读认出具体地名并已落到坐标，判 `medium` 并明示「卫星未确认」，而不是直接判 `low`。

9. **模型配置外置**
   模型地址、名称、API Key、Temperature 全部改为用户填写，不预置任何端点；未配置时在分析入口直接给出明确提示，不白跑脚本。

## 开发中踩过的坑

| 坑 | 表现 | 处理 |
| --- | --- | --- |
| PowerShell 5 写 UTF-8 带 BOM | `JSON.parse` 读到 BOM 直接抛错，`.catch` 又把异常吞掉，表现为「改了端口完全不生效」 | 读取时剥离 `\uFEFF` 再解析 |
| PowerShell 脚本无 BOM | PowerShell 5 按 ANSI 读中文，字符串变乱码、引号配对错乱，整个脚本解析失败 | 脚本转存为 UTF-8 **带 BOM** |
| 端口被残留进程占用 | 新进程起不来但旧进程仍在服务，复测结果其实来自旧代码，结论不可信 | 先按端口查 PID 并结束，再启动 |
| 地名库模糊匹配 | 「文儒坊入口」被匹配成「书香文儒酒店」，坐标对、名字错 | 用模型提炼的短名检索 |
| 括号清洗过激 | 「福州市（三坊七巷历史文化街区）」被洗成只剩城市 | 保留含街、巷、坊、岛、园等关键词的括号内容 |
| 裁剪策略想当然 | 对称放大、居中前景都返回 0 条来源，只有向右扩展前景命中 | 宽幅航拍按比例向右补前景 |
| 提示词一改就回归 | 给裁剪框加「保留完整立面」后，模型反而只返回城市名 | 恢复紧裁剪，前景扩展交给确定性代码 |
| 街景做卫星核验 | 所有候选一律 `no`，排序完全失去区分度 | 街景场景单独处理，不据此否决 |

## 能力边界

- 本制品的计划只包含模型推理步骤，**不产经纬度**；`lat` / `lon` 由外部取证流程补齐。
- 需要照片取证链（EXIF、以图搜图、地名检索、卫星图比对）时，使用完整项目，而不是本制品。
- 无候选获得画面支撑时输出 `status: "unlocatable"`，不降级猜测。
