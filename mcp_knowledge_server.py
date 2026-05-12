"""MCP Knowledge Server — 让 AI 工具搜索本地知识库。

通过 JSON-RPC 2.0 over stdio 协议提供三个工具：
- search_articles: 按关键词搜索文章标题和摘要
- get_article: 按 ID 获取文章完整内容
- knowledge_stats: 返回统计信息

无第三方依赖，仅使用 Python 标准库。
"""

import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# ── 配置 ──────────────────────────────────────────────

ARTICLES_DIR = Path(__file__).parent / "knowledge" / "articles"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mcp_knowledge_server")

# ── JSON-RPC 2.0 辅助函数 ────────────────────────────


def _rpc_result(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id: Any, code: int, message: str, data: Any = None) -> dict:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": error}


# ── 数据加载 ──────────────────────────────────────────


def _load_all_articles() -> list[dict]:
    """加载 articles 目录下所有 JSON 文件，跳过损坏文件。"""
    articles: list[dict] = []
    if not ARTICLES_DIR.is_dir():
        logger.warning("文章目录不存在: %s", ARTICLES_DIR)
        return articles

    for fp in sorted(ARTICLES_DIR.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(data, list):
                articles.extend(data)
            elif isinstance(data, dict):
                articles.append(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("跳过损坏文件 %s: %s", fp.name, exc)
    return articles


# ── 工具实现 ──────────────────────────────────────────


def _search_articles(arguments: dict) -> list[dict]:
    """按关键词搜索文章标题和摘要，返回匹配结果。"""
    keyword = arguments.get("keyword", "").strip()
    limit = arguments.get("limit", 5)
    if not keyword:
        return []

    articles = _load_all_articles()
    keyword_lower = keyword.lower()
    results: list[dict] = []

    for art in articles:
        title = (art.get("title") or "").lower()
        summary = (art.get("summary") or "").lower()
        tags = " ".join(art.get("tags") or []).lower()
        if keyword_lower in title or keyword_lower in summary or keyword_lower in tags:
            results.append({
                "id": art.get("id"),
                "title": art.get("title"),
                "source": art.get("source"),
                "summary": art.get("summary"),
                "tags": art.get("tags", []),
                "score": art.get("score"),
                "source_url": art.get("source_url"),
                "collected_at": art.get("collected_at"),
            })

    results.sort(key=lambda a: a.get("score") or 0, reverse=True)
    return results[:limit]


def _get_article(arguments: dict) -> dict:
    """按 ID 获取单篇文章完整内容。"""
    article_id = arguments.get("article_id", "").strip()
    if not article_id:
        return {"error": "article_id 参数不能为空"}

    for art in _load_all_articles():
        if art.get("id") == article_id:
            return art
    return {"error": f"未找到 ID 为 '{article_id}' 的文章"}


def _knowledge_stats(_arguments: dict) -> dict:
    """返回知识库统计信息。"""
    articles = _load_all_articles()
    source_counter = Counter(art.get("source", "unknown") for art in articles)
    tag_counter = Counter(tag for art in articles for tag in (art.get("tags") or []))

    return {
        "total_articles": len(articles),
        "sources": dict(source_counter.most_common()),
        "top_tags": dict(tag_counter.most_common(20)),
        "statuses": dict(Counter(art.get("status", "unknown") for art in articles)),
    }


# ── MCP 工具定义 ──────────────────────────────────────

TOOLS = [
    {
        "name": "search_articles",
        "description": "按关键词搜索知识库文章，匹配标题、摘要和标签。返回按相关度排序的结果列表。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词，匹配标题、摘要或标签",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量上限，默认 5",
                    "default": 5,
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_article",
        "description": "按文章 ID 获取完整内容，包括所有字段（标题、摘要、标签、评分、元数据等）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "article_id": {
                    "type": "string",
                    "description": "文章的唯一 ID",
                },
            },
            "required": ["article_id"],
        },
    },
    {
        "name": "knowledge_stats",
        "description": "返回知识库统计信息：文章总数、来源分布、热门标签、状态分布。",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]

TOOL_HANDLERS = {
    "search_articles": _search_articles,
    "get_article": _get_article,
    "knowledge_stats": _knowledge_stats,
}

# ── MCP 协议处理 ──────────────────────────────────────

SERVER_INFO = {
    "name": "knowledge-server",
    "version": "0.1.0",
}

CAPABILITIES = {
    "tools": {},
}


def _handle_initialize(params: dict) -> dict:
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": CAPABILITIES,
        "serverInfo": SERVER_INFO,
    }


def _handle_tools_list() -> list[dict]:
    return TOOLS


def _handle_tools_call(params: dict) -> dict:
    tool_name = params.get("name", "")
    arguments = params.get("arguments") or {}

    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"未知工具: {tool_name}"}],
        }

    try:
        result = handler(arguments)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, ensure_ascii=False, indent=2),
                }
            ],
        }
    except Exception as exc:
        logger.exception("工具 %s 执行失败", tool_name)
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"工具执行失败: {exc}"}],
        }


METHOD_HANDLERS = {
    "initialize": lambda params: _handle_initialize(params),
    "notifications/initialized": lambda params: None,
    "tools/list": lambda params: _handle_tools_list(),
    "tools/call": lambda params: _handle_tools_call(params),
}


def _process_request(request: dict) -> dict | None:
    """处理单个 JSON-RPC 请求，返回响应 dict。对通知类消息返回 None。"""
    method = request.get("method", "")
    req_id = request.get("id")

    # 通知类消息（无 id）不需要响应
    if req_id is None and not method.startswith("tools/"):
        return None

    handler = METHOD_HANDLERS.get(method)
    if handler is None:
        return _rpc_error(req_id, -32601, f"方法未找到: {method}")

    try:
        result = handler(request.get("params") or {})
        if result is None:
            return None  # 通知，无响应
        return _rpc_result(req_id, result)
    except Exception as exc:
        logger.exception("处理方法 %s 时出错", method)
        return _rpc_error(req_id, -32603, f"内部错误: {exc}")


# ── 主循环 ────────────────────────────────────────────


def main() -> None:
    """从 stdin 读取 JSON-RPC 消息，处理后写入 stdout。"""
    # Windows 下确保 stdin/stdout 使用 UTF-8 且无缓冲
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

    logger.info("MCP Knowledge Server 启动，文章目录: %s", ARTICLES_DIR)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            response = _rpc_error(None, -32700, "无效的 JSON")
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            continue

        response = _process_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
