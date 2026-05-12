# AI 知识库助手

自动采集 AI/LLM/Agent 领域技术动态，经 AI 分析后结构化存储，并支持 MCP 协议供 AI 工具检索。

## 功能概览

- **数据采集** — 从 GitHub Trending、Hacker News 等来源自动采集 AI 相关内容
- **AI 分析** — 调用大模型生成中文摘要、标签、评分和目标受众
- **结构化存储** — 每条知识存为独立 JSON，包含元数据和生命周期状态
- **MCP 检索** — 内置 MCP Server，供 Claude Code 等 AI 工具直接搜索知识库
- **多渠道分发** — 支持 Telegram / 飞书推送（规划中）

## 项目结构

```
├── mcp_knowledge_server.py   # MCP Server（搜索/统计/详情）
├── hooks/                     # Git hooks（JSON 校验、质量评分）
│   ├── validate_json.py
│   ├── check_quality.py
│   └── run_if_article.py
├── knowledge/
│   ├── raw/                   # 采集原始数据
│   └── articles/              # AI 分析后的结构化 JSON
├── .claudecode/
│   ├── agents/                # Agent 定义（采集/分析/整理）
│   └── skills/                # Claude Code 技能文件
├── specs/                     # PRD 和 Issue 规范
└── docs/                      # 架构图、设计文档
```

## MCP Server

`mcp_knowledge_server.py` 提供 3 个工具，供 AI 工具通过 MCP 协议（JSON-RPC 2.0 over stdio）访问本地知识库：

| 工具 | 参数 | 功能 |
|------|------|------|
| `search_articles` | `keyword`, `limit=5` | 按关键词搜索标题、摘要、标签 |
| `get_article` | `article_id` | 按 ID 获取文章完整内容 |
| `knowledge_stats` | — | 文章总数、来源分布、热门标签 |

### 注册到 Claude Code

```bash
claude mcp add knowledge -s user -- python /path/to/mcp_knowledge_server.py
```

无第三方依赖，仅使用 Python 标准库。

## 数据格式

每条知识存储为独立 JSON 文件，命名 `{YYYYMMDD}_{source}_{id}.json`：

```json
{
  "id": "UUID v4",
  "title": "文章标题",
  "source_url": "原文链接",
  "source": "github_trending | hacker_news",
  "collected_at": "ISO 8601 采集时间",
  "summary": "AI 生成的中文摘要",
  "tags": ["agent", "llm"],
  "score": 7,
  "status": "analyzed",
  "metadata": {
    "stars": 56000,
    "language": "Python"
  }
}
```

## Agent 流水线

| Agent | 职责 |
|-------|------|
| **采集 Agent** | 抓取 GitHub Trending / HN 的 AI 相关内容 |
| **分析 Agent** | 调用大模型提取摘要、标签、评分 |
| **整理 Agent** | 筛选高质量条目，推送至分发渠道 |

## 技术栈

- **语言**: Python 3.12+
- **AI 编排**: Claude Code + 智谱 GLM
- **协议**: MCP (Model Context Protocol)
- **分发**: Telegram Bot API、飞书 Webhook（规划中）

## 快速开始

```bash
# 1. 克隆仓库
git clone <repo-url>
cd AI知识系统

# 2. 注册 MCP Server（可选）
claude mcp add knowledge -s user -- python "$(pwd)/mcp_knowledge_server.py"

# 3. 验证
claude mcp list
```

## License

MIT
