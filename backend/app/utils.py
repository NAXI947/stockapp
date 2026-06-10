"""
公共工具函数模块
提取自 config.py 和 runtime_config.py 的重复函数
"""
from __future__ import annotations

import json
from typing import Any, Dict, List


def parse_bool(value: Any) -> bool:
    """解析布尔值"""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def parse_list(value: Any) -> List[str]:
    """解析列表值"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    raw = str(value).strip()
    if not raw:
        return []
    if raw.startswith('['):
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, list):
                return [str(v).strip() for v in loaded if str(v).strip()]
        except Exception:
            pass
    return [part.strip() for part in raw.split(',') if part.strip()]


def parse_dict_int(value: Any) -> Dict[str, int]:
    """解析字典整数值"""
    if value is None:
        return {}
    if isinstance(value, dict):
        result: Dict[str, int] = {}
        for key, val in value.items():
            try:
                parsed = int(val)
            except Exception:
                continue
            if parsed > 0:
                result[str(key)] = parsed
        return result
    raw = str(value).strip()
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(loaded, dict):
        return {}
    result: Dict[str, int] = {}
    for key, val in loaded.items():
        try:
            parsed = int(val)
        except Exception:
            continue
        if parsed > 0:
            result[str(key)] = parsed
    return result


def parse_dict_float(value: Any) -> Dict[str, float]:
    """解析字典浮点值"""
    if value is None:
        return {}
    if isinstance(value, dict):
        result: Dict[str, float] = {}
        for key, val in value.items():
            try:
                parsed = float(val)
            except Exception:
                continue
            if parsed > 0:
                result[str(key)] = parsed
        return result
    raw = str(value).strip()
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(loaded, dict):
        return {}
    result: Dict[str, float] = {}
    for key, val in loaded.items():
        try:
            parsed = float(val)
        except Exception:
            continue
        if parsed > 0:
            result[str(key)] = parsed
    return result


def to_float(value: Any) -> float | None:
    """转换为浮点数"""
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def to_int(value: Any) -> int | None:
    """转换为整数"""
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def parse_extra_json(value: Any) -> dict[str, Any]:
    """解析额外的JSON数据"""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def row_get(row: Any, key: str) -> Any:
    """从行数据中获取值"""
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except Exception:
        return None