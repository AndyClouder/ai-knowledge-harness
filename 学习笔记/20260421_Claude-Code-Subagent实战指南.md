# Claude Code Subagent 实战指南

> **日期**：2026-04-21
> **项目**：AI 知识库助手（[ai-knowledge-harness](https://github.com/AndyClouder/ai-knowledge-harness)）
> **场景**：用 Subagent 构建采集→分析→整理三阶段知识流水线

---

## 1. 从一个真实需求说起

我们的项目需要自动从 GitHub Trending 和 Hacker News 采集 AI 领域热门项目，经 AI 深度分析后结构化存储为 JSON 文件。

如果让一个 Agent 干所有事，prompt 会极其冗长，上下文窗口很快撑爆，而且任何一步出错都要从头来。

**Subagent 解决的核心问题：把复杂任务拆成独立工序，每个 Agent 只管自己那一摊，主进程当调度员。**

最终效果：我们在一次对话中跑通了完整流水线，采集 10 条 GitHub Trending 项目，生成 12 个标准化 JSON 文件。

---

## 2. 什么是 Subagent

Claude Code 提供了 `Agent` 工具，允许主对话**派生子 Agent** 执行独立任务。子 Agent：

- 拥有**独立的上下文窗口**（不占用主对话的 token）
- 可以使用**受限的工具集**（由 agent 定义文件控制）
- 运行完毕后将结果**文本返回**给主对话
- 主对话负责**合并结果、保存文件、驱动下一步**

关键参数一览：

| 参数 | 作用 | 示例 |
|------|------|------|
| `description` | 子 Agent 任务简述（3-5 词） | `"采集 GitHub Trending AI 项目"` |
| `model` | 指定模型，覆盖 agent 定义的默认值 | `sonnet` / `opus` / `haiku` |
| `subagent_type` | 子 Agent 类型 | `general-purpose`（通用） |
| `prompt` | 完整的任务指令（自包含，子 Agent 看不到之前的对话） | 见下文实战示例 |
| `isolation` | 隔离模式，`worktree` 创建独立 git 工作树 | 默认不隔离 |
| `run_in_background` | 后台运行，完成后自动通知 | `true` / `false` |

**最重要的一点：prompt 必须自包含。** 子 Agent 是全新的上下文，它不知道主对话中发生了什么。

---

## 3. Agent 定义文件

每个 Agent 有自己的定义文件，放在 `.claudecode/agents/` 目录下，采用 Markdown + YAML frontmatter 格式。

### 文件结构模板

```markdown
---
name: agent_name              # 唯一标识符
description: 一句话描述职责     # 出现在 agent 选择列表中
model: sonnet                  # 默认使用的模型
allowed-tools:                 # 白名单，只能用这些工具
  - Read
  - Grep
  - Glob
  - WebSearch
---

# Agent 名称 — agent_name

Agent 的详细角色说明、输入输出格式、业务规则...
```

### 我们项目的三个 Agent

```
.claudecode/agents/
├── collector.md    # 采集：从 GitHub/HN 抓取原始数据
├── analyzer.md     # 分析：生成中文摘要、评分、标签
└── organizer.md    # 整理：去重、校验、标准化、入库
```

三个 Agent 的 `allowed-tools` 设计体现了**最小权限原则**：

| Agent | 可用工具 | 理由 |
|-------|---------|------|
| collector | Read, Grep, Glob, WebFetch, WebSearch | 只需要搜索和读取网页 |
| analyzer | Read, Grep, Glob, WebFetch, WebSearch | 同上，可能需要补充搜索原文 |
| organizer | Read, Grep, Glob, **Write, Edit** | 唯一需要写入文件的 Agent |

> **设计决策**：collector 和 analyzer **不写文件**，只返回 JSON 字符串给主进程。这避免了并发写入冲突，也让主进程对数据流有完全控制。

---

## 4. 实战 Step 1：采集 Agent

### 目标

从 GitHub Trending 抓取本周 AI 领域 Top 10 热门项目，返回结构化 JSON。

### 委派代码

```python
Agent(
    description="采集 GitHub Trending AI 项目",
    model="sonnet",
    subagent_type="general-purpose",
    prompt="""
你是采集 Agent（collector），负责从 GitHub Trending 采集 AI/LLM/Agent 领域的热门开源项目。

## 任务
搜集本周 AI 领域的 GitHub 热门开源项目 Top 10。

## 筛选规则
- 今日 Stars ≥ 50，与 AI/ML/LLM/Agent 相关
- 排除纯教程/awesome 列表（除非 Stars ≥ 5000）

## 输出格式
返回一个 JSON 数组，每个元素：
{
  "title": "owner/repo",
  "url": "完整 GitHub 链接",
  "source": "github_trending",
  "popularity": { "stars": int, "stars_today": int, "score": null, "comments": null },
  "summary": "简要描述（50字以内，中文）",
  "language": "主要编程语言",
  "author": "仓库作者"
}

## 要求
- 使用 WebSearch 搜索 GitHub trending 数据
- 条目恰好 10 条，按热度降序排列
- 最终以纯 JSON 数组形式返回，不要包含其他文本
"""
)
```

### 关键技巧

1. **prompt 末尾强调输出格式**："以纯 JSON 数组形式返回，不要包含其他文本" — 子 Agent 有时会加解释文字，需要明确约束。

2. **把 agent 定义中的业务规则内联到 prompt 里** — 虽然有 `.md` 定义文件，但 Agent 工具的 prompt 参数才是子 Agent 实际看到的指令。定义文件更多是给人看的文档。

3. **主进程负责保存返回结果**：

```python
# 子 Agent 返回的 JSON 文本，由主进程解析并保存
Write(
    file_path="knowledge/raw/github-trending-20260420.json",
    content=result  # 子 Agent 返回的 JSON 字符串
)
```

---

## 5. 实战 Step 2：分析 Agent（并行拆分）

### 目标

对 10 条采集数据进行深度分析，生成中文摘要、亮点、评分和标签。

### 并行策略

10 条数据如果串行分析，等待时间翻倍。我们将数据拆成两组，**同时派发两个 analyzer 实例**：

```python
# 在一条消息中同时发出两个 Agent 调用（并行执行）
Agent(
    description="分析前5条GitHub项目",
    model="sonnet",
    subagent_type="general-purpose",
    prompt="...对以下 5 条数据进行深度分析...\n{前5条JSON数据}"
)

Agent(
    description="分析后5条GitHub项目",
    model="sonnet",
    subagent_type="general-purpose",
    prompt="...对以下 5 条数据进行深度分析...\n{后5条JSON数据}"
)
```

### 为什么能并行

- 两组数据**完全独立**，没有依赖关系
- 两个 analyzer 实例**各自有独立上下文**，互不干扰
- 主进程在**两个都完成后**才合并结果

### prompt 中的评分标准（来自 analyzer.md）

```
| 分数 | 等级     | 判断依据                           |
|------|----------|------------------------------------|
| 9-10 | 改变格局 | 重大架构创新、新范式、头部实验室里程碑 |
| 7-8  | 直接有帮助 | 可直接用于生产的高质量工具/框架       |
| 5-6  | 值得了解 | 有一定创新性，特定场景有用            |
| 1-4  | 可略过   | 教程搬运、重复造轮子、纯营销          |

9-10 分应很稀缺（每批 ≤ 2 条），大部分在 5-8 分。
```

### 合并结果

两个子 Agent 都返回后，主进程将两组 JSON 数组合并为完整的 10 条数据：

```python
# 主进程读取两个结果，合并为一个数组
combined = analyzer_result_1 + analyzer_result_2

# 然后交给下一步 organizer 处理
```

### 实际运行效果

两组并行分析在约 1 分钟内完成（vs 串行约 2 分钟），评分分布符合预期：

| 评分 | 数量 | 项目 |
|------|------|------|
| 9 | 2 | hermes-agent, VoxCPM |
| 8 | 1 | markitdown |
| 7 | 5 | Archon, voicebox, multica, claude-mem, GenericAgent |
| 6 | 2 | ai-hedge-fund, evolver |

---

## 6. 实战 Step 3：整理 Agent

### 目标

去重检查 → Schema 校验 → 格式标准化 → 写入独立 JSON 文件。

### 与前两步的区别

organizer 是**唯一有写入权限的 Agent**（`allowed-tools` 包含 `Write` 和 `Edit`）。

### 去重逻辑

```python
# organizer 在写入前检查已有文件
# 1. 列出 knowledge/articles/ 下所有 .json（排除 analyzed-*.json）
# 2. URL 归一化：去除尾部 /、?utm_source=*、#*
# 3. 新 score ≥ 旧 score → 创建新版本；否则跳过
```

### Schema 校验

每条数据必须符合标准格式：

```json
{
  "id": "UUID v4",
  "title": "string, 必填",
  "source_url": "string, 必填, https://",
  "source": "github_trending | hacker_news",
  "collected_at": "ISO 8601",
  "analyzed_at": "ISO 8601, ≥ collected_at",
  "summary": "50-300 字符",
  "highlights": ["1-3 条"],
  "score": "int, 1-10",
  "score_reason": "string, ≤ 100 字符",
  "tags": ["2-5 个小写标签"],
  "target_audience": "string, ≤ 100 字符",
  "status": "analyzed",
  "published_at": null,
  "metadata": {
    "stars": "int | null",
    "stars_today": "int | null",
    "score": "int | null",
    "comments": "int | null",
    "language": "string | null",
    "author": "string | null"
  }
}
```

校验失败 → 跳过该条目，记录原因。

### 文件命名规则

```
{YYYYMMDD}-{source}-{slug}.json

示例：
20260420-github_trending-hermes-agent.json
20260420-github_trending-markitdown.json
20260420-github_trending-voxcpm.json
```

slug 生成：标题关键词 → 小写 → 特殊字符转 `-` → 截断 50 字符 → 重名追加 `-2`。

### 返回结果

organizer 处理完成后返回汇总报告：

```json
{
  "total_input": 10,
  "new_entries": 10,
  "updated_entries": 0,
  "skipped_entries": 0,
  "skipped_details": [],
  "written_files": [
    "knowledge/articles/20260420-github_trending-hermes-agent.json",
    "knowledge/articles/20260420-github_trending-markitdown.json",
    ...
  ]
}
```

---

## 7. 关键设计原则

从本次实战中提炼出 5 条核心原则：

### 7.1 单一职责

每个 Agent 只管一道工序。collector 只采集不分析，analyzer 只分析不存储，organizer 只整理不采集。

**好处**：prompt 简短精准，出错时可以单独重跑某一步。

### 7.2 无状态 + JSON 数据流

Agent 之间不传递 Python 对象，一律通过 JSON 字符串通信。

```
collector → JSON 字符串 → 主进程解析 → analyzer → JSON 字符串 → 主进程合并 → organizer
```

**好处**：每个 Agent 可独立运行和调试，数据流可审计。

### 7.3 主进程统一保存文件

collector 和 analyzer 的 `allowed-tools` 不包含 `Write`，只有 organizer 能写文件。

**好处**：避免并发写入冲突；主进程对最终数据有完全控制权，可以做二次校验。

### 7.4 权限最小化

每个 Agent 的 `allowed-tools` 精确到具体工具：

- collector/analyzer：`Read, Grep, Glob, WebSearch`（只读 + 搜索）
- organizer：`Read, Grep, Glob, Write, Edit`（增加写入）

**好处**：即使 prompt 被注入恶意指令，Agent 也无法执行超出权限的操作。

### 7.5 并行拆分无依赖数据

当数据条目较多（≥ 8 条）时，将 analyzer 拆成两组并行处理。

**前提条件**：两组数据之间没有依赖关系，结果顺序不影响最终合并。

---

## 8. 踩坑记录

### 坑 1：Agent 定义路径记错

用户说"读取 `.opencode/agents/collector.md`"，实际路径是 `.claudecode/agents/collector.md`。

**解决**：用 `Glob("**/*collector*")` 搜索正确路径，不纠结于用户给的错误路径。

**经验**：agent 定义文件的位置取决于项目配置，没有固定标准。先用搜索确认。

### 坑 2：子 Agent 返回结果带废话

子 Agent 有时在 JSON 前后加解释文字，如"以下是分析结果：\n```json\n...\n```\n希望对你有帮助"。

**解决**：在 prompt 中明确要求"以纯 JSON 数组形式返回，不要包含其他文本"。主进程解析时也要做容错处理。

### 坑 3：Windows 编码

项目 CLAUDE.md 中明确要求：所有涉及中文内容的文件读写必须指定 `encoding='utf-8'`，`json.dumps` 加 `ensure_ascii=False`。

**解决**：organizer 的 prompt 中特别强调写入时使用这两个参数。

### 坑 4：并行 Agent 的结果顺序

两个并行 analyzer 返回结果的顺序可能和输入不一致。主进程合并时需要确认条目数量正确（5+5=10），而不是依赖顺序。

### 坑 5：SSH 推送失败

`git push` 到 GitHub 时 SSH 密钥未配置（`Permission denied (publickey)`）。

**解决**：切换到 HTTPS 协议推送：`git remote set-url origin https://github.com/...`

---

## 9. 总结：完整架构一览

```
┌─────────────────────────────────────────────────────────┐
│                     主进程 (Main Process)                 │
│                                                           │
│  1. 读取 agent 定义文件 (.claudecode/agents/*.md)         │
│  2. 委派 collector subagent                               │
│  3. 保存采集结果到 knowledge/raw/                          │
│  4. 并行委派 2 个 analyzer subagent                       │
│  5. 合并分析结果                                          │
│  6. 委派 organizer subagent                              │
│  7. 验证写入结果                                          │
│  8. Git 提交并推送                                        │
└─────┬──────────┬──────────┬──────────────────────────────┘
      │          │          │
      ▼          ▼          ▼
 ┌─────────┐ ┌─────────┐ ┌──────────┐
 │Collector│ │Analyzer │ │Organizer │
 │(只读)   │ │(只读)   │ │(读写)    │
 └────┬────┘ └────┬────┘ └────┬─────┘
      │           │           │
      ▼           ▼           ▼
   WebSearch   WebSearch   Write files
   GitHub.com  补充搜索    knowledge/articles/
      │           │           │
      └─────JSON data flow────┘

数据演进：
  raw JSON → analyzed JSON → standardized JSON files
  (10条)      (10条+analysis)  (10个独立文件)
```

### 最终产出

```
knowledge/
├── raw/
│   └── github-trending-20260420.json          # 采集原始数据
└── articles/
    ├── analyzed-20260420.json                  # 分析汇总文件
    ├── 20260420-github_trending-hermes-agent.json   # ★9
    ├── 20260420-github_trending-markitdown.json      # ★8
    ├── 20260420-github_trending-voxcpm.json          # ★9
    ├── 20260420-github_trending-archon.json          # ★7
    ├── 20260420-github_trending-voicebox.json        # ★7
    ├── 20260420-github_trending-multica.json         # ★7
    ├── 20260420-github_trending-claude-mem.json      # ★7
    ├── 20260420-github_trending-genericagent.json    # ★7
    ├── 20260420-github_trending-ai-hedge-fund.json   # ★6
    └── 20260420-github_trending-evolver.json         # ★6
```

一次对话，三道工序，12 个文件，流水线完整跑通。
