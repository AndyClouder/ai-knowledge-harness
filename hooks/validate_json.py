#!/usr/bin/env python3
"""校验知识条目 JSON 文件。

以 specs/schemas/ 下的 JSON Schema 为数据契约，同时执行轻量的
Python 前置检查（摘要长度、标签数量等 Schema 难以表达的规则）。

用法:
    python hooks/validate_json.py <file.json> [file2.json ...]
    python hooks/validate_json.py knowledge/articles/*.json

退出码:
    0 — 全部通过
    1 — 存在校验错误
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Schema 加载
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = PROJECT_ROOT / "specs" / "schemas"

# 按文件名前缀自动匹配 schema
_SCHEMA_PREFIX_MAP = {
    "raw": "raw.json",
    "analyzed": "analyzed.json",
}


def _load_schema(name: str) -> dict:
    """从 specs/schemas/ 加载 JSON Schema。"""
    path = SCHEMAS_DIR / name
    if not path.exists():
        print(f"错误: Schema 文件不存在: {path}", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def _detect_schema(filepath: Path) -> dict | None:
    """根据文件名前缀自动匹配对应的 JSON Schema，匹配失败返回 None。"""
    stem = filepath.stem.lower()
    for prefix, schema_file in _SCHEMA_PREFIX_MAP.items():
        if prefix in stem:
            return _load_schema(schema_file)
    return None


def _jsonschema_validate(instance: dict, schema: dict) -> list[str]:
    """纯手写 JSON Schema 校验器，零第三方依赖。

    覆盖 draft-07 常用关键字: type, required, properties, enum,
    format(uri/uuid/date-time), minimum, maximum, minLength, maxLength,
    minItems, maxItems, items, additionalProperties(false), null 类型。
    """
    errors: list[str] = []

    # type 检查
    expected = schema.get("type")
    if expected:
        type_ok = _check_type(instance, expected)
        if not type_ok:
            errors.append(f"类型错误: 期望 {expected}, 实际 {type(instance).__name__}")
            return errors  # 类型都不对，后续无意义

    # enum 检查
    enum_values = schema.get("enum")
    if enum_values is not None and instance not in enum_values:
        errors.append(f"值无效: '{instance}', 应为 {enum_values}")

    # format 检查（仅对字符串生效）
    fmt = schema.get("format")
    if fmt and isinstance(instance, str):
        if fmt == "uri" and not re.match(r"^https?://\S+$", instance):
            errors.append(f"URI 格式错误: '{instance}'")
        elif fmt == "uuid" and not re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            instance,
        ):
            errors.append(f"UUID 格式错误: '{instance}'")
        elif fmt == "date-time" and not re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", instance
        ):
            errors.append(f"日期时间格式错误: '{instance}'，应为 ISO 8601")

    # 数值范围
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and instance < minimum:
            errors.append(f"值 {instance} 小于最小值 {minimum}")
        if maximum is not None and instance > maximum:
            errors.append(f"值 {instance} 大于最大值 {maximum}")

    # 字符串长度
    if isinstance(instance, str):
        min_len = schema.get("minLength")
        max_len = schema.get("maxLength")
        if min_len is not None and len(instance) < min_len:
            errors.append(f"字符串长度 {len(instance)} 小于最小长度 {min_len}")
        if max_len is not None and len(instance) > max_len:
            errors.append(f"字符串长度 {len(instance)} 大于最大长度 {max_len}")

    # 数组约束
    if isinstance(instance, list):
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if min_items is not None and len(instance) < min_items:
            errors.append(f"数组长度 {len(instance)} 小于最小项数 {min_items}")
        if max_items is not None and len(instance) > max_items:
            errors.append(f"数组长度 {len(instance)} 大于最大项数 {max_items}")
        # items schema — 对每个元素递归校验
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for i, elem in enumerate(instance):
                sub_errors = _jsonschema_validate(elem, items_schema)
                for e in sub_errors:
                    errors.append(f"[{i}] {e}")

    # 对象: required + properties + additionalProperties
    if isinstance(instance, dict):
        required = schema.get("required", [])
        for field in required:
            if field not in instance:
                errors.append(f"缺少必填字段: {field}")

        properties = schema.get("properties", {})
        for key, prop_schema in properties.items():
            if key in instance and instance[key] is not None:
                sub_errors = _jsonschema_validate(instance[key], prop_schema)
                for e in sub_errors:
                    errors.append(f".{key}: {e}")

        if schema.get("additionalProperties") is False:
            allowed = set(properties.keys())
            extra = set(instance.keys()) - allowed
            if extra:
                errors.append(f"存在多余字段: {', '.join(sorted(extra))}")

    return errors


def _check_type(instance: object, expected: str | list[str]) -> bool:
    """检查 instance 是否匹配期望类型。"""
    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }
    types = [expected] if isinstance(expected, str) else expected
    for t in types:
        checker = type_map.get(t)
        if checker is None:
            continue
        if isinstance(instance, checker):
            # int 不是 bool（JSON Schema 规范）
            if t == "integer" and isinstance(instance, bool):
                continue
            return True
    return False


# ---------------------------------------------------------------------------
# Python 前置检查（Schema 难以表达的规则）
# ---------------------------------------------------------------------------

URL_PATTERN = re.compile(r"^https?://\S+$")


def _extra_checks(item: dict, index: int) -> list[str]:
    """Schema 之外的轻量校验。"""
    errors: list[str] = []

    # source_url 格式
    url = item.get("source_url")
    if isinstance(url, str) and url and not URL_PATTERN.match(url):
        errors.append(f"[{index}] source_url 格式错误: '{url}'")

    # summary 最少 20 字
    summary = item.get("summary", "")
    if isinstance(summary, str) and len(summary) < 20:
        errors.append(f"[{index}] summary 过短: 当前 {len(summary)} 字，最少需要 20 字")

    # tags 至少 1 个
    tags = item.get("tags")
    if isinstance(tags, list) and len(tags) < 1:
        errors.append(f"[{index}] tags 至少需要 1 个标签")

    return errors


# ---------------------------------------------------------------------------
# 文件级校验
# ---------------------------------------------------------------------------


def validate_file(filepath: Path, schema: dict | None = None) -> tuple[int, int, list[str]]:
    """校验单个 JSON 文件。

    支持两种格式:
      - 单条目对象 {...}
      - 条目数组 [{...}, {...}, ...]

    如果 schema 为 None，会根据文件名自动匹配。
    匹配失败时仅执行 Python 前置检查。

    Returns:
        (passed_count, total_count, errors)
    """
    errors: list[str] = []

    # 1) JSON 解析
    try:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        errors.append(f"JSON 解析失败: {exc}")
        return 0, 0, errors

    # 2) 归一化为列表
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [data]
    else:
        errors.append(f"JSON 根元素应为对象或数组，实际为 {type(data).__name__}")
        return 0, 0, errors

    # 3) 自动匹配 schema，如果是数组 schema 则提取 items 子 schema
    if schema is None:
        schema = _detect_schema(filepath)
    if schema is not None and schema.get("type") == "array":
        schema = schema.get("items", {})

    # 4) 逐条校验
    passed = 0
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"[{idx}] 条目不是对象，而是 {type(item).__name__}")
            continue

        item_errors: list[str] = []

        # 4a) JSON Schema 校验
        if schema is not None:
            schema_errors = _jsonschema_validate(item, schema)
            for e in schema_errors:
                item_errors.append(f"[{idx}] {e}")

        # 4b) Python 前置检查
        item_errors.extend(_extra_checks(item, idx))

        if item_errors:
            errors.extend(item_errors)
        else:
            passed += 1

    return passed, len(items), errors


# ---------------------------------------------------------------------------
# Hook 模式（从 stdin 读取 Claude Code 传入的文件路径）
# ---------------------------------------------------------------------------


def _log_hook_call(file_paths: list[str]) -> None:
    """记录 hook 调用到诊断日志。"""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    fp = file_paths[0] if file_paths else '?'
    with open('hooks_diag.log', 'a', encoding='utf-8') as f:
        f.write(f'[{ts}] PreToolUse:validate_json.py | file={fp}\n')


def _try_hook_mode() -> list[str] | None:
    """尝试从 stdin 读取 hook 模式的文件路径。

    Returns:
        文件路径列表（匹配 knowledge/articles/*.json 时），
        或 None 表示非 hook 模式（交互式终端）。
        hook 模式下任何异常均静默 exit(0)，不阻塞写入。
    """
    if sys.stdin.isatty():
        return None

    try:
        raw = sys.stdin.read()
    except Exception:
        sys.exit(0)

    if not raw.strip():
        sys.exit(0)

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    norm = file_path.replace("\\", "/")
    if "knowledge/articles/" not in norm or not norm.endswith(".json"):
        sys.exit(0)

    return [file_path]


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def _collect_files(paths: list[str]) -> list[Path]:
    """从命令行参数收集实际文件路径（展开通配符）。"""
    files: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            files.extend(sorted(path.glob("*.json")))
        elif path.is_file():
            files.append(path)
        else:
            # 尝试 glob（处理 shell 未展开的通配符）
            parent = path.parent
            if parent.is_dir():
                files.extend(sorted(parent.glob(path.name)))
            else:
                print(f"警告: 路径不存在: {p}", file=sys.stderr)
    return files


def main() -> None:
    hook_files = _try_hook_mode()
    if hook_files is not None:
        _log_hook_call(hook_files)
        files = [Path(p) for p in hook_files]
    elif len(sys.argv) >= 2:
        files = _collect_files(sys.argv[1:])
    else:
        print("用法: python hooks/validate_json.py <file.json> [file2.json ...]", file=sys.stderr)
        sys.exit(1)
    if not files:
        print("错误: 未找到匹配的 JSON 文件", file=sys.stderr)
        sys.exit(1)

    total_passed = 0
    total_items = 0
    all_errors: list[str] = []

    for filepath in files:
        passed, count, errors = validate_file(filepath)
        total_passed += passed
        total_items += count
        if errors:
            rel = filepath.relative_to(Path.cwd()) if filepath.is_relative_to(Path.cwd()) else filepath
            all_errors.append(f"--- {rel} ({passed}/{count} 通过) ---")
            all_errors.extend(errors)

    if all_errors:
        print("\n".join(all_errors))

    print(f"\n汇总: {total_passed}/{total_items} 条目通过, {len(all_errors)} 个文件有错误")

    sys.exit(1 if all_errors else 0)


if __name__ == "__main__":
    main()
