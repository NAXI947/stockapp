from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.local_job_log_store import LOG_DIR
from backend.app.utils import row_get


UPDATE_NOTES = {
    "daily": "数据更新页：日更；依次运行 jobs/job_daily_common.py、jobs/job_daily_featured.py、jobs/job_daily_strategy.py --latest-only",
    "update_date": "数据更新页：按日期补更；依次运行指定日期的 daily_common、daily_featured、daily_strategy",
    "weekly": "数据更新页：全量周更；脚本 jobs/job_weekly.py",
    "monthly": "数据更新页：全量月更；脚本 jobs/job_monthly.py",
    "yearly": "数据更新页：全量年更；依次运行 jobs/job_quarterly.py、jobs/job_yearly.py",
    "manual_ambush": "页面手工维护；接口 /api/v1/ambush",
}


TABLE_SPECS: list[dict[str, Any]] = [
    {
        "table": "t_stock_basic",
        "label": "股票基础信息",
        "date_field": "updated_at",
        "coverage": "stock_rows",
        "updater": f"{UPDATE_NOTES['daily']}；申万行业字段由 {UPDATE_NOTES['weekly']} 更新",
        "fields": ["ts_code", "symbol", "name", "industry", "sw_level1_name", "sw_level2_name", "list_date", "updated_at"],
        "field_updaters": {
            "sw_level1_name": UPDATE_NOTES["weekly"],
            "sw_level2_name": UPDATE_NOTES["weekly"],
        },
    },
    {
        "table": "t_trade_cal",
        "label": "交易日历",
        "date_field": "cal_date",
        "updater": UPDATE_NOTES["daily"],
        "fields": ["cal_date", "is_open", "updated_at"],
    },
    {
        "table": "t_daily_bar",
        "label": "日行情",
        "date_field": "trade_date",
        "coverage": "per_stock_latest",
        "align_market_date": True,
        "updater": UPDATE_NOTES["daily"],
        "fields": ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount", "pct_chg"],
    },
    {
        "table": "t_adj_factor",
        "label": "复权因子",
        "date_field": "trade_date",
        "coverage": "per_stock_latest",
        "align_market_date": True,
        "updater": UPDATE_NOTES["daily"],
        "fields": ["ts_code", "trade_date", "adj_factor"],
    },
    {
        "table": "t_daily_basic",
        "label": "每日指标",
        "date_field": "trade_date",
        "coverage": "per_stock_latest",
        "align_market_date": True,
        "updater": UPDATE_NOTES["daily"],
        "fields": ["ts_code", "trade_date", "turnover_rate", "volume_ratio", "circ_mv"],
    },
    {
        "table": "t_concept_detail",
        "label": "概念明细",
        "coverage": "stock_distinct",
        "updater": UPDATE_NOTES["monthly"],
        "fields": ["id", "concept_name", "ts_code", "name"],
    },
    {
        "table": "t_cyq_perf",
        "label": "筹码分布",
        "date_field": "trade_date",
        "coverage": "per_stock_latest",
        "align_market_date": True,
        "updater": UPDATE_NOTES["daily"],
        "fields": ["ts_code", "trade_date", "winner_rate", "cost_50", "cost_85", "concentration"],
        "field_updaters": {"concentration": "由 cost_50pct 兼容填充；同 jobs/job_daily_featured.py"},
    },
    {
        "table": "t_top_list",
        "label": "龙虎榜",
        "date_field": "trade_date",
        "updater": UPDATE_NOTES["daily"],
        "fields": ["ts_code", "trade_date", "name", "net", "buy", "sell", "reason"],
        "field_updaters": {
            "net": "Tushare top_list.net_amount -> t_top_list.net；jobs/job_daily_common.py",
            "buy": "Tushare top_list.l_buy -> t_top_list.buy；jobs/job_daily_common.py",
            "sell": "Tushare top_list.l_sell -> t_top_list.sell；jobs/job_daily_common.py",
        },
    },
    {
        "table": "t_share_float",
        "label": "限售解禁",
        "date_field": "float_date",
        "updater": UPDATE_NOTES["monthly"],
        "fields": ["ts_code", "ann_date", "float_date", "float_share", "float_ratio", "holder_name", "share_type"],
    },
    {
        "table": "t_fin_indicator",
        "label": "财务指标",
        "date_field": "end_date",
        "coverage": "stock_distinct",
        "updater": UPDATE_NOTES["yearly"],
        "fields": ["ts_code", "ann_date", "end_date", "debt_to_assets", "roe"],
    },
    {
        "table": "t_strategy_daily",
        "label": "策略结果",
        "date_field": "trade_date",
        "coverage": "per_stock_latest",
        "align_market_date": True,
        "updater": f"{UPDATE_NOTES['daily']}；全量重算也可用 {UPDATE_NOTES['yearly']}",
        "fields": [
            "ts_code", "trade_date", "ma5", "ma20", "ma60", "upper_space", "vol_score",
            "is_limit_up", "limit_up_20d", "bull_trend", "avg_price_support", "float_risk_7d",
            "final_score", "pct_chg", "turnover_rate", "volume_ratio", "winner_rate",
            "trend_baseline", "chip_vacuum", "kline_body", "liquidity_base", "safety_margin",
            "top_list_3d", "st_risk", "rejected", "reject_reason",
        ],
    },
    {
        "table": "t_ambush_pool",
        "label": "埋伏池",
        "date_field": "update_time",
        "updater": UPDATE_NOTES["manual_ambush"],
        "fields": ["ts_code", "expected_logic", "add_date", "status", "update_time"],
    },
]


