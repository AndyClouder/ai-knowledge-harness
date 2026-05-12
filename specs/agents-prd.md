# AI 知识库系统 — Agent 编排 PRD

> **状态：** Draft
> **创建日期：** 2026-04-21
> **负责人：**
> **版本：** 0.1

---

## 1. 背景与目标

_TBD_

## 2. 用户画像

_TBD_

## 3. 核心功能

_TBD_

## 4. 系统架构

_TBD_

## 5. 数据模型

_TBD_

## 6. Agent 定义

### 6.1 采集 Agent (Collector)

- **职责：** 抓取 GitHub Trending Top 50，过滤 AI 相关项目
- **输入：** 采集配置（关键词列表、频率）
- **输出：** `knowledge/raw/` 下的原始数据文件

### 6.2 分析 Agent (Analyzer)

- **职责：** 读取原始数据，为每条打 3 维度标签
- **输入：** `knowledge/raw/` 下的原始文件
- **输出：** `knowledge/articles/` 下的结构化 JSON

### 6.3 整理 Agent (Organizer)

- **职责：** 读取已标注条目，整理成 Markdown
- **输入：** `knowledge/articles/`（已标注条目）
- **输出：** 整理后的 MD 文件

## 7. 接口设计

_TBD_

## 8. 非功能需求

_TBD_

## 9. 里程碑与交付计划

_TBD_

## 10. 风险与缓解

_TBD_

## 11. 开放问题

> 用 `/to-issues` 细化成 GitHub Issues

- **上游失败下游怎么办？** — collector 抓取失败时，analyzer / organizer 的降级策略
- **数据怎么传？** — Agent 间传递方式：文件 or 消息？
- **重跑策略？** — 单个 Agent 失败后的重试 / 重跑机制
- **进度追踪？** — Pipeline 执行状态的可见性（日志 / 状态文件 / 通知）
