# dfs-hello

最小 DFS 制品示例：把一个「按名字生成问候语」的 Skill 规约，编译成可独立执行的两步计划。

## 结构

| 文件 | 作用 |
| --- | --- |
| `SKILL.md` | 规约：目标、输入输出、流程、边界 |
| `dfs.json` | 契约：来源声明、模型绑定与鉴权、IO Schema、UI 形态、步骤上限、工具白名单（空） |
| `plan.json` | 编译产物：`greet`（生成） → `guard`（校验包含名字） |
| `input.example.json` | 示例输入 |

## 运行

```bash
python dfs.py validate subprojects/dfs-hello
python dfs.py inspect  subprojects/dfs-hello
python dfs.py run      subprojects/dfs-hello
```

## 独立界面

```bash
python dfs.py serve  subprojects/dfs-hello     # 浏览器：http://127.0.0.1:8787/
python dfs.py window subprojects/dfs-hello     # 无标签栏的独立窗口
```

两种形态共用同一页面与同一条执行路径：表单由 `io.input_schema` 生成，运行结果与 `runs/` 目录同时返回。

## 换成真实模型

```bash
# 本地无鉴权端点（允许空 Key）
python dfs.py model subprojects/dfs-hello --provider openai-compatible \
  --base-url http://127.0.0.1:11434/v1 --model qwen3 --auth none

# 云端（鉴权走环境变量，不落盘）
$env:DFS_API_KEY = "<key>"
python dfs.py model subprojects/dfs-hello --provider openai-compatible \
  --base-url https://api.example.com/v1 --model qwen3-35b
python dfs.py build subprojects/dfs-hello
python dfs.py run   subprojects/dfs-hello
```

## 为什么这个例子有意义

它把「确定性」演示完整了：`guard` 步骤是对规约「输出必须包含 name」这一条的机械校验。真实模型给出不合规文本时，制品会失败，而不是悄悄交付一个看似合理的答案。
