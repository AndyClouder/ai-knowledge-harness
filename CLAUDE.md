# AI 知识库助手

自动从 GitHub Trending 和 Hacker News 采集 AI/LLM/Agent 领域技术动态，经 AI 分析后结构化存储为 JSON，并支持多渠道分发（Telegram / 飞书）。

---

## 技术栈

| 类别 | 选型 |
|------|------|
| 语言 | Python 3.12 |
| AI 编排 | Claude Code + 国产大模型（通义千问 / DeepSeek /智谱GLM） |
| Agent 框架 | LangGraph |
| 网页抓取 | OpenClaw |
| 分发渠道 | Telegram Bot API、飞书 Webhook |

---

## 编码规范

- **PEP 8**，行宽 120
- 命名：`snake_case`（变量 / 函数 / 文件名）、`PascalCase`（类）
- 文档字符串：**Google 风格**
- **禁止裸 `print()`**——统一使用 `logging` 模块，通过 `getLogger(__name__)` 获取 logger
- 类型注解：所有公开函数必须有返回值类型注解
- JSON 输出：`json.dumps(data, ensure_ascii=False, indent=2)`

---

## 项目结构

```
.claudecode/
  agents/           # LangGraph Agent 定义（采集 / 分析 / 整理）
  skills/           # Claude Code 技能文件
knowledge/
  raw/              # 采集原始数据（HTML / RSS XML）
  articles/         # AI 分析后的结构化 JSON 条目
```

---

## 知识条目 JSON 格式

每条知识存储为独立 JSON 文件，命名 `{YYYYMMDD}_{source}_{id}.json`：

```json
{
  "id": "string, 唯一标识（UUID v4）",
  "title": "string, 文章标题",
  "source_url": "string, 原文链接",
  "source": "string, 来源（github_trending / hacker_news）",
  "collected_at": "string, ISO 8601 采集时间",
  "summary": "string, AI 生成的中文摘要（200 字以内）",
  "tags": ["string, 领域标签（llm / agent / rag / ...）"],
  "status": "string, 状态（raw / analyzed / published）",
  "published_at": "string | null, 分发时间",
  "metadata": {
    "stars": "int | null, GitHub Stars（仅 github_trending）",
    "score": "int | null, HN 得分（仅 hacker_news）",
    "author": "string | null, 作者",
    "language": "string | null, 编程语言（仅 github_trending）"
  }
}
```

---

## Agent 角色概览

| 角色 | 文件 | 职责 | 输入 | 输出 |
|------|------|------|------|------|
| **采集 Agent** | `agents/collector.py` | 定时抓取 GitHub Trending / HN 的 AI 相关内容 | 采集配置（关键词、频率） | `knowledge/raw/` 下的原始文件 |
| **分析 Agent** | `agents/analyzer.py` | 读取原始数据，调用大模型提取摘要、标签、分类 | `knowledge/raw/` | `knowledge/articles/` 下的结构化 JSON |
| **整理 Agent** | `agents/publisher.py` | 筛选高质量条目，格式化后推送至 Telegram / 飞书 | `knowledge/articles/`（status=analyzed） | 渠道消息 + 更新 status=published |

---

## 红线（绝对禁止）

1. **禁止直接写入生产知识库**——所有入库操作必须经过分析 Agent 校验
2. **禁止硬编码 API Key / Token**——统一从环境变量读取，变量名以 `_API_KEY` 或 `_TOKEN` 结尾
3. **禁止在采集循环中使用同步阻塞 I/O**——必须使用 `asyncio` + `aiohttp`
4. **禁止跳过 JSON Schema 校验**——写入 `knowledge/articles/` 前必须通过 schema 验证
5. **禁止裸 `print()` 调试输出**——使用 `logging`，日志级别：采集用 `INFO`，分析用 `DEBUG`，错误用 `ERROR`
6. **禁止覆盖已有知识条目**——相同 `source_url` 存在时必须更新而非覆盖（保留历史版本）
7. **禁止在 Agent 间传递未序列化的对象**——跨 Agent 通信一律使用 JSON 字符串
