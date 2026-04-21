---
name: github-trending
description: 当需要采集 GitHub 热门开源项目时使用此技能
allowed-tools:
  - Read
  - Grep
  - Glob
  - WebFetch
---

# GitHub Trending 采集技能

自动采集 GitHub 上 AI/LLM/Agent 领域的热门开源项目，生成结构化 JSON 存入知识库。

## 使用场景

- 每日技术动态追踪
- AI/LLM/Agent 领域趋势分析
- 知识库原始数据补充

## 执行步骤

### 第 1 步：搜索热门仓库

通过 GitHub Search API 搜索近期热门仓库：

```
https://api.github.com/search/repositories?q=created:>=YYYY-MM-DD+stars:>50&sort=stars&order=desc&per_page=100
```

可并行请求多个时间窗口（最近 1 天、3 天、7 天）以覆盖不同热度的项目。

### 第 2 步：提取信息

从 API 响应中提取每个仓库的关键字段：

- `full_name` → name
- `html_url` → url
- `stargazers_count` → stars
- `language` → language
- `topics` → topics

### 第 3 步：过滤

对采集结果进行双向过滤：

**纳入标准**（满足任一即可）：
- 仓库 `topics` 或 `description` 包含关键词：`ai`、`llm`、`agent`、`gpt`、`transformer`、`diffusion`、`embedding`、`rag`、`fine-tuning`、`multimodal`、`speech`、`vision`、`nlp`、`machine-learning`、`deep-learning`、`openai`、`anthropic`、`langchain`、`vector-database`

**排除标准**（命中任一即排除）：
- 仓库名以 `awesome-` 开头
- 仓库 `topics` 包含 `awesome-list`
- 仓库描述中仅为链接集合或资源列表，无实质性项目代码

### 第 4 步：去重

检查 `knowledge/raw/github-trending-*.json` 历史文件，按 `url` 字段去重。已存在于最近 7 天历史文件中的仓库跳过，不重复采集。

### 第 5 步：撰写中文摘要

对每个仓库，阅读其 README 或描述，按以下公式撰写中文摘要（200 字以内）：

> **项目名** + **做什么** + **为什么值得关注**

示例：
> NousResearch/hermes-agent — NousResearch 构建的自改进 AI Agent，内置学习循环，可从经验中创建技能并持续进化，支持多平台部署。

### 第 6 步：排序取 Top 15

按 `stars` 降序排列，取前 15 个项目作为最终输出。

### 第 7 步：输出 JSON

将结果写入 `knowledge/raw/github-trending-{YYYY-MM-DD}.json`，格式如下：

```json
{
  "source": "github_trending",
  "skill": "github-trending",
  "collected_at": "2026-04-21T10:30:00+08:00",
  "items": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "summary": "中文摘要，200字以内",
      "stars": 12345,
      "language": "Python",
      "topics": ["ai", "agent", "llm"]
    }
  ]
}
```

## 注意事项

- **API 速率限制**：GitHub API 未认证时限制 10 次/分钟。如需大量请求，从环境变量 `GITHUB_TOKEN` 读取 Token 进行认证（限制提升至 30 次/分钟）。
- **日期格式**：文件名中的日期使用 `YYYY-MM-DD` 格式，`collected_at` 使用 ISO 8601 带时区格式。
- **编码**：写入 JSON 文件时使用 `encoding='utf-8'`，`json.dumps` 参数添加 `ensure_ascii=False`。
- **幂等性**：同一天重复执行时，先检查目标文件是否已存在。若已存在，读取并与新结果合并去重后覆盖写入。
- **日志**：使用 `logging` 模块记录采集过程，包括：请求数、过滤前数量、过滤后数量、最终输出数量。
