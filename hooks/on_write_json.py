#!/usr/bin/env python3
"""PostToolUse hook: 写入 knowledge/articles/*.json 后自动校验。

从 stdin 读取 Claude Code 的 hook JSON，判断文件路径是否匹配，
匹配则运行 validate_json.py 并将结果作为 systemMessage 返回。
"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VALIDATE_SCRIPT = PROJECT_ROOT / "hooks" / "validate_json.py"


def main() -> None:
    # 读取 hook stdin
    hook_input = json.load(sys.stdin)
    file_path = (
        hook_input.get("tool_response", {}).get("filePath")
        or hook_input.get("tool_input", {}).get("file_path", "")
    )

    # 只校验 knowledge/articles/ 下的 JSON 文件
    if "knowledge/articles" not in file_path or not file_path.endswith(".json"):
        return

    # 运行校验脚本
    result = subprocess.run(
        [sys.executable, str(VALIDATE_SCRIPT), file_path],
        capture_output=True,
        encoding="utf-8",
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
    )

    if result.returncode != 0:
        output = result.stdout.strip()
        if not output:
            output = "JSON 校验失败（无详细输出）"
        # 返回 systemMessage 让 Claude 看到错误
        json.dump(
            {"systemMessage": f"JSON 校验未通过:\n{output}", "continue": True},
            sys.stdout,
            ensure_ascii=False,
        )
        sys.stdout.write("\n")
    else:
        # 校验通过，静默（不输出任何内容）
        pass


if __name__ == "__main__":
    main()
