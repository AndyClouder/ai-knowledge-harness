---
name: wechat-article
description: 从本地部署的 we-mp-rss 服务采集微信公众号 AI/LLM/Agent 领域技术文章。当需要采集微信公众号技术文章、追踪 AI 领域公众号动态时使用此技能。
allowed-tools:
  - Read
  - Grep
  - Glob
  - WebFetch
---

# 微信公众号文章采集技能

通过本地部署的 [we-mp-rss](https://github.com/rachelos/we-mp-rss) 服务采集微信公众号 AI/LLM/Agent 领域的技术文章，生成结构化 JSON 存入知识库。

## 前置条件

- 本机已部署 we-mp-rss 服务（Docker 或源码部署）
- 服务地址从环境变量 `WE_MP_RSS_URL` 读取，默认值 `http://localhost:8001`
- 已在 we-mp-rss 中订阅目标公众号（通过 Web 管理界面添加）

## 使用场景

- 每日 AI 技术文章追踪（补充 GitHub Trending 以外的中文技术视角）
- AI/LLM/Agent 领域国内技术动态收集
- 知识库中文内容源补充

## 目标公众号（建议订阅）

以下为 AI/LLM/Agent 领域高质量技术公众号，建议在 we-mp-rss 中优先订阅：

| 公众号 | 方向 | 说明 |
|--------|------|------|
| 机器之心 | AI 综合前沿 | AI 领域头部媒体，覆盖论文解读和行业动态 |
| 新智元 | AI 综合前沿 | AI 行业新闻和深度分析 |
| 量子位 | AI 综合前沿 | AI 技术解读和产业报道 |
| 夕小瑶科技说 | NLP/LLM | 学术论文解读，偏 NLP/LLM 方向 |
| Hugging Face | 开源/LLM | Hugging Face 官方中文，开源模型和工具 |
| LangChain 中文 | Agent/RAG | LangChain 官方中文，Agent 和 RAG 实践 |
| 程序员小明 | 工程化 | AI 工程化落地实践 |
| GitHub 科技 | 开源 | GitHub 热门项目解读 |

> 用户可在 we-mp-rss 管理界面自由增删订阅，此列表仅为建议。

## 执行步骤

### 第 1 步：获取 RSS 订阅列表

从 we-mp-rss 服务获取已订阅的公众号列表：

```
GET {WE_MP_RSS_URL}/rss
```

解析返回的 RSS XML，提取每个 `<item>` 中的：
- `<title>` → 公众号名称（mp_name）
- `<link>` → 该公众号的 RSS 链接（feed_url）

### 第 2 步：获取各公众号最新文章

遍历每个公众号的 feed_url，获取最新文章：

```
GET {WE_MP_RSS_URL}/rss/{feed_id}?limit=50&offset=0
```

也可通过全量接口一次性获取所有公众号的最新文章：

```
GET {WE_MP_RSS_URL}/rss/all?limit=100&offset=0
```

从返回的 RSS XML 中提取每篇文章的字段：

| RSS 字段 | 映射到 | 说明 |
|----------|--------|------|
| `<title>` | title | 文章标题 |
| `<link>` | url | 文章原文链接 |
| `<description>` | description | 文章摘要/描述 |
| `<pubDate>` | publish_date | 发布时间 |
| `feed.name` | account | 所属公众号名称 |
| `content:encoded` | content | 文章正文（若 RSS 包含全文） |

若 RSS 不包含正文，通过 WebFetch 访问文章链接获取内容：
- 链接格式 A（本地缓存）：`{WE_MP_RSS_URL}/rss/content/{content_id}`
- 链接格式 B（微信原文）：`https://mp.weixin.qq.com/s/xxxxxx`

### 第 3 步：过滤

对采集结果进行双向过滤：

**纳入标准**（满足任一即可）：
- 文章内容涉及以下技术话题：AI、LLM、大模型、Agent、RAG、MCP、Diffusion、Embedding、Fine-tuning、多模态、NLP、Prompt Engineering、向量数据库、知识图谱
- 文章对开源 AI 项目进行技术解读或实战分析
- 文章介绍 AI 工程化落地经验或架构设计
- 文章发布时间在最近 **7 天**内

**排除标准**（命中任一即排除）：
- 广告、营销推广、课程售卖
- 非技术内容（行业新闻简讯、融资消息、人事变动）
- 纯搬运/转载且无原创分析
- 标题党但内容空洞（无实质技术内容）

### 第 4 步：去重

检查 `knowledge/raw/wechat-article-*.json` 历史文件，按 `url` 字段去重。已存在于最近 7 天历史文件中的文章跳过。

同时检查 `knowledge/raw/github-trending-*.json` 和 `knowledge/raw/hacker-news-*.json`，若文章内容与已采集的 GitHub 项目高度重合（如同一项目的介绍文章），在 `related_github_url` 字段中记录关联。

### 第 5 步：撰写中文摘要

对每篇文章，基于正文内容（优先使用 RSS 中的 `content:encoded` 或通过 WebFetch 获取），按以下公式撰写中文摘要（200 字以内）：

> **核心观点/技术方案** + **具体技术细节** + **价值/启发**

示例：
> 文章详解了基于 RAG 的企业知识库搭建方案，采用 LangChain + Milvus 技术栈，通过混合检索（BM25 + 向量相似度）将检索准确率从 72% 提升至 91%，并分享了处理长文档切分和幻觉问题的实战经验。

### 第 6 步：排序取 Top 15

按发布时间降序排列，结合内容质量做微调：
1. 发布时间近的文章优先
2. 有原创技术分析/实战经验的文章优先于纯资讯
3. 同一公众号每天最多取 3 篇，避免单一来源占比过高

取前 **10-15 篇**文章作为最终输出。

### 第 7 步：输出 JSON

将结果写入 `knowledge/raw/wechat-article-{YYYY-MM-DD}.json`，格式如下：

```json
{
  "source": "wechat_article",
  "skill": "wechat-article",
  "collected_at": "2026-04-21T10:30:00+08:00",
  "rss_service": "http://localhost:8001",
  "items": [
    {
      "title": "文章标题",
      "url": "https://mp.weixin.qq.com/s/xxxxxxxx",
      "account": "公众号名称",
      "author": "作者署名",
      "summary": "中文摘要，200字以内",
      "publish_date": "2026-04-20",
      "tags": ["llm", "rag"],
      "related_github_url": null
    }
  ]
}
```

## 注意事项

- **服务可用性**：采集前先检测 `{WE_MP_RSS_URL}/rss` 是否可访问，若服务未启动则跳过并记录日志
- **RSS 解析**：we-mp-rss 返回标准 RSS 2.0 XML，使用 XML 解析库提取字段，不要依赖正则
- **链接优先级**：优先使用 we-mp-rss 本地缓存链接（`/rss/content/{id}`），避免直接请求微信域名触发反爬
- **日期格式**：文件名中的日期使用 `YYYY-MM-DD` 格式，`collected_at` 使用 ISO 8601 带时区格式
- **编码**：写入 JSON 文件时使用 `encoding='utf-8'`，`json.dumps` 参数添加 `ensure_ascii=False`
- **幂等性**：同一天重复执行时，先检查目标文件是否已存在。若已存在，读取并与新结果合并去重后覆盖写入
- **日志**：使用 `logging` 模块记录采集过程，包括：订阅公众号数、获取文章数、过滤前数量、过滤后数量、最终输出数量
