# Issue #01 · Collector Agent

## Depends on

None — 流水线起点，无前置依赖。

## Description

采集 Agent 是流水线的第一个环节。负责从 GitHub Trending 抓取 AI/LLM/Agent 领域的热门项目，按关键词过滤后输出结构化 JSON 到 `knowledge/raw/`。

**数据源：**
- GitHub Trending（每日 Top 50）
- Hacker News（可选，score ≥ 100）

**过滤关键词：** AI, LLM, GPT, Agent, Claude, Transformer, vector database, embeddings, RAG, fine-tuning, diffusion, multimodal, TTS, STT, speech, vision model

## Acceptance Criteria

- [ ] 输出文件：`knowledge/raw/github-trending-{YYYYMMDD}.json`（JSON 数组）
- [ ] 每条数据包含字段：`title`, `url`, `source`, `popularity`, `summary`, `language`, `author`
- [ ] `popularity` 为对象，含 `stars`(int), `stars_today`(int), `score`(int|null), `comments`(int|null)
- [ ] `source` 取值为 `"github_trending"` 或 `"hacker_news"`
- [ ] AI 关键词过滤后结果 ≥ 15 条
- [ ] 同 URL 去重，只保留一条
- [ ] 按 `popularity.stars_today` 降序排列
- [ ] 幂等：同一天重跑不产生重复文件（先检查文件是否已存在）
- [ ] 输出 JSON 通过 `specs/schemas/raw.json` schema 校验

## Schema Reference

→ `specs/schemas/raw.json`
