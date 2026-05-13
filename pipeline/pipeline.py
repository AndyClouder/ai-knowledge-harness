"""Pipeline — AI 知识库采集流水线。

从 GitHub Trending 和 RSS（Hacker News 等）采集 AI/LLM/Agent 领域技术动态，
输出原始 JSON 到 knowledge/raw/ 目录。

用法:
    python pipeline/pipeline.py --sources github,rss --limit 20 --verbose
"""

import argparse
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import feedparser
import requests

# ── 配置 ──────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "knowledge" / "raw"

# AI 关键词（小写匹配）
AI_KEYWORDS: list[str] = [
    "ai", "llm", "agent", "gpt", "transformer", "diffusion", "embedding",
    "rag", "fine-tuning", "multimodal", "speech", "vision", "nlp",
    "machine-learning", "deep-learning", "openai", "anthropic",
    "langchain", "vector-database", "mcp", "copilot", "claude",
]

# 排除关键词
EXCLUDE_PATTERNS: list[str] = ["awesome-", "awesome_list"]

# HN RSS 查询关键词
HN_RSS_QUERIES = ["AI", "LLM", "agent", "GPT", "language model"]

# RSS 源配置
RSS_FEEDS: list[dict[str, str]] = [
    {
        "name": "hacker_news",
        "url": "https://hnrss.org/newest?q={query}&count=50",
    },
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("pipeline")

# ── GitHub 采集 ──────────────────────────────────────


def _github_api_get(url: str, params: dict, session: requests.Session) -> dict | None:
    """发送 GitHub API 请求，返回 JSON 或 None。"""
    token = os.environ.get("GH_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = session.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.warning("GitHub API 请求失败: %s", exc)
        return None


def _is_ai_related(repo: dict) -> bool:
    """判断仓库是否与 AI 相关。"""
    text_fields = [
        (repo.get("topics") or []),
        (repo.get("description") or "").lower().split(),
        repo.get("name", "").lower().split("/"),
    ]
    all_text = " ".join(" ".join(f) if isinstance(f, list) else f for f in text_fields).lower()
    return any(kw in all_text for kw in AI_KEYWORDS)


def _is_excluded(repo: dict) -> bool:
    """判断仓库是否应排除（如 awesome-list）。"""
    name = repo.get("full_name", "").lower()
    topics = [t.lower() for t in (repo.get("topics") or [])]
    for pattern in EXCLUDE_PATTERNS:
        if name.split("/")[-1].startswith(pattern.replace("-", "")):
            return True
        if pattern in topics:
            return True
    return False


def _repo_to_item(repo: dict) -> dict:
    """将 GitHub API 仓库对象转为统一 item 格式。"""
    return {
        "name": repo.get("full_name", ""),
        "url": repo.get("html_url", ""),
        "summary": (repo.get("description") or "")[:200],
        "stars": repo.get("stargazers_count"),
        "language": repo.get("language"),
        "topics": repo.get("topics", []),
    }


def collect_github(limit: int = 20) -> list[dict]:
    """从 GitHub Search API 采集 AI 相关热门仓库。"""
    logger.info("开始采集 GitHub Trending，limit=%d", limit)
    today = datetime.now(timezone.utc)
    time_windows = [1, 3, 7]
    seen_ids: set[int] = set()
    all_repos: list[dict] = []

    with requests.Session() as session:
        for days in time_windows:
            since = (today - timedelta(days=days)).strftime("%Y-%m-%d")
            params = {
                "q": f"created:>={since} stars:>50",
                "sort": "stars",
                "order": "desc",
                "per_page": 100,
            }
            logger.debug("请求 GitHub: created:>=%s stars:>50", since)
            data = _github_api_get("https://api.github.com/search/repositories", params, session)
            if not data:
                continue

            items = data.get("items", [])
            logger.debug("窗口 %d 天: 返回 %d 条", days, len(items))

            for repo in items:
                repo_id = repo.get("id")
                if repo_id in seen_ids:
                    continue
                if _is_excluded(repo):
                    continue
                if not _is_ai_related(repo):
                    continue
                seen_ids.add(repo_id)
                all_repos.append(repo)

    logger.info("GitHub 采集: 过滤前 %d, 过滤后 %d", len(seen_ids), len(all_repos))

    # 按 stars 降序
    all_repos.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)
    result = [_repo_to_item(r) for r in all_repos[:limit]]
    logger.info("GitHub 最终输出: %d 条", len(result))
    return result


# ── RSS 采集 ──────────────────────────────────────────


def _is_ai_rss(entry: dict) -> bool:
    """判断 RSS 条目是否与 AI 相关。"""
    title = (entry.get("title") or "").lower()
    summary = (entry.get("summary") or "").lower()
    text = f"{title} {summary}"
    return any(kw.lower() in text for kw in AI_KEYWORDS)


def _fetch_rss_feed(url: str) -> list[dict]:
    """获取并解析单个 RSS 源。"""
    logger.debug("获取 RSS: %s", url)
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("RSS 获取失败 %s: %s", url, exc)
        return []

    feed = feedparser.parse(resp.text)
    if feed.bozo and not feed.entries:
        logger.warning("RSS 解析失败 %s: %s", url, feed.bozo_exception)
        return []
    return feed.entries


def _entry_to_item(entry: dict, source_name: str) -> dict:
    """将 RSS entry 转为统一 item 格式。"""
    title = entry.get("title", "Untitled")
    link = entry.get("link", "")
    summary = entry.get("summary", "")
    # 清理 HTML 标签
    if summary:
        import re
        summary = re.sub(r"<[^>]+>", "", summary)[:200]

    return {
        "name": title,
        "url": link,
        "summary": summary,
        "source": source_name,
        "score": None,
        "author": entry.get("author", None),
        "published": entry.get("published", None),
    }


def collect_rss(limit: int = 20) -> list[dict]:
    """从 RSS 源采集 AI 相关内容。"""
    logger.info("开始采集 RSS，limit=%d", limit)
    all_items: list[dict] = []
    seen_urls: set[str] = set()

    for feed_config in RSS_FEEDS:
        for query in HN_RSS_QUERIES:
            url = feed_config["url"].format(query=query)
            entries = _fetch_rss_feed(url)

            filtered = 0
            for entry in entries:
                if not _is_ai_rss(entry):
                    continue
                link = entry.get("link", "")
                if link in seen_urls:
                    continue
                seen_urls.add(link)
                all_items.append(_entry_to_item(entry, feed_config["name"]))
                filtered += 1

            logger.debug("RSS %s query=%s: 过滤后 %d 条", feed_config["name"], query, filtered)

    logger.info("RSS 采集: 共 %d 条", len(all_items))
    return all_items[:limit]


# ── 去重 ──────────────────────────────────────────────


def _load_history_urls(days: int = 7) -> set[str]:
    """加载最近 N 天历史文件中的 URL，用于去重。"""
    urls: set[str] = set()
    if not RAW_DIR.is_dir():
        return urls

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for fp in RAW_DIR.glob("*.json"):
        try:
            mtime = datetime.fromtimestamp(fp.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                continue
            data = json.loads(fp.read_text(encoding="utf-8"))
            items = data.get("items", []) if isinstance(data, dict) else data
            for item in items:
                url = item.get("url") or item.get("source_url")
                if url:
                    urls.add(url)
        except (json.JSONDecodeError, OSError):
            continue

    logger.debug("加载历史 URL: %d 个（最近 %d 天）", len(urls), days)
    return urls


def dedup(items: list[dict], history_days: int = 7) -> list[dict]:
    """跨源去重 + 历史去重。"""
    history_urls = _load_history_urls(history_days)
    seen: set[str] = set()
    result: list[dict] = []

    for item in items:
        url = item.get("url") or item.get("source_url") or ""
        if url in seen or url in history_urls:
            continue
        seen.add(url)
        result.append(item)

    removed = len(items) - len(result)
    if removed:
        logger.info("去重: 移除 %d 条重复，保留 %d 条", removed, len(result))
    return result


# ── 保存 ──────────────────────────────────────────────


def save_raw(source: str, items: list[dict]) -> Path | None:
    """将采集结果保存到 knowledge/raw/，幂等（合并去重后覆盖）。"""
    if not items:
        logger.info("无数据可保存 (%s)", source)
        return None

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{source}-{today}.json"
    filepath = RAW_DIR / filename

    # 幂等：合并已有数据
    existing_items: list[dict] = []
    if filepath.exists():
        try:
            existing = json.loads(filepath.read_text(encoding="utf-8"))
            existing_items = existing.get("items", []) if isinstance(existing, dict) else existing
        except (json.JSONDecodeError, OSError):
            pass

    # 合并去重
    all_items = existing_items + items
    seen_urls: set[str] = set()
    merged: list[dict] = []
    for item in all_items:
        url = item.get("url") or item.get("source_url") or ""
        if url in seen_urls:
            continue
        seen_urls.add(url)
        merged.append(item)

    output = {
        "source": source,
        "skill": source,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "items": merged,
    }

    filepath.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("保存 %s: %d 条 → %s", source, len(merged), filepath)
    return filepath


# ── 主流程 ────────────────────────────────────────────


def main() -> None:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(description="AI 知识库采集流水线")
    parser.add_argument(
        "--sources",
        default="github,rss",
        help="采集源，逗号分隔 (github, rss)，默认: github,rss",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="每个源最大条目数，默认: 20",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="启用详细日志 (DEBUG)",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    sources = [s.strip() for s in args.sources.split(",")]
    logger.info("采集流水线启动: sources=%s, limit=%d", sources, args.limit)

    total_collected = 0

    for source in sources:
        items: list[dict] = []

        if source == "github":
            items = collect_github(limit=args.limit)
        elif source == "rss":
            items = collect_rss(limit=args.limit)
        else:
            logger.warning("未知采集源: %s，跳过", source)
            continue

        # 去重
        items = dedup(items)
        total_collected += len(items)

        # 保存
        source_name = "github-trending" if source == "github" else source
        save_raw(source_name, items)

    logger.info("采集流水线完成: 共采集 %d 条新数据", total_collected)

    # ── 分析步骤 ──
    if total_collected > 0:
        logger.info("启动 LLM 分析步骤")
        from pipeline.analyzer import run_analysis, save_articles

        articles = run_analysis(limit=args.limit)
        if articles:
            save_articles(articles)
            logger.info("LLM 分析完成: 新增 %d 条文章", len(articles))
        else:
            logger.info("LLM 分析: 无新数据需要分析")


if __name__ == "__main__":
    main()
