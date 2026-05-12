# Issue #02 · Analyzer Agent

## Depends on

- Issue #01 · Collector Agent — 必须先产出 `knowledge/raw/*.json`

## Description

分析 Agent 是流水线的第二个环节。读取 collector 产出的原始 JSON，调用大模型为每条数据生成中文摘要、评分、标签等分析字段，输出结构化 JSON 到 `knowledge/articles/`。

**输入发现策略：** 读取 `knowledge/raw/` 下所有匹配 `*-*.json` 的文件。

**分析维度（3 维度标签）：**
1. **技术方向**（tech）：agent / rag / multimodal / llm / prompt_engineering / open_source / research_paper / tutorial
2. **质量等级**（quality）：通过 `analysis.score` 字段体现，1-10 分制
3. **适用场景**（scenario）：通过 `analysis.target_audience` 字段描述

## Acceptance Criteria

- [ ] 输入：`knowledge/raw/*.json`，每条符合 `specs/schemas/raw.json`
- [ ] 输出文件：`knowledge/articles/{YYYYMMDD}-{source}-{slug}.json`（slug 从 title 派生）
- [ ] 每条数据在原始字段基础上新增：`id`(UUID v4), `collected_at`(ISO 8601), `tags`, `status`, `published_at`, `metadata`, `analysis`
- [ ] `analysis.summary_cn`：150-200 字中文摘要
- [ ] `analysis.highlights`：1-3 条关键亮点（字符串数组）
- [ ] `analysis.score`：1-10 整数，评分标准如下：
  - 9-10：颠覆性项目，范式创新
  - 7-8：实用工具，可直接用于生产
  - 5-6：值得关注，有学习或参考价值
  - 1-4：可跳过
- [ ] `analysis.score_reason`：评分理由（一句话）
- [ ] `analysis.suggested_tags`：2-5 个小写标签
- [ ] `analysis.target_audience`：目标受众描述
- [ ] **失败处理：** 上游 `knowledge/raw/` 为空或无新文件 → 记 WARNING 日志 + skip，不抛异常
- [ ] **幂等：** 同输入多次运行结果一致（确定性输出）
- [ ] 保留所有原始字段，不丢失数据
- [ ] 输出 JSON 通过 `specs/schemas/analyzed.json` schema 校验

## Schema Reference

- 输入 → `specs/schemas/raw.json`
- 输出 → `specs/schemas/analyzed.json`
