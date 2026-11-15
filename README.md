# derived-from-skill (DFS)

> **DFS（Derived From Skill）**：以 Skill 规约作为源素材，经模型转化、衍生生成运行逻辑的独立可运行制品。
>
> *Executable artifacts derived from skill specifications.*

> **命名说明**：仓库名使用全称 `derived-from-skill`，因为 `DFS` 在工程语境中已被 *Depth-First Search*（深度优先搜索）与 *Distributed File System*（分布式文件系统）占用。仓库内术语、子项目前缀仍沿用缩写 **DFS**。
> 本项目中的 DFS **不等于** 上述两者。

---

## 目录

- [1. 一句话定义](#1-一句话定义)
- [2. 问题：多 Skill Agent 的结构性不确定性](#2-问题多-skill-agent-的结构性不确定性)
- [3. 设计主张](#3-设计主张)
- [4. 核心设计：四层结构](#4-核心设计四层结构)
- [5. 与相邻范式对比](#5-与相邻范式对比)
- [6. 收益与代价](#6-收益与代价)
- [7. 非目标（Non-goals）](#7-非目标non-goals)
- [8. 仓库结构](#8-仓库结构)
- [9. 快速开始](#9-快速开始)
- [10. 契约一览](#10-契约一览)
- [11. 子项目组织与命名](#11-子项目组织与命名)
- [12. 相关项目](#12-相关项目)
- [13. 术语](#13-术语)
- [14. Roadmap](#14-roadmap)
- [15. 开发规范（硬性规则）](#15-开发规范硬性规则)
- [16. 发布到 GitHub](#16-发布到-github)

---

## 1. 一句话定义

**DFS（Derived From Skill）** 以声明式 Skill 规约（单个 Skill，或一组协同 Skill）作为唯一输入源，由模型在规约划定的边界内完成理解、转化、重组，生成该任务专属的运行计划，并封装为自带最小运行时、可独立部署的执行制品。

- Skill 在 DFS 中是**规约（specification）**，不是被宿主直接解释执行的脚本；
- 模型是**转化与执行单元**，在规约边界内做分支判断、参数填充、内容生成，**不具备跨 Skill 的自主调度权**；
- 制品是**一等应用**，不需要 Claw / WorkBuddy 这类 Agent 宿主加载，可独立测试、版本化、灰度、留痕。

一句话：**把「选哪个 Skill、怎么触发它」的决定权，从通用 Agent 手里收回，固化进制品。**

---

## 2. 问题：多 Skill Agent 的结构性不确定性

Skill 的设计初衷是收敛推理范围、让工作按流程办事、减少无效 Token 开销。但在一个通用 Agent 宿主注册多个 Skill 之后，这套收益会被三个失稳源侵蚀：

### 2.1 路由歧义（Routing Ambiguity）

多个 Skill 并存时，由模型自行判断「当前该调哪一个」。这个判断依赖对话上下文与用户措辞，而 Skill 之间的语义边界天然存在重叠区（例如「整理会议纪要」与「提炼会议待办」）。一旦落入重叠区：

- 选错 Skill → 产出不合规，用户需要多轮纠正；
- 选对 Skill 但参数解析错误 → 表面执行成功，实际结果偏移；
- 两个 Skill 交替触发 → 上下文被互相污染。

### 2.2 引导成本（Prompt Tax）

Skill 的正确触发高度依赖用户的规范表达。用户表达稍有偏差，Agent 就偏离预设流程，需要多轮对话把任务「掰回」正确路径。这部分额外轮次本身就是 Token 消耗与时间成本，**恰好抵消了 Skill 想节省的那部分开销**。也就是说：Skill 节省的是「模型自由发挥的推理 Token」，但新增的是「路由与纠偏的对话 Token」，后者在复杂任务中往往更大。

### 2.3 上下文漂移（Context Drift）

Agent 的对话上下文随轮次累积噪声：历史任务的残留约束、被否决的方案、无关闲聊，都会持续参与后续推理。多 Skill 场景下这种漂移尤其危险——一个早先被讨论过的 Skill 会持续「吸附」后续请求，造成偏题、越界、脱离业务约束。

### 2.4 失稳的根源：通用调度器与专用流程的目标冲突

这不是提示词工程能解决的问题，而是**架构层面的目标冲突**：

| 角色 | 被要求做的事 | 由此带来的性质 |
| --- | --- | --- |
| 通用 Agent | 在开放任务空间里自主规划、动态选择能力 | 高泛化、低确定性 |
| Skill | 在固定流程里稳定复现一类业务 | 低泛化、高确定性 |

把高确定性的 Skill 挂载到高自由度的 Agent 上，Agent 的自由度必然泄漏进 Skill 的执行，Skill 的确定性则无法传导到最终结果。**自由度是宿主给的，不是 Skill 自己争取来的。**

---

## 3. 设计主张

> **确定性应当由制品承载，而不是由宿主的克制承载。**

DFS 的做法是把「调度」这件事在架构上消除，而不是靠提示词去约束：

1. **一个制品只服务一类任务。** 不存在「多个 Skill 之间选一个」的问题——制品本身已经选完了。
2. **Skill 作为规约，不作为运行脚本。** 工作在编译期（transform 阶段）完成一次，而不是在每一轮对话里重新解释 Skill 文本。
3. **模型的自由度被限定在规约边界内。** 它可以决定分支走向、填充参数、组织措辞，但不能新增规约之外的任务、不能切换到别的 Skill、不能改变输出契约。
4. **没有开放式对话循环。** 输入直接面向业务，输出直接交付，不经过「猜用户想干什么」的环节。

---

## 4. 核心设计：四层结构

```
┌──────────────────────────────────────────────────────────┐
│ ① 规约层 Specification                                   │
│   SKILL.md（人类可读的流程、约束、边界）                    │
│   dfs.json（机器可读的契约：IO Schema、模型绑定、工具白名单）│
└──────────────────────────┬───────────────────────────────┘
                           │  transform（模型参与，一次性）
┌──────────────────────────▼───────────────────────────────┐
│ ② 编译层 Compilation                                      │
│   模型读取规约 → 生成 plan.json（步骤 DAG、分支、输出映射） │
│   产出物必须通过 plan schema 校验，越界即失败（fail closed）│
└──────────────────────────┬───────────────────────────────┘
                           │  execute（确定性调度）
┌──────────────────────────▼───────────────────────────────┐
│ ③ 运行层 Runtime                                          │
│   最小运行时：顺序/分支执行、模板渲染、工具白名单、输出校验  │
│   模型只在 llm 步骤内推理，不参与「下一步做什么」的决策      │
└──────────────────────────┬───────────────────────────────┘
                           │  record
┌──────────────────────────▼───────────────────────────────┐
│ ④ 证据层 Evidence                                         │
│   每次运行落盘：规约摘要、计划摘要、逐步记录、输入输出哈希   │
│   支持审计、回归对比、版本回溯                             │
└──────────────────────────────────────────────────────────┘
```

**关键区分：编译时 vs 运行时。**
流程结构在编译期被确定（此时模型可以发挥理解与重组能力），运行期只做确定性执行（此时模型只承担节点内的语义工作）。这正是 DFS 与「每轮对话都重新解释 Skill」的 Agent 模式的根本差异。

---

## 5. 与相邻范式对比

| 范式 | Skill 的角色 | 谁决定「下一步」 | 主要不确定性来源 | 适用场景 |
| --- | --- | --- | --- | --- |
| **Agent + 多 Skill 插件**（Claw / WorkBuddy） | 可被随时调用的插件 | 模型，每轮动态决定 | 路由歧义、对话漂移、用户表达不规范 | 开放式探索、需要动态切换多种能力 |
| **Skill Capsule**（如 SkillRun） | 固化的执行合约 | 合约（打包时锁定） | 流程不可变，缺少适配能力 | 流程完全固定、强确定性的标准任务 |
| **NL → Workflow**（自然语言生成工作流） | 不适用 | 生成的工作流 | 输入是自然语言，非标准规约；生成质量波动大 | 一次性自动化、低复用场景 |
| **DFS（本项目）** | 规约 / 源素材 | 编译期由模型生成计划，运行期由计划决定 | 仅受本规约约束，无跨 Skill 调度 | 专职业务流水线、需稳定可控可审计 |

DFS 与 Skill Capsule 是互补关系，不是替代关系：

- **Capsule**：Skill 合约**静态固化**，Runtime 直接解释执行——确定性最高，柔性最低；
- **DFS**：Skill 规约**动态转化**，由模型生成适配的运行逻辑——保留规约内的柔性，同时切断跨 Skill 调度。

---

## 6. 收益与代价

### 收益

1. **消除路由歧义**：制品与任务一一对应，架构上不存在选错 Skill 的可能。
2. **消除引导成本**：输入直接面向业务字段，不需要用户学习「规范话术」。
3. **抑制上下文漂移**：无开放式对话循环，任务边界由规约锁定，历史不参与后续推理。
4. **Token 结构优化**：Skill 文本只在编译期读一次；运行期上下文只含当前任务数据，而非整个对话历史。
5. **可审计、可回归**：每次运行有完整证据链，可对比两个版本的制品在同一输入下的行为差异。
6. **可独立分发**：每个制品可单独安装、单独升级、单独给第三方使用，不要求对方装 Agent 宿主。

### 代价（必须诚实记录）

1. **失去跨任务泛化**：一个制品不能顺手处理隔壁任务，需要另建制品。
2. **多一道编译工序**：每类任务都要走一次 transform，并对其产出做校验。
3. **制品数量膨胀**：任务种类多时，仓库/制品数量会显著增长，需要目录治理（见第 11 节）。
4. **规约质量决定上限**：Skill 写得含糊，编译出的计划同样含糊——DFS 不放宽对 Skill 质量的要求，只是把问题前移到了编译期，让它可被测出来。

---

## 7. 非目标（Non-goals）

明确不做的事，避免被误读为「又一个 Agent 框架」：

- ❌ 不做通用对话 Agent，不做跨任务自主规划；
- ❌ 不做多 Skill 自动路由/自动选择；
- ❌ 不做 Agent 之间的协商、投票、反思循环；
- ❌ 不追求「一句话什么都能干」，只追求「一类任务稳定干成」；
- ❌ 不替代 Skill Capsule：需要绝对静态确定性的场景应使用 Capsule。

---

## 8. 仓库结构

```
derived-from-skill/
├── README.md                  # 本文件：定位、动因、设计
├── dfs.py                     # 仓库根启动器：python dfs.py <cmd>
├── docs/
│   ├── motivation.md          # 设计动因的理论展开
│   ├── architecture.md        # 四层架构、生命周期、失败策略
│   ├── terminology.md         # 术语表（DFS vs Capsule vs Agent）
│   ├── ui-spec.md             # R2 独立 UI 规范（web / window）
│   ├── model-binding.md       # R3 模型绑定与手动设置（含空 Key 规则）
│   └── related-work.md        # 与现有项目的逐项对照
├── spec/
│   ├── skill-contract.md      # 输入规约要求：SKILL.md 该怎么写
│   ├── provenance.md          # R1 来源声明规范
│   └── capsule-contract.md    # 制品契约：dfs.json / plan.json 字段说明
├── runtime/
│   ├── pyproject.toml
│   └── dfs_runtime/
│       ├── cli.py             # validate / inspect / build / run / serve / window / model / new
│       ├── manifest.py        # 制品加载、来源校验、模型解析
│       ├── compiler.py        # 规约 → 运行计划
│       ├── executor.py        # 计划 → 执行 + 证据
│       ├── runner.py          # 单次运行（CLI / Web / 窗口共用）
│       ├── adapters.py        # 模型适配器（openai-compatible / mock，bearer / none）
│       ├── uigen.py           # schema → 表单描述与类型转换
│       ├── webui.py           # 内置 Web UI（零依赖，仅回环）
│       ├── appwindow.py       # 窗口模式（浏览器 app 窗口）
│       ├── winui.py           # 可选原生窗口（tkinter）
│       ├── schemas/           # manifest / plan 的 JSON Schema
│       └── tools.py           # 内置安全工具集
├── template/                  # 新建 DFS 子项目的脚手架
├── subprojects/
│   └── dfs-hello/             # 可离线跑通的最小示例
├── catalog.md                 # 子项目索引
└── LICENSE
```

---

## 9. 快速开始

前置：Python 3.10+（零第三方依赖）。

```bash
# 校验制品契约（来源声明、UI 声明、Skill 文件、IO Schema、运行计划）
python dfs.py validate subprojects/dfs-hello

# 查看制品摘要（模型绑定、来源、UI、步骤上限、工具白名单）
python dfs.py inspect subprojects/dfs-hello

# 执行制品（离线示例使用 mock 适配器回放计划中的预期输出）
python dfs.py run subprojects/dfs-hello --input subprojects/dfs-hello/input.example.json

# 打开该制品的独立界面（二者共用同一套页面与执行路径）
python dfs.py serve  subprojects/dfs-hello            # 浏览器
python dfs.py window subprojects/dfs-hello            # 独立应用窗口

# 手动指定模型（写入 dfs.local.json，不入库；本地无鉴权端点允许空 Key）
python dfs.py model subprojects/dfs-hello \
  --provider openai-compatible --base-url http://127.0.0.1:11434/v1 \
  --model qwen3 --auth none

# 用真实模型重新编译运行计划（云端鉴权走环境变量，不落盘）
$env:DFS_API_KEY = "<key>"
python dfs.py build subprojects/dfs-hello --provider openai-compatible \
  --base-url https://api.example.com/v1 --model qwen3-35b

# 从模板新建一个子项目
python dfs.py new dfs-invoice --title "发票字段抽取" --ui web
```

运行产物落在 `<制品目录>/runs/<时间戳>-<短哈希>/`，包含 `evidence.jsonl`（逐步证据）与 `result.json`（最终输出）。

---

## 10. 契约一览

| 文件 | 作用 | 谁写 | 是否可变 |
| --- | --- | --- | --- |
| `SKILL.md` | 人类可读的任务规约：目标、输入输出、流程、边界、失败处理 | 人 | 编译前可变 |
| `dfs.json` | 机器契约：制品身份、**Skill 来源声明**、模型绑定与鉴权、**UI 形态**、IO Schema、工具白名单、步骤上限 | 人 | 编译前可变 |
| `dfs.local.json` | 本机手动设置（模型/端点/鉴权），不入库 | 人（`dfs model`） | 随时可变，无需重新编译 |
| `plan.json` | 编译产物：步骤 DAG、提示模板、输出映射 | 模型（编译期） | 运行期只读 |
| `runs/*` | 运行证据 | 运行时 | 追加写 |

原则：**人在规约里表达「要什么」，模型在编译期决定「怎么走」，运行期只按计划执行，界面只负责收发。**

---

## 11. 子项目组织与命名

- 主仓库：`derived-from-skill`（框架、规范、运行时、模板、索引）
- 子项目仓库：`dfs-{skill-name}`，例如 `dfs-invoice`、`dfs-video-pipeline`
- 每个子项目是一个独立可运行的 DFS 制品，内自包含 `SKILL.md` + `dfs.json` + `plan.json`
- 单一 Skill 转化 → 一个子项目；一组协同 Skill 转化 → 一个子项目（`source.skills` 可列多个）
- 本仓库 `subprojects/` 用于孵化；稳定后拆为独立仓库，并在 `catalog.md` 与主 README 登记

---

## 12. 相关项目

| 项目 | 输入源 | 机制 | 与 DFS 的关系 |
| --- | --- | --- | --- |
| SkillRun（`.skr`） | SKILL.md | 静态打包，直接解释执行 | 对照项：Skill Capsule，非 DFS |
| Skillscript | 声明式 Skill 源码 | 解释执行 + 权限审计 | Skill 即执行源码，无编译期转化 |
| SkillFlow | 自然语言 | 模型生成 DAG 后执行 | 输入不是标准 Skill 规约 |
| GitHub Agentic Workflows | Markdown 描述 | 编译为 Actions YAML | 领域限定 CI，转译为确定性文本 |
| skillify | 对话历史 | 反向生成 SKILL.md | 方向相反（Skill ← 对话） |
| Claude Code / Claw 生态 SKILL.md 项目 | SKILL.md | Agent 宿主按需加载 | Skill 为插件，不能脱离宿主 |

详见 `docs/related-work.md`。

---

## 13. 术语

| 术语 | 定义 |
| --- | --- |
| **Skill 规约** | 描述一类任务的目标、IO、流程、边界的文本 + 结构化契约定，本身不直接执行 |
| **DFS（Derived From Skill）** | 以 Skill 规约为源素材，经模型转化生成运行逻辑的独立可运行制品 |
| **Skill Capsule（技能胶囊）** | Skill 合约静态固化、打包即可直接解释执行的制品（对照概念） |
| **transform / 编译** | 把规约转成可执行计划的工序；只在制品构建时发生一次 |
| **plan** | 编译产物：有序步骤、模板、输出映射；运行期只读 |
| **fail closed** | 契约不满足时直接失败，不做降级猜测 |

---

## 14. Roadmap

- [x] 制品契约（`dfs.json`）与运行计划 schema
- [x] 最小运行时：校验、计划执行、输出校验、证据落盘
- [x] 离线 mock 回放（无模型环境也能验证执行链路）
- [x] 来源声明与强制校验（provenance / upstream_url / digest 防篡改）
- [x] 内置独立 UI：Web（浏览器）与 Window（应用窗口），共用同一执行路径
- [x] 模型手动设置（`dfs model`）+ `auth=none` 空 Key 本地端点
- [ ] 真实模型适配器：流式输出、多端点、编译失败重试（仍不降级）
- [ ] 计划版本对比（同一输入，两个 plan 的行为 diff）
- [ ] 子项目脚手架增强：从现有 Claw Skill 目录一键导入并自动生成 provenance
- [ ] 编译期自检：Skill 规约完整性 lint（缺 IO 定义、流程含歧义动词等）

---

## 15. 开发规范（硬性规则）

以下三条是**准入门槛**，不是建议。`dfs validate` 会强制检查，不合规的制品不能进入 `subprojects/`，也不能交付。

### R1 声明 Skill 来源

每个 Skill 文件必须在 `source.provenance` 中声明来源，字段包含 `file` / `origin`，并按需补齐 `upstream_url`、`author`、`license`、`version`、`imported_at`、`digest`。

- 覆盖率必须完整：`source.skills` 有几个文件，provenance 就得有几条，多一条少一条都拒绝加载；
- 来源为 `github` / `clawhub` / `other` 时，`upstream_url` 必填；
- 填了 `digest` 就强制校验，内容被改动即判定「来源被动过」；
- 多 Skill 组合时逐个文件声明，不合并。

> 完整规范：[`spec/provenance.md`](spec/provenance.md)

### R2 独立 UI（web 或 window）

每个制品必须在 `dfs.json` 里声明 `ui.kind`：

| 形态 | 启动方式 | 壳体 |
| --- | --- | --- |
| `web` | `python dfs.py serve <制品>` | 浏览器标签页，默认仅 `127.0.0.1` |
| `window` | `python dfs.py window <制品>` | 无标签栏的独立应用窗口（浏览器 app 模式） |
| `none` | — | 仅库型制品，必须在 `note` 写明理由 |

硬性细节：

- 表单**必须**由 `io.input_schema` 推导，不允许手写字段；
- 两种形态共用同一份页面与同一条执行路径（`runner.run_once`），避免行为分叉；
- 界面必须展示：输入区、运行按钮、结果区、**原文错误**、本次 `runs/` 目录、制品身份与来源、模型与鉴权状态；
- 失败必须原文显示，不美化、不吞错。

> 完整规范：[`docs/ui-spec.md`](docs/ui-spec.md)

### R3 模型可手动设置，允许空 API Key

- 模型配置四层优先级：**CLI 参数 > 环境变量 `DFS_*` > `dfs.local.json` > `dfs.json`**；
- 手动设置走 `dfs model`，写入 `dfs.local.json`（已 `.gitignore`，不入库），无需改契约、无需重新编译；
- `model.auth` 显式声明：`bearer` 必须给 Key；`none` **允许空 Key**，请求不带 `Authorization` 头（用于 Ollama / LM Studio / LocalAI 等本地端点）；
- `dfs.json` **禁止**出现明文 `api_key`（schema 中无此字段）；证据里不记录 Key 与提示词原文，只存哈希；
- 换模型即换制品：必须重新 `build` 并重新验收，不自动降级、不自动重试到别的模型。

> 完整规范：[`docs/model-binding.md`](docs/model-binding.md)

### 三条规则的落地校验

| 规则 | 校验命令 | 失败表现 |
| --- | --- | --- |
| R1 来源 | `dfs validate` | 缺声明 / 外部来源缺 `upstream_url` / digest 不匹配 → 拒绝加载 |
| R2 UI | `dfs validate` + `dfs serve`/`window` | 缺 `ui` → schema 失败；启动失败 → 明确报错 |
| R3 模型 | `dfs model --show` + `dfs build` | 缺 `base_url` / `model`，或 `bearer` 缺 Key → 运行前即失败 |

---

## 16. 发布到 GitHub

本仓库已在本机初始化（分支 `main`，含首个提交），尚未配置远端。两种发布方式：

### A. GitHub Desktop（推荐，无需命令行）

1. 打开 GitHub Desktop → `File` → `Add Local Repository…` → 选择本目录；
2. 首次使用需 `Sign in to GitHub.com` 登录你的账号；
3. 点右上角 `Publish repository`，仓库名保持 `derived-from-skill`，按需取消 `Keep this code private`；
4. 发布后地址形如 `https://github.com/<用户名>/derived-from-skill`。

### B. 命令行（需要 PAT）

在 GitHub → Settings → Developer settings → Personal access tokens 创建带 `repo` 权限的令牌，然后：

```bash
git remote add origin https://github.com/<用户名>/derived-from-skill.git
git push -u origin main
```

> 仓库名使用全称而非 `dfs`，是为了避免与 *Depth-First Search* / *Distributed File System* 混淆；子项目独立成仓时沿用 `dfs-<skill>` 前缀（此时已在本仓库定义语境中，歧义风险低）。

---

## License

MIT，见 [LICENSE](LICENSE)。
