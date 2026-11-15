"""契约校验：一个最小实现的 JSON Schema 子集。

支持 type / required / properties / additionalProperties / enum / const /
minLength / maxLength / pattern / minimum / maximum / minItems / maxItems /
items / minProperties / 本地 $ref / oneOf。

不支持外部 $ref、anyOf、allOf、patternProperties：遇到即报错，避免静默放宽。
"""

from __future__ import annotations

import re

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "integer": int,
    "number": (int, float),
}


def _resolve(schema: dict, root: dict, path: str) -> dict:
    ref = schema.get("$ref")
    if not ref:
        return schema
    if not ref.startswith("#/"):
        raise ValueError(f"{path}: 不支持外部 $ref: {ref}")
    node: object = root
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"{path}: 无法解析 $ref: {ref}")
        node = node[part]
    if not isinstance(node, dict):
        raise ValueError(f"{path}: $ref 指向的不是 schema: {ref}")
    merged = dict(node)
    for key, value in schema.items():
        if key != "$ref":
            merged[key] = value
    return merged


def validate_json(schema: dict, value, path: str = "$", root: dict | None = None) -> None:
    """按 schema 校验 value，失败抛 ValueError（调用方包装成 ContractError）。"""
    if not isinstance(schema, dict):
        return
    if root is None:
        root = schema

    for unsupported in ("anyOf", "allOf", "patternProperties"):
        if unsupported in schema:
            raise ValueError(f"{path}: 不支持的 schema 关键字 {unsupported}")

    schema = _resolve(schema, root, path)

    if "oneOf" in schema:
        passed = 0
        messages: list[str] = []
        for index, branch in enumerate(schema["oneOf"]):
            try:
                validate_json(branch, value, path, root)
                passed += 1
            except ValueError as exc:
                messages.append(f"branch#{index}: {exc}")
        if passed != 1:
            detail = "; ".join(messages[:3])
            raise ValueError(f"{path}: oneOf 需要恰好一个分支通过，实际 {passed} 个（{detail}）")

    expected_type = schema.get("type")
    if expected_type:
        if expected_type not in _TYPES:
            raise ValueError(f"{path}: 不支持的 schema type: {expected_type}")
        if expected_type in ("integer", "number") and isinstance(value, bool):
            raise ValueError(f"{path}: 期望 {expected_type}，实际 boolean")
        elif expected_type == "string":
            if not isinstance(value, str):
                raise ValueError(f"{path}: 期望 string，实际 {type(value).__name__}")
        elif not isinstance(value, _TYPES[expected_type]):
            raise ValueError(f"{path}: 期望 {expected_type}，实际 {type(value).__name__}")

    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{path}: 期望常量 {schema['const']!r}，实际 {value!r}")

    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: {value!r} 不在枚举 {schema['enum']!r} 中")

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"{path}: 缺少必填字段 {key}")
        props = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in props:
                validate_json(props[key], item, f"{path}.{key}", root)
            elif additional is False:
                raise ValueError(f"{path}: 不允许的字段 {key}")
            elif isinstance(additional, dict):
                validate_json(additional, item, f"{path}.{key}", root)
        if "minProperties" in schema and len(value) < schema["minProperties"]:
            raise ValueError(f"{path}: 至少需要 {schema['minProperties']} 个字段")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise ValueError(f"{path}: 至少需要 {schema['minItems']} 项")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValueError(f"{path}: 最多允许 {schema['maxItems']} 项")
        if "items" in schema:
            for index, item in enumerate(value):
                validate_json(schema["items"], item, f"{path}[{index}]", root)

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ValueError(f"{path}: 长度不足 {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValueError(f"{path}: 长度超过 {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            raise ValueError(f"{path}: 不匹配模式 {schema['pattern']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path}: 小于最小值 {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{path}: 大于最大值 {schema['maximum']}")
