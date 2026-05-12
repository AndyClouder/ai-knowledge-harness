# Issue #03 · Organizer Agent

## Depends on

- Issue #02 · Analyzer Agent — 必须先产出 `knowledge/articles/*.json`（status=analyzed）

## Description

整理 Agent 是流水线的第三个环节。读取 analyzer 产出的结构化 JSON，执行去重、校验后整理成 Markdown 日报，输出到 `knowledge/organized/`。

**输入发现策略：** 读取 `knowledge/articles/` 下所有 status=analyzed 的条目。

**去重规则：** 按 `source_url` 归一化去重，同 URL 只保留 `analysis.score` 更高的版本。

## Acceptance Criteria

- [ ] 输入：`knowledge/articles/*.json`，每条 status=analyzed
- [ ] **去重：** URL 归一化（去掉末尾 `/`、统一小写）后，同 URL 保留高分版本
- [ ] **校验：** 每条数据通过 `specs/schemas/analyzed.json` schema 校验
- [ ] 输出文件：`knowledge/organized/{YYYYMMDD}_digest.md`
- [ ] Markdown 格式包含每个条目的：标题、中文摘要（summary_cn）、标签（tags）、链接（source_url）、评分（score）
- [ ] 按评分降序排列
- [ ] **幂等：** 同一天重跑输出内容一致
- [ ] 输出处理统计：总数 / 新增 / 更新 / 跳过
- [ ] 上游 `knowledge/articles/` 为空 → 记 WARNING 日志 + skip，不抛异常

## Schema Reference

- 输入 → `specs/schemas/analyzed.json`
