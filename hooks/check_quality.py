#!/usr/bin/env python3
"""知识条目 5 维度质量评分。

用法:
    python hooks/check_quality.py <file.json> [file2.json ...]
    python hooks/check_quality.py knowledge/articles/*.json

退出码:
    0 — 全部 A/B 级
    1 — 存在 C 级条目
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# 标准标签库 & 空洞词黑名单
# ---------------------------------------------------------------------------

STANDARD_TAGS: frozenset[str] = frozenset({
    "llm", "agent", "rag", "fine_tuning", "prompt_engineering",
    "multimodal", "embedding", "vector_database", "knowledge_graph",
    "quantization", "open_source", "research_paper", "tutorial",
    "benchmark", "speech", "tts", "stt", "vision_model",
    "diffusion", "transformer", "reinforcement_learning",
})

BUZZWORDS_ZH: tuple[str, ...] = (
    "赋能", "抓手", "闭环", "打通", "全链路", "底层逻辑", "颗粒度",
    "对齐", "拉通", "沉淀", "强大的", "革命性的",
)

BUZZWORDS_EN: tuple[str, ...] = (
    "groundbreaking", "revolutionary", "game-changing", "cutting-edge",
    "disruptive", "next-generation", "industry-leading", "world-class",
    "paradigm-shifting", "state-of-the-art", "bleeding-edge",
    "leverage", "synergy", "holistic", "comprehensive",
)

ALL_BUZZWORDS: tuple[str, ...] = BUZZWORDS_ZH + BUZZWORDS_EN

# 技术关键词（用于摘要质量奖励）
TECH_KEYWORDS: tuple[str, ...] = (
    "模型", "算法", "架构", "API", "框架", "训练", "推理", "微调",
    "向量", "嵌入", "注意力", "Transformer", "RAG", "Agent",
    "开源", "分布式", "多模态", "量化", "蒸馏", "prompt",
    "fine-tuning", "embedding", "attention", "inference",
)

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class DimensionScore:
    """单个维度的评分结果。"""

    name: str
    max: int
    score: int
    details: str = ""


@dataclass
class QualityReport:
    """一条知识条目的质量报告。"""

    title: str
    file_path: str
    dimensions: list[DimensionScore] = field(default_factory=list)
    total: int = 0
    grade: str = "C"

    def __post_init__(self) -> None:
        self.total = sum(d.score for d in self.dimensions)
        if self.total >= 80:
            self.grade = "A"
        elif self.total >= 60:
            self.grade = "B"
        else:
            self.grade = "C"


# ---------------------------------------------------------------------------
# 评分函数
# ---------------------------------------------------------------------------


def _score_summary(item: dict) -> DimensionScore:
    """摘要质量 (25 分)。

    - >= 50 字: 满分基础 20 + 技术关键词奖励最多 5
    - >= 20 字: 基础 12 + 关键词奖励
    - < 20 字: 基础 0 + 关键词奖励
    """
    summary = item.get("summary", "")
    # 也检查 analysis.summary_cn（如果存在且更长，取更长的）
    analysis = item.get("analysis", {})
    if isinstance(analysis, dict):
        cn = analysis.get("summary_cn", "")
        if isinstance(cn, str) and len(cn) > len(summary):
            summary = cn

    length = len(summary)

    if length >= 50:
        base = 20
    elif length >= 20:
        base = 12
    else:
        base = 0

    # 技术关键词奖励：每个关键词 1 分，最多 5 分
    kw_count = sum(1 for kw in TECH_KEYWORDS if kw.lower() in summary.lower())
    bonus = min(kw_count, 5)

    score = min(base + bonus, 25)
    details = f"字数={length}, 基础={base}, 关键词={kw_count}, 奖励={bonus}"
    return DimensionScore(name="摘要质量", max=25, score=score, details=details)


def _score_depth(item: dict) -> DimensionScore:
    """技术深度 (25 分)。

    基于 analysis.score（1-10）线性映射到 0-25。
    无 score 字段则给 0 分。
    """
    analysis = item.get("analysis", {})
    if isinstance(analysis, dict):
        raw = analysis.get("score")
    else:
        raw = None

    if isinstance(raw, (int, float)) and 1 <= raw <= 10:
        score = round(raw / 10 * 25)
        details = f"analysis.score={raw}"
    else:
        score = 0
        details = "无 score 字段"

    return DimensionScore(name="技术深度", max=25, score=score, details=details)


def _score_format(item: dict) -> DimensionScore:
    """格式规范 (20 分)。

    id、title、source_url、status、时间戳 五项各 4 分。
    """
    checks = [
        ("id", isinstance(item.get("id"), str) and len(item.get("id", "")) > 0),
        ("title", isinstance(item.get("title"), str) and len(item.get("title", "")) > 0),
        ("source_url", isinstance(item.get("source_url"), str)
         and item.get("source_url", "").startswith(("http://", "https://"))),
        ("status", isinstance(item.get("status"), str) and item.get("status", "") in
         ("raw", "analyzed", "published")),
        ("时间戳", isinstance(item.get("collected_at"), str)
         and len(item.get("collected_at", "")) > 0),
    ]

    scored = sum(4 for _, ok in checks if ok)
    passed_names = [name for name, ok in checks if ok]
    failed_names = [name for name, ok in checks if not ok]
    details = f"通过: {', '.join(passed_names) or '无'}"
    if failed_names:
        details += f" | 缺失: {', '.join(failed_names)}"

    return DimensionScore(name="格式规范", max=20, score=scored, details=details)


def _score_tags(item: dict) -> DimensionScore:
    """标签精度 (15 分)。

    - 1-3 个标签: 满分基础 10
    - 4-5 个标签: 基础 8
    - > 5 或 0 个: 基础 4
    - 标准标签比例: 最多加 5 分
    """
    tags = item.get("tags", [])
    if not isinstance(tags, list):
        tags = []

    count = len(tags)

    if 1 <= count <= 3:
        base = 10
    elif 4 <= count <= 5:
        base = 8
    elif count > 5:
        base = 4
    else:
        base = 0

    # 标准标签奖励
    if count > 0:
        std_count = sum(1 for t in tags if isinstance(t, str) and t.lower() in STANDARD_TAGS)
        std_ratio = std_count / count
        bonus = round(std_ratio * 5)
    else:
        std_count = 0
        bonus = 0

    score = min(base + bonus, 15)
    details = f"标签数={count}, 标准标签={std_count}, 基础={base}, 奖励={bonus}"
    return DimensionScore(name="标签精度", max=15, score=score, details=details)


def _score_buzzwords(item: dict) -> DimensionScore:
    """空洞词检测 (15 分)。

    检查 title、summary、analysis.summary_cn 中的空洞词。
    每 1 个空洞词扣 3 分，扣完为止。
    """
    texts: list[str] = []

    title = item.get("title", "")
    if isinstance(title, str):
        texts.append(title)

    summary = item.get("summary", "")
    if isinstance(summary, str):
        texts.append(summary)

    analysis = item.get("analysis", {})
    if isinstance(analysis, dict):
        cn = analysis.get("summary_cn", "")
        if isinstance(cn, str):
            texts.append(cn)
        highlights = analysis.get("highlights", [])
        if isinstance(highlights, list):
            for h in highlights:
                if isinstance(h, str):
                    texts.append(h)

    combined = " ".join(texts).lower()

    found: list[str] = []
    for bw in ALL_BUZZWORDS:
        if bw.lower() in combined:
            found.append(bw)

    deduction = min(len(found) * 3, 15)
    score = 15 - deduction

    if found:
        details = f"发现 {len(found)} 个空洞词: {', '.join(found[:5])}"
        if len(found) > 5:
            details += f" 等"
    else:
        details = "未发现空洞词"

    return DimensionScore(name="空洞词检测", max=15, score=score, details=details)


SCORERS = [
    _score_summary,
    _score_depth,
    _score_format,
    _score_tags,
    _score_buzzwords,
]

# ---------------------------------------------------------------------------
# 可视化输出
# ---------------------------------------------------------------------------

GRADE_COLORS = {"A": "\033[92m", "B": "\033[93m", "C": "\033[91m"}
RESET = "\033[0m"


def _bar(score: int, max_score: int, width: int = 20) -> str:
    """生成可视化进度条。"""
    filled = round(score / max_score * width) if max_score > 0 else 0
    empty = width - filled
    return "\u2588" * filled + "\u2591" * empty


def _print_report(report: QualityReport) -> None:
    """打印单条质量报告。"""
    color = GRADE_COLORS.get(report.grade, RESET)
    print(f"\n{'─' * 60}")
    print(f"  {report.title}")
    print(f"  文件: {report.file_path}")
    print(f"{'─' * 60}")

    for dim in report.dimensions:
        bar_str = _bar(dim.score, dim.max)
        print(f"  {dim.name:　<8} [{bar_str}] {dim.score:>2}/{dim.max:<2}  {dim.details}")

    print(f"{'─' * 60}")
    total_bar = _bar(report.total, 100)
    print(f"  总分      [{total_bar}] {report.total:>2}/100   等级: {color}{report.grade}{RESET}")
    print()


# ---------------------------------------------------------------------------
# 文件级评分
# ---------------------------------------------------------------------------


def score_file(filepath: Path) -> list[QualityReport]:
    """对单个 JSON 文件中的所有条目评分。"""
    reports: list[QualityReport] = []

    try:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"错误: {filepath} JSON 解析失败: {exc}", file=sys.stderr)
        return reports

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [data]
    else:
        print(f"错误: {filepath} 根元素应为对象或数组", file=sys.stderr)
        return reports

    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title", "(无标题)")
        dimensions = [scorer(item) for scorer in SCORERS]
        report = QualityReport(
            title=title,
            file_path=str(filepath),
            dimensions=dimensions,
        )
        reports.append(report)

    return reports


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def _collect_files(paths: list[str]) -> list[Path]:
    """从命令行参数收集实际文件路径。"""
    files: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            files.extend(sorted(path.glob("*.json")))
        elif path.is_file():
            files.append(path)
        else:
            parent = path.parent
            if parent.is_dir():
                files.extend(sorted(parent.glob(path.name)))
            else:
                print(f"警告: 路径不存在: {p}", file=sys.stderr)
    return files


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python hooks/check_quality.py <file.json> [file2.json ...]", file=sys.stderr)
        sys.exit(1)

    files = _collect_files(sys.argv[1:])
    if not files:
        print("错误: 未找到匹配的 JSON 文件", file=sys.stderr)
        sys.exit(1)

    all_reports: list[QualityReport] = []
    for filepath in files:
        all_reports.extend(score_file(filepath))

    if not all_reports:
        print("未找到可评分的条目", file=sys.stderr)
        sys.exit(1)

    for report in all_reports:
        _print_report(report)

    # 汇总
    total = len(all_reports)
    grade_a = sum(1 for r in all_reports if r.grade == "A")
    grade_b = sum(1 for r in all_reports if r.grade == "B")
    grade_c = sum(1 for r in all_reports if r.grade == "C")
    avg_score = round(sum(r.total for r in all_reports) / total)

    print(f"{'═' * 60}")
    print(f"  汇总: {total} 条 | A={grade_a} B={grade_b} C={grade_c} | 平均分={avg_score}")
    print(f"{'═' * 60}")

    sys.exit(1 if grade_c > 0 else 0)


if __name__ == "__main__":
    main()