def build_data_health_report(database) -> dict[str, Any]:
    stock_count = _safe_count(database, "t_stock_basic")
    market_latest = _safe_scalar(database, "SELECT MAX(trade_date) AS value FROM t_daily_bar")
    latest_logs = _read_latest_table_logs(LOG_DIR / "job_table.log")
    items = []
    warnings = []

    for spec in TABLE_SPECS:
        item = _build_table_item(database, spec, stock_count, market_latest, latest_logs)
        items.append(item)
        warnings.extend(_table_warnings(item))

    summary = {
        "table_count": len(items),
        "ok_count": sum(1 for item in items if item["status"] == "ok"),
        "warning_count": sum(1 for item in items if item["status"] == "warning"),
        "empty_count": sum(1 for item in items if item["status"] == "empty"),
        "stock_count": stock_count,
        "market_latest_trade_date": market_latest,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return {"summary": summary, "items": items, "warnings": warnings[:20]}


def _build_table_item(database, spec: dict[str, Any], stock_count: int, market_latest: str | None, latest_logs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    table = spec["table"]
    date_field = spec.get("date_field")
    total_rows = _safe_count(database, table)
    latest_value = _safe_scalar(database, f"SELECT MAX({date_field}) AS value FROM {table}") if date_field else None
    latest_rows = _count_for_date(database, table, date_field, latest_value) if date_field and latest_value else total_rows
    coverage = _coverage(database, spec, total_rows, latest_rows, latest_value, stock_count)
    fields = [
        _field_item(database, spec, field, date_field, latest_value, latest_rows, total_rows)
        for field in spec["fields"]
    ]
    latest_log = latest_logs.get(table)
    status = _table_status(total_rows, coverage, spec, latest_value, market_latest, fields)
    return {
        "table_name": table,
        "label": spec["label"],
        "updater": spec.get("updater") or "-",
        "status": status,
        "total_rows": total_rows,
        "latest_date_field": date_field,
        "latest_date": latest_value,
        "latest_rows": latest_rows,
        "completion_rate": coverage["rate"],
        "completion_text": coverage["text"],
        "expected_rows": coverage["expected"],
        "actual_rows": coverage["actual"],
        "latest_job_at": latest_log.get("logged_at") if latest_log else None,
        "latest_job_status": latest_log.get("status") if latest_log else None,
        "latest_job_message": latest_log.get("message") if latest_log else None,
        "fields": fields,
    }


def _field_item(database, spec: dict[str, Any], field: str, date_field: str | None, latest_value: str | None, latest_rows: int, total_rows: int) -> dict[str, Any]:
    table = spec["table"]
    base_total = latest_rows if date_field and latest_value else total_rows
    if date_field and latest_value:
        non_null = _safe_scalar(
            database,
            f"SELECT COUNT(1) AS value FROM {table} WHERE {date_field} = %s AND {field} IS NOT NULL AND CAST({field} AS TEXT) != ''",
            (latest_value,),
            default=0,
        )
    else:
        non_null = _safe_scalar(
            database,
            f"SELECT COUNT(1) AS value FROM {table} WHERE {field} IS NOT NULL AND CAST({field} AS TEXT) != ''",
            default=0,
        )
    latest_field_date = None
    if date_field:
        latest_field_date = _safe_scalar(
            database,
            f"SELECT MAX({date_field}) AS value FROM {table} WHERE {field} IS NOT NULL AND CAST({field} AS TEXT) != ''",
        )
    rate = _rate(int(non_null or 0), int(base_total or 0))
    return {
        "field": field,
        "latest_date": latest_field_date,
        "non_null_rows": int(non_null or 0),
        "total_rows": int(base_total or 0),
        "completion_rate": rate,
        "status": "ok" if rate is None or rate >= 0.95 else "warning",
        "updater": spec.get("field_updaters", {}).get(field) or spec.get("updater") or "-",
    }


def _coverage(database, spec: dict[str, Any], total_rows: int, latest_rows: int, latest_value: str | None, stock_count: int) -> dict[str, Any]:
    mode = spec.get("coverage")
    table = spec["table"]
    if mode == "per_stock_latest" and latest_value and stock_count:
        distinct_count = int(_safe_scalar(database, f"SELECT COUNT(DISTINCT ts_code) AS value FROM {table} WHERE {spec['date_field']} = %s", (latest_value,), default=0) or 0)
        return {"actual": distinct_count, "expected": stock_count, "rate": _rate(distinct_count, stock_count), "text": f"{distinct_count}/{stock_count} 只股票"}
    if mode == "stock_distinct" and stock_count:
        distinct_count = int(_safe_scalar(database, f"SELECT COUNT(DISTINCT ts_code) AS value FROM {table}", default=0) or 0)
        return {"actual": distinct_count, "expected": stock_count, "rate": _rate(distinct_count, stock_count), "text": f"{distinct_count}/{stock_count} 只股票"}
    if mode == "stock_rows" and stock_count:
        return {"actual": total_rows, "expected": stock_count, "rate": _rate(total_rows, stock_count), "text": f"{total_rows}/{stock_count} 只股票"}
    return {"actual": latest_rows or total_rows, "expected": None, "rate": None, "text": f"{latest_rows or total_rows} 行"}


def _table_status(total_rows: int, coverage: dict[str, Any], spec: dict[str, Any], latest_value: str | None, market_latest: str | None, fields: list[dict[str, Any]]) -> str:
    if total_rows <= 0:
        return "empty"
    if spec.get("align_market_date") and market_latest and latest_value and latest_value < market_latest:
        return "warning"
    if coverage["rate"] is not None and coverage["rate"] < 0.8:
        return "warning"
    if any(field["status"] == "warning" for field in fields if field["field"] not in {"reject_reason", "industry", "sw_level1_name", "sw_level2_name"}):
        return "warning"
    return "ok"


def _table_warnings(item: dict[str, Any]) -> list[str]:
    if item["status"] == "empty":
        return [f"{item['label']} 没有数据"]
    if item["status"] != "warning":
        return []
    return [f"{item['label']} 可能存在漏更或字段缺失，最新日期：{item.get('latest_date') or '-'}，完成率：{_percent(item.get('completion_rate'))}"]


def _read_latest_table_logs(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    latest: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            table = payload.get("table_name")
            if not table:
                continue
            ts = int(payload.get("ts") or 0)
            current = latest.get(table)
            if not current or ts >= int(current.get("ts") or 0):
                payload["logged_at"] = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else None
                latest[table] = payload
    return latest


def _safe_count(database, table: str) -> int:
    try:
        return int(database.fetch_count(table))
    except Exception:
        return 0


def _safe_scalar(database, sql: str, params: tuple[Any, ...] = (), default: Any = None) -> Any:
    try:
        row = database.fetch_one(sql, params)
    except Exception:
        return default
    return row_get(row, "value") if row else default


def _count_for_date(database, table: str, date_field: str, latest_value: str) -> int:
    value = _safe_scalar(database, f"SELECT COUNT(1) AS value FROM {table} WHERE {date_field} = %s", (latest_value,), default=0)
    return int(value or 0)


def _rate(actual: int, expected: int) -> float | None:
    if expected <= 0:
        return None
    return round(min(actual / expected, 1.0), 4)


def _percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"
