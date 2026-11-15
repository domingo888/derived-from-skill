# 子项目索引

每个子项目是一个 DFS 制品：由**一份 Skill 规约**（或**一组协同 Skill 规约**）编译而来，独立可运行、可单独验收。

## 命名约定

- 单一 Skill 转化：`dfs-<skill-name>`，例如 `dfs-invoice`
- 一组 Skill 协同转化：`dfs-<domain>-pipeline`，例如 `dfs-video-pipeline`
- 孵化阶段放在本仓库 `subprojects/`；稳定后拆为独立仓库，并在下表登记

## 制品清单

| 制品 | 源规约 / 来源 | 模型绑定 | UI | 步骤 | 状态 |
| --- | --- | --- | --- | --- | --- |
| [`dfs-hello`](subprojects/dfs-hello/) | `SKILL.md`（单个 Skill，origin=original） | `mock-replay`（离线示例，auth=none） | `web`（端口 8787，可用 window 启动） | 2（生成 + 校验） | 可运行 |
| [`dfs-mijing`](subprojects/dfs-mijing/) | `SKILL.md`（单个 Skill，origin=original） | 未预设（`openai-compatible`，`model` 为空，需 `dfs model` 绑定；`auth=none` 允许空 Key） | `web`（端口 8787，可用 window 启动） | 8（观察 + 候选 + 收敛 + 等级 + 地名 + 证据 + 状态） | 草稿 |

## 登记格式

新增子项目时，在本表追加一行，并补齐：

- **制品名**：与 `dfs.json.name`、目录名一致
- **源规约 / 来源**：Skill 文件列表 + `provenance.origin`；外部来源注明 `upstream_url` 与 `license`；一组 Skill 时注明协同关系
- **模型绑定**：`provider / model` + `auth`（`bearer` 需标 Key 来源，`none` 表示允许空 Key）；换模型需重新编译
- **UI**：`web` / `window`，并注明默认端口或窗口尺寸
- **步骤**：计划步骤数与关键步骤
- **状态**：`草稿` / `可运行` / `已验收` / `已独立仓`
