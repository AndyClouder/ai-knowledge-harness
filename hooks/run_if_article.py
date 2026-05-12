#!/usr/bin/env python3
"""轻量 wrapper：只在写入 knowledge/articles/*.json 时才启动下游 hook 脚本。

用法（由 Claude Code hooks 自动调用， stdin 传入 JSON）:
    python hooks/run_if_article.py <actual_hook.py>

stdin 格式（Claude Code PostToolUse hook）:
    {"tool_input": {"file_path": "..."}, ...}

匹配规则:
    file_path 包含 "knowledge/articles/" 且以 ".json" 结尾时，
    将 stdin 原样透传给下游脚本；否则静默退出。
"""

import subprocess
import sys


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(0)

    # 读取 stdin（Claude Code 传入的 hook payload）
    if sys.stdin.isatty():
        sys.exit(0)

    try:
        raw = sys.stdin.buffer.read()
    except Exception:
        sys.exit(0)

    if not raw.strip():
        sys.exit(0)

    # 用最简单的方式提取 file_path，避免 import json
    text = raw.decode("utf-8", errors="replace")
    # 快速查找 "file_path":"..." 或 "file_path": "..."
    fp_start = text.find('"file_path"')
    if fp_start == -1:
        sys.exit(0)

    # 找到值的起止引号
    val_start = text.find('"', fp_start + len('"file_path"'))
    if val_start == -1:
        sys.exit(0)
    val_end = text.find('"', val_start + 1)
    if val_end == -1:
        sys.exit(0)

    file_path = text[val_start + 1 : val_end]
    norm = file_path.replace("\\", "/")

    if "knowledge/articles/" not in norm or not norm.endswith(".json"):
        sys.exit(0)

    # 匹配成功：透传 stdin 给下游脚本
    target = sys.argv[1]
    result = subprocess.run(
        [sys.executable, target],
        input=raw,
        capture_output=True,
        timeout=30,
    )
    if result.stdout:
        sys.stdout.buffer.write(result.stdout)
    if result.stderr:
        sys.stderr.buffer.write(result.stderr)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
