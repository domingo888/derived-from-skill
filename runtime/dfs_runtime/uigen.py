"""由 input_schema 生成表单描述，供 Web UI 与窗口 UI 共用。

规范：UI 不得手写字段列表，必须从 schema 推导，保证「契约改了 UI 自动跟着变」。
"""

from __future__ import annotations


def describe_fields(input_schema: dict) -> list[dict]:
    properties = input_schema.get("properties") or {}
    required = input_schema.get("required") or []
    fields: list[dict] = []

    for name, meta in properties.items():
        if not isinstance(meta, dict):
            meta = {}
        field_type = meta.get("type", "string")
        field = {
            "name": name,
            "type": field_type,
            "required": name in required,
            "label": meta.get("title") or name,
            "description": meta.get("description") or "",
            "placeholder": meta.get("examples", [""])[0] if isinstance(meta.get("examples"), list) else "",
            "enum": meta.get("enum"),
            "default": meta.get("default", ""),
            "multiline": bool(meta.get("format") == "text" or field_type == "array"),
        }
        if field_type == "array":
            field["itemType"] = (meta.get("items") or {}).get("type", "string")
        if field_type in ("integer", "number"):
            field["minimum"] = meta.get("minimum")
            field["maximum"] = meta.get("maximum")
        fields.append(field)

    return fields


def default_values(input_schema: dict) -> dict:
    values: dict = {}
    for field in describe_fields(input_schema):
        if field["default"] not in ("", None):
            values[field["name"]] = field["default"]
    return values


def coerce_input(values: dict, input_schema: dict) -> dict:
    """把表单里的字符串转换成 schema 要求的类型，失败时汇总报错。"""
    properties = input_schema.get("properties") or {}
    required = input_schema.get("required") or []
    result: dict = {}
    errors: list[str] = []

    for name, meta in properties.items():
        if not isinstance(meta, dict):
            meta = {}
        raw = values.get(name)
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            if name in required:
                errors.append(f"{name}: 必填")
            continue

        field_type = meta.get("type", "string")
        try:
            if field_type == "integer":
                result[name] = int(str(raw).strip())
            elif field_type == "number":
                result[name] = float(str(raw).strip())
            elif field_type == "boolean":
                if isinstance(raw, bool):
                    result[name] = raw
                else:
                    text = str(raw).strip().lower()
                    if text in ("1", "true", "yes", "on", "是"):
                        result[name] = True
                    elif text in ("0", "false", "no", "off", "否"):
                        result[name] = False
                    else:
                        raise ValueError("应为 true / false")
            elif field_type == "array":
                if isinstance(raw, list):
                    items = raw
                else:
                    text = str(raw)
                    separator = "\n" if "\n" in text else ","
                    items = [part.strip() for part in text.split(separator) if part.strip()]
                item_type = (meta.get("items") or {}).get("type", "string")
                if item_type == "integer":
                    items = [int(item) for item in items]
                elif item_type == "number":
                    items = [float(item) for item in items]
                result[name] = items
            else:
                result[name] = raw if isinstance(raw, str) else str(raw)
        except (TypeError, ValueError) as exc:
            errors.append(f"{name}: {exc}")

    if errors:
        raise ValueError("; ".join(errors))
    return result
