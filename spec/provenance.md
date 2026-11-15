# R1 来源声明规范（Provenance）

> 一句话：**每个 Skill 文件都必须说清「从哪来」，说不清就不许进制品。**

DFS 制品的可信度等于源规约的可信度。没有来源声明的规约，等于一份无法追溯的合同：出了问题不知道找谁，改了内容不知道是谁改的，换版本不知道差在哪。

---

## 1. 硬性要求

`dfs.json` 的 `source.provenance` 是**必填**字段，数组长度必须与 `source.skills` 一一对应。

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `file` | ✅ | 对应 `source.skills` 中的文件路径，必须完全一致 |
| `origin` | ✅ | 来源类型，见下表 |
| `upstream_url` | 条件必填 | `origin` 为 `github` / `clawhub` / `other` 时必填 |
| `author` | 推荐 | 原作者或组织 |
| `license` | 推荐 | 许可证；不确定时写 `unknown`，不要留空假装没有版权问题 |
| `version` | 推荐 | 上游版本或规约版本 |
| `imported_at` | 推荐 | 引入日期 `YYYY-MM-DD` |
| `digest` | 推荐 | `sha256:<64 位>`；填写后运行时强制校验，内容被改动即拒绝加载 |
| `note` | 可选 | 补充说明（授权依据、改写程度等） |

### origin 取值

| 值 | 含义 | 使用场景 |
| --- | --- | --- |
| `original` | 本项目原创 | 自己写的规约 |
| `github` | 来自 GitHub 仓库 | 引用了别人的开源 Skill，**必须填 `upstream_url`** |
| `clawhub` | 来自 Claw / WorkBuddy 生态的技能库 | 从既有 Agent 生态迁移过来 |
| `local-import` | 来自本机既有文件 | 从本地旧项目/旧笔记导入，无法给出公开链接 |
| `other` | 其他来源 | 商业授权、内部知识库等，**必须填 `upstream_url` 或授权依据** |

---

## 2. 运行时强制的三条校验

`dfs validate` / `dfs run` / `dfs serve` 加载制品时都会执行：

1. **覆盖完整**：`source.skills` 中的每个文件都必须有 provenance 条目；少一个即失败。
2. **无多余声明**：provenance 不能声明 `source.skills` 里不存在的文件。
3. **防篡改**：若填写了 `digest`，必须与当前文件内容的 sha256 一致；不一致即认为来源被动过。

另外：外部来源（`github` / `clawhub` / `other`）缺少 `upstream_url` 时直接拒绝加载。

---

## 3. 多 Skill 组合怎么声明

`source.kind: "skill-set"` 时，逐个文件声明，不合并、不含糊：

```json
"source": {
  "kind": "skill-set",
  "skills": ["SKILL.extract.md", "SKILL.validate.md"],
  "provenance": [
    { "file": "SKILL.extract.md", "origin": "original", "author": "domingo888" },
    { "file": "SKILL.validate.md", "origin": "github",
      "upstream_url": "https://github.com/<org>/<repo>/blob/main/skills/validate.md",
      "author": "<原作者>", "license": "MIT", "imported_at": "2026-11-15" }
  ]
}
```

这样可以回答：**这个制品里哪一部分是别人的、哪一部分是自己的、改了什么。**

---

## 4. 变更流程

| 情况 | 必须做的事 |
| --- | --- |
| 引入新 Skill | 新增 provenance 条目，填写 origin 与上游信息 |
| 修改了引入的 Skill 内容 | 在 `note` 里写明改动，更新 `digest`，并**重新 build** |
| 上游发布新版本 | 更新 `version` / `imported_at` / `digest`，重新 build 并重新验收 |
| 来源不再可用 | 保留原条目并把 `license` 记为 `unknown`，在 `note` 说明；不要静默删除痕迹 |

> 原则：**来源信息只增不改，删改都要留痕。** 制品是可交付物，交付物要能被审计。

---

## 5. 示例（本项目 dfs-hello）

```json
"source": {
  "kind": "skill",
  "skills": ["SKILL.md"],
  "provenance": [
    {
      "file": "SKILL.md",
      "origin": "original",
      "author": "domingo888",
      "license": "MIT",
      "version": "0.1.0",
      "imported_at": "2026-11-15",
      "note": "本项目自写的示例规约，非第三方 Skill"
    }
  ]
}
```

---

## 6. 为什么这条规则值得强制

1. **责任可追**：制品交付给客户后，客户能查到规约出处与授权状态。
2. **升级可控**：上游一改，`digest` 立刻暴露差异，避免「悄悄换了别人的 skill」。
3. **合规可查**：许可证信息在制品里，而不是散落在聊天记录里。
4. **协作可分工**：多人维护同一制品时，来源字段明确了各部分归属。
