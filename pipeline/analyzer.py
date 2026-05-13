"""Analyzer — 调用 LLM 分析采集数据，输出结构化 JSON 到 knowledge/articles/。

读取 knowledge/raw/ 中最新的原始数据，逐条调用智谱 API 生成
中文摘要、亮点、评分、标签，输出符合 analyzed schema 的 JSON。

用法:
    python pipeline/analyzer.py --verbose
    python pipeline/analyzer.py --date 2026-05-13 --limit 10 --verbose
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI

# ── 配置 ──────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "knowledge" / "raw"
ARTICLES_DIR = PROJECT_ROOT / "knowledge" / "articles"

# 智谱 Coding 端点
BIGMODEL_BASE_URL = os.environ.get(
    "BIGMODEL_BASE_URL", "https://open.bigmodel.cn/api/coding/paas/v4"
)
BIGMODEL_API_KEY = os.environ.get("BIGMODEL_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "glm-4.7")

# 备用：通用端点
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "bigmodel")

# 标准标签池
STANDARD_TAGS: list[str] = [
    "llm", "agent", "rag", "multimodal", "diffusion", "mcp",
    "fine_tuning", "embedding", "browser_automation", "knowledge_graph",
    "code_generation", "security", "open_source", "programming_language",
    "simulation", "prompt_engineering", "vector_database", "quantization",
    "speech", "vision", "nlp", "transformer", "reinforcement_learning",
    "benchmark", "tutorial", "mlops",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("analyzer")

# ── LLM 客户端 ──────────────────────────────────────


def _create_client() -> OpenAI:
    """根据 LLM_PROVIDER 创建对应的 OpenAI 兼容客户端。"""
    if LLM_PROVIDER == "bigmodel" and BIGMODEL_API_KEY:
        logger.debug("使用智谱 GLM (%s)", BIGMODEL_BASE_URL)
        return OpenAI(api_key=BIGMODEL_API_KEY, base_url=BIGMODEL_BASE_URL)

    if LLM_PROVIDER == "deepseek" and DEEPSEEK_API_KEY:
        logger.debug("使用 DeepSeek")
        return OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com/v1",
        )

    if LLM_PROVIDER == "qwen" and QWEN_API_KEY:
        logger.debug("使用通义千问")
        return OpenAI(
            api_key=QWEN_API_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

    if OPENAI_API_KEY:
        logger.debug("使用 OpenAI")
        return OpenAI(api_key=OPENAI_API_KEY)

    raise ValueError(
        f"无可用的 LLM API Key。LLM_PROVIDER={LLM_PROVIDER}, "
        "请设置 BIGMODEL_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY / QWEN_API_KEY"
    )


# ── Prompt 构建 ──────────────────────────────────────


ANALYSIS_SYSTEM_PROMPT = (
    "你是一位编程助手，负责为 AI/LLM/Agent 领域的技术项目生成结构化的 JSON 数据对象。\n"
    "请用中文编写以下 JSON 数据结构，仅输出合法 JSON，无其他文字。\n\n"
    "JSON Schema:\n"
    "{\n"
    '  "summary_cn": "str — 中文摘要150-200字，结构：是什么→核心方案→解决什么问题",\n'
    '  "highlights": ["str — 亮点1(15-30字)", "str — 亮点2(15-30字)"],\n'
    '  "score": "int — 1-10评分",\n'
    '  "score_reason": "str — 评分理由50字以内",\n'
    '  "suggested_tags": ["str — 从标签池选取2-5个"],\n'
    '  "target_audience": "str — 目标受众描述"\n'
    "}\n\n"
    "评分规则:\n"
    "9-10: 改变格局(重大创新/新范式/头部实验室里程碑)\n"
    "7-8: 直接有帮助(可用于生产的工具/框架)\n"
    "5-6: 值得了解(有创新性,特定场景有用)\n"
    "1-4: 可略过(教程搬运/重复造轮子/纯营销)\n"
    "大部分项目5-8分,9-10分应很稀缺。\n\n"
    "标签池: " + ", ".join(STANDARD_TAGS) + "\n\n"
    "约束: 仅输出合法JSON,禁止markdown代码块,禁止编造夸大。"
)


def _build_user_prompt(item: dict) -> str:
    """为单个条目构建分析 prompt。"""
    parts = [
        f"标题: {item.get('name') or item.get('title', 'Unknown')}",
        f"链接: {item.get('url') or item.get('source_url', '')}",
    ]

    summary = item.get("summary") or item.get("description") or ""
    if summary:
        parts.append(f"描述: {summary}")

    if item.get("stars"):
        parts.append(f"GitHub Stars: {item['stars']}")
    if item.get("language"):
        parts.append(f"语言: {item['language']}")
    if item.get("topics"):
        parts.append(f"Topics: {', '.join(item['topics'])}")
    if item.get("score"):
        parts.append(f"HN 得分: {item['score']}")
    if item.get("author"):
        parts.append(f"作者: {item['author']}")

    return "\n".join(parts)


# ── LLM 调用 ────────────────────────────────────────


def _extract_json_object(text: str) -> str | None:
    """从文本中提取第一个完整的 JSON 对象（支持嵌套）。"""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _parse_llm_response(text: str) -> dict | None:
    """从 LLM 回复中提取 JSON。"""
    # 去除 markdown 代码块
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    # 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 提取第一个完整 JSON 对象（支持嵌套）
    json_str = _extract_json_object(text)
    if json_str:
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    logger.warning("无法解析 LLM 回复为 JSON: %s...", text[:200])
    return None


def analyze_item(client: OpenAI, item: dict) -> dict | None:
    """调用 LLM 分析单个条目，返回 analysis dict 或 None。"""
    user_prompt = _build_user_prompt(item)

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        text = response.choices[0].message.content or ""
        logger.debug("LLM 原始回复 (%s): %s", item.get("name") or item.get("title"), text[:300])
        return _parse_llm_response(text)
    except Exception as exc:
        logger.warning("LLM 分析失败 (%s): %s", item.get("name") or item.get("title"), exc)
        return None


# ── 数据加载 ──────────────────────────────────────────


def load_raw_items(date_str: str | None = None) -> list[dict]:
    """从 knowledge/raw/ 加载原始条目。"""
    items: list[dict] = []

    if date_str:
        # 加载指定日期
        patterns = [f"*{date_str}*.json"]
    else:
        # 加载今天
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        patterns = [f"*{today}*.json"]

    for pattern in patterns:
        for fp in sorted(RAW_DIR.glob(pattern)):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                raw_items = data.get("items", []) if isinstance(data, dict) else data
                for item in raw_items:
                    item["_source_file"] = fp.name
                items.extend(raw_items)
            except (json.JSONDecodeError, OSError) as exc:
                logger.error("跳过损坏文件 %s: %s", fp.name, exc)

    logger.info("加载原始数据: %d 条", len(items))
    return items


def _load_analyzed_urls() -> set[str]:
    """加载已有 articles 中的 URL，用于跳过已分析的。"""
    urls: set[str] = set()
    if not ARTICLES_DIR.is_dir():
        return urls

    for fp in ARTICLES_DIR.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    url = item.get("source_url")
                    if url:
                        urls.add(url)
            elif isinstance(data, dict):
                url = data.get("source_url")
                if url:
                    urls.add(url)
        except (json.JSONDecodeError, OSError):
            continue

    logger.debug("已有 articles URL: %d 个", len(urls))
    return urls


# ── 分析主流程 ────────────────────────────────────────


def run_analysis(date_str: str | None = None, limit: int = 0) -> list[dict]:
    """加载原始数据，逐条调用 LLM 分析，返回结构化结果列表。"""
    raw_items = load_raw_items(date_str)
    if not raw_items:
        logger.info("无原始数据可分析")
        return []

    # 跳过已分析的
    analyzed_urls = _load_analyzed_urls()
    items_to_analyze = []
    for item in raw_items:
        url = item.get("url") or item.get("source_url") or ""
        if url in analyzed_urls:
            logger.debug("跳过已分析: %s", item.get("name") or item.get("title"))
            continue
        items_to_analyze.append(item)

    if not items_to_analyze:
        logger.info("所有条目已分析过，无新数据")
        return []

    if limit > 0:
        items_to_analyze = items_to_analyze[:limit]

    logger.info("待分析: %d 条", len(items_to_analyze))

    client = _create_client()
    results: list[dict] = []

    for i, item in enumerate(items_to_analyze, 1):
        name = item.get("name") or item.get("title", "Unknown")
        logger.info("[%d/%d] 分析: %s", i, len(items_to_analyze), name)

        analysis = analyze_item(client, item)
        now = datetime.now(timezone.utc).isoformat()

        article = {
            "id": str(uuid.uuid4()),
            "title": name,
            "source_url": item.get("url") or item.get("source_url", ""),
            "source": _normalize_source(item),
            "collected_at": now,
            "analyzed_at": now,
            "summary": (analysis or {}).get("summary_cn", item.get("summary", "")),
            "highlights": (analysis or {}).get("highlights", []),
            "score": (analysis or {}).get("score", 5),
            "score_reason": (analysis or {}).get("score_reason", ""),
            "tags": (analysis or {}).get("suggested_tags", []),
            "status": "analyzed" if analysis else "raw",
            "published_at": None,
            "metadata": {
                "stars": item.get("stars"),
                "score": item.get("score"),
                "author": item.get("author"),
                "language": item.get("language"),
            },
        }

        if analysis:
            article["target_audience"] = analysis.get("target_audience", "")

        results.append(article)

        # 避免触发速率限制
        if i < len(items_to_analyze):
            time.sleep(1)

    logger.info("分析完成: %d 条成功", len(results))
    return results


def _normalize_source(item: dict) -> str:
    """将来源标准化为 schema 枚举值。"""
    source = (item.get("source") or "").lower()
    if "github" in source:
        return "github_trending"
    if "hack" in source or "hn" in source:
        return "hacker_news"
    return source or "unknown"


# ── 保存 ──────────────────────────────────────────────


def save_articles(articles: list[dict], date_str: str | None = None) -> Path | None:
    """将分析结果保存到 knowledge/articles/。"""
    if not articles:
        return None

    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    today = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filepath = ARTICLES_DIR / f"analyzed-{today}.json"

    # 合并已有
    existing: list[dict] = []
    if filepath.exists():
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            existing = data if isinstance(data, list) else [data]
        except (json.JSONDecodeError, OSError):
            pass

    # 按 URL 去重合并
    seen_urls: set[str] = set()
    merged: list[dict] = []
    for art in existing + articles:
        url = art.get("source_url", "")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        merged.append(art)

    filepath.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("保存分析结果: %d 条 → %s", len(merged), filepath)
    return filepath


# ── CLI ──────────────────────────────────────────────


def main() -> None:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(description="AI 知识库分析器")
    parser.add_argument("--date", help="分析指定日期的数据 (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=0, help="最大分析条数，0=全部")
    parser.add_argument("--verbose", action="store_true", help="启用详细日志")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("分析器启动: date=%s, limit=%d", args.date or "today", args.limit)

    articles = run_analysis(date_str=args.date, limit=args.limit)
    if articles:
        save_articles(articles, date_str=args.date)
        logger.info("分析器完成: 新增 %d 条", len(articles))
    else:
        logger.info("分析器完成: 无新数据")


if __name__ == "__main__":
    main()
