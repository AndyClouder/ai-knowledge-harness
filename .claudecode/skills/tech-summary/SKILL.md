---
name: tech-summary
description: 当需要对采集的技术内容进行深度分析总结时使用此技能
allowed-tools:
  - Read
  - Grep
  - Glob
  - WebFetch
---

# 技术深度分析技能

对采集到的 AI/LLM/Agent 领域技术动态进行逐条深度分析，提炼技术亮点、发现趋势主题，生成结构化分析报告。

## 使用场景

- 每日采集后的深度分析环节
- 技术周报 / 月报素材生成
- 趋势研判与方向决策参考

## 执行步骤

### 第 1 步：读取采集数据

从 `knowledge/raw/` 目录读取最新采集文件（按文件名日期排序，取最新）：

```
knowledge/raw/github-trending-{YYYY-MM-DD}.json
knowledge/raw/hacker-news-{YYYY-MM-DD}.json
```

合并所有来源的数据，按热度降序排列。

### 第 2 步：逐条深度分析

对每个项目 / 文章，基于其原始描述和页面内容（必要时通过 WebFetch 补充），输出以下字段：

**摘要**（≤ 50 字，中文）：
> 一句话讲清楚项目做什么、为什么值得关注。

**技术亮点**（2-3 个，用事实说话）：
- 必须引用具体技术细节（架构、参数、基准、方法等）
- 禁止空泛赞美（如"设计优雅""社区活跃"）
- 示例：`8B DiT 参数在 GenEval 基准 Overall 得分 0.8856，超越同规模模型`

**评分**（1-10，附一句话理由）：

| 分数 | 含义 | 标准 |
|------|------|------|
| 9-10 | 改变格局 | 开创性技术或范式转移，会重塑领域方向 |
| 7-8 | 直接有帮助 | 实用工具 / 方法，立即可用于生产或研究 |
| 5-6 | 值得了解 | 有趣思路或参考价值，但影响范围有限 |
| 1-4 | 可略过 | 同质化 / 营销为主 / 无实质技术贡献 |

**约束：15 个项目中，9-10 分总计不超过 2 个。** 宁可严苛，不可通胀。

**标签建议**（2-4 个）：
- 从预定义标签池中选取，必要时新增
- 预定义标签池：`llm`、`agent`、`rag`、`multimodal`、`diffusion`、`mcp`、`fine-tuning`、`embedding`、`browser-automation`、`knowledge-graph`、`code-generation`、`security`、`open-source`、`programming-language`、`simulation`、`prompt-engineering`

### 第 3 步：趋势发现

从全部条目的分析中提炼共性：

- **共同主题**：本周多个项目围绕的核心方向（如"Agent 自愈合"、"本地优先 LLM"）
- **新概念 / 新范式**：首次出现或显著升温的概念（附具体项目引用）
- **值得关注的信号**：虽非高分但暗示趋势变化的项目

输出 3-5 条趋势观察，每条需引用至少 2 个具体项目作为依据。

### 第 4 步：输出分析结果

将结果写入 `knowledge/raw/tech-summary-{YYYY-MM-DD}.json`，格式如下：

```json
{
  "source": "tech_summary",
  "skill": "tech-summary",
  "analyzed_at": "2026-04-21T12:00:00+08:00",
  "source_files": [
    "knowledge/raw/github-trending-2026-04-21.json"
  ],
  "items": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "summary": "50字以内中文摘要",
      "highlights": [
        "技术亮点1：具体事实",
        "技术亮点2：具体事实"
      ],
      "score": 8,
      "score_reason": "一句话理由",
      "tags": ["llm", "agent"]
    }
  ],
  "trends": [
    {
      "theme": "趋势主题",
      "description": "趋势描述",
      "evidence": ["project-a", "project-b"]
    }
  ],
  "score_distribution": {
    "transformative": 0,
    "highly_useful": 5,
    "worth_knowing": 7,
    "skippable": 3
  }
}
```

## 注意事项

- **评分纪律**：9-10 分是稀缺资源，每批不超过 2 个。大部分项目应落在 5-8 分区间
- **事实优先**：所有技术亮点必须基于可验证的事实（README、论文、基准数据），不可编造
- **时效性**：`analyzed_at` 使用 ISO 8601 带时区格式，`source_files` 记录本次分析依赖的采集文件
- **编码**：写入 JSON 文件时使用 `encoding='utf-8'`，`json.dumps` 参数添加 `ensure_ascii=False`
- **幂等性**：同一天重复执行时，直接覆盖已有分析文件
