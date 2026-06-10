from __future__ import annotations

import json
from decimal import Decimal
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import HTTPException

from backend.app.config import AiConfig
from backend.app.paths import resource_path
from backend.app.strategy.field_catalog import strategy_field_label
from backend.app.utils import to_float, to_int

PROMPT_DIR = resource_path("backend/app/prompts")
PROMPT_TEMPLATE_MAP = {
    "balanced": PROMPT_DIR / "stock_advice_balanced_prompt.txt",
    "risk_guarded": PROMPT_DIR / "stock_advice_risk_guarded_prompt.txt",
    "momentum": PROMPT_DIR / "stock_advice_momentum_prompt.txt",
}


def _query_one(database, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    rows = database.fetch_all(sql, params)
    return dict(rows[0]) if rows else None


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


def build_stock_analysis_context(database, symbol: str) -> dict[str, Any]:
    strategy = _query_one(
        database,
        """
        SELECT trade_date, final_score, pct_chg, winner_rate, float_risk_7d,
               ma5, ma20, ma60, turnover_rate, volume_ratio, upper_space, vol_score
        FROM t_strategy_daily
        WHERE ts_code = %s
        ORDER BY trade_date DESC
        LIMIT 1
        """,
        (symbol,),
    )
    if not strategy:
        raise HTTPException(status_code=404, detail="stock not found")

    stock = _query_one(
        database,
        """
        SELECT ts_code, symbol, name, industry, sw_level1_name, sw_level2_name, list_date
        FROM t_stock_basic
        WHERE ts_code = %s
        LIMIT 1
        """,
        (symbol,),
    ) or {}

    trade_date = str(strategy.get("trade_date") or "")
    cyq = _query_one(
        database,
        """
        SELECT winner_rate, cost_50, cost_85, concentration
        FROM t_cyq_perf
        WHERE ts_code = %s AND trade_date = %s
        LIMIT 1
        """,
        (symbol, trade_date),
    ) or {}

    fin = _query_one(
        database,
        """
        SELECT ann_date, end_date, debt_to_assets, roe
        FROM t_fin_indicator
        WHERE ts_code = %s
        ORDER BY end_date DESC, ann_date DESC
        LIMIT 1
        """,
        (symbol,),
    ) or {}

    top_list = database.fetch_all(
        """
        SELECT trade_date, name, net, buy, sell, reason
        FROM t_top_list
        WHERE ts_code = %s
        ORDER BY trade_date DESC, id DESC
        LIMIT 3
        """,
        (symbol,),
    )

    recent_bars = [
        {
            "trade_date": row["trade_date"],
            "open": to_float(row.get("open")),
            "close": to_float(row.get("close")),
            "low": to_float(row.get("low")),
            "high": to_float(row.get("high")),
            "pct_chg": to_float(row.get("pct_chg")),
            "vol": to_float(row.get("vol")),
        }
        for row in database.fetch_all(
            """
            SELECT trade_date, open, close, low, high, pct_chg, vol
            FROM t_daily_bar
            WHERE ts_code = %s
            ORDER BY trade_date DESC
            LIMIT 20
            """,
            (symbol,),
        )
    ]

    upcoming_float: list[dict[str, Any]] = []
    if trade_date:
        try:
            end_date = (datetime.strptime(trade_date, "%Y%m%d") + timedelta(days=30)).strftime("%Y%m%d")
            upcoming_float = [
                dict(row)
                for row in database.fetch_all(
                    """
                    SELECT ann_date, float_date, float_share, float_ratio, holder_name, share_type
                    FROM t_share_float
                    WHERE ts_code = %s AND float_date > %s AND float_date <= %s
                    ORDER BY float_date ASC
                    LIMIT 5
                    """,
                    (symbol, trade_date, end_date),
                )
            ]
        except Exception:
            upcoming_float = []

    trend_snapshot = {}
    if recent_bars:
        latest_bar = recent_bars[0]
        oldest_bar = recent_bars[-1]
        latest_close = to_float(latest_bar.get("close"))
        oldest_close = to_float(oldest_bar.get("close"))
        trend_snapshot = {
            "latest_trade_date": latest_bar.get("trade_date"),
            "latest_close": latest_close,
            "window_return_pct": round(((latest_close - oldest_close) / oldest_close) * 100, 2)
            if latest_close is not None and oldest_close not in (None, 0)
            else None,
            "highest_high_20d": max(
                [to_float(item.get("high")) or float("-inf") for item in recent_bars],
                default=None,
            ),
            "lowest_low_20d": min(
                [to_float(item.get("low")) or float("inf") for item in recent_bars],
                default=None,
            ),
        }

    return {
        "stock": stock,
        "strategy": {
            "trade_date": strategy.get("trade_date"),
            "final_score": to_int(strategy.get("final_score")),
            "pct_chg": to_float(strategy.get("pct_chg")),
            "winner_rate": to_float(strategy.get("winner_rate")),
            "float_risk_7d": to_int(strategy.get("float_risk_7d")),
            "ma5": to_float(strategy.get("ma5")),
            "ma20": to_float(strategy.get("ma20")),
            "ma60": to_float(strategy.get("ma60")),
            "turnover_rate": to_float(strategy.get("turnover_rate")),
            "volume_ratio": to_float(strategy.get("volume_ratio")),
        },
        "cyq": {
            "winner_rate": to_float(cyq.get("winner_rate")),
            "cost_50": to_float(cyq.get("cost_50")),
            "cost_85": to_float(cyq.get("cost_85")),
            "concentration": to_float(cyq.get("concentration")),
        },
        "fin_indicator": {
            "ann_date": fin.get("ann_date"),
            "end_date": fin.get("end_date"),
            "debt_to_assets": to_float(fin.get("debt_to_assets")),
            "roe": to_float(fin.get("roe")),
        },
        "recent_bars": recent_bars,
        "trend_snapshot": trend_snapshot,
        "top_list": _json_safe([dict(row) for row in top_list]),
        "upcoming_float": _json_safe(upcoming_float),
    }


def _build_retrieval_digest(context: dict[str, Any]) -> str:
    stock = context.get("stock") or {}
    strategy = context.get("strategy") or {}
    trend = context.get("trend_snapshot") or {}
    fin = context.get("fin_indicator") or {}
    cyq = context.get("cyq") or {}
    top_list = context.get("top_list") or []
    upcoming_float = context.get("upcoming_float") or []

    lines = [
        f"- 标的: {stock.get('name') or stock.get('ts_code') or ''} / 行业: {stock.get('industry') or '-'}",
        f"- 最新交易日: {strategy.get('trade_date') or '-'} / {strategy_field_label('final_score')}: {strategy.get('final_score') or '-'} / {strategy_field_label('pct_chg')}: {strategy.get('pct_chg') or '-'}%",
        f"- 均线: {strategy_field_label('ma5')}={strategy.get('ma5') or '-'} {strategy_field_label('ma20')}={strategy.get('ma20') or '-'} {strategy_field_label('ma60')}={strategy.get('ma60') or '-'}",
        f"- 筹码: {strategy_field_label('winner_rate')}={cyq.get('winner_rate') or '-'} cost_50={cyq.get('cost_50') or '-'} cost_85={cyq.get('cost_85') or '-'}",
        f"- 结构: {strategy_field_label('upper_space')}={strategy.get('upper_space') or '-'}% {strategy_field_label('vol_score')}={strategy.get('vol_score') or '-'}",
        f"- 财务: roe={fin.get('roe') or '-'} debt_to_assets={fin.get('debt_to_assets') or '-'}",
        f"- 20日趋势: 最新收盘={trend.get('latest_close') or '-'} 20日区间收益={trend.get('window_return_pct') or '-'}%",
        f"- 龙虎榜次数: {len(top_list)} / 未来30天解禁事件: {len(upcoming_float)}",
    ]
    return "\n".join(lines)


def _candidate_models(ai_config: AiConfig) -> list[str]:
    ordered: list[str] = []
    primary = (ai_config.model or "").strip()
    if primary:
        ordered.append(primary)
    for item in ai_config.models or []:
        candidate = item.strip()
        if candidate and candidate not in ordered:
            ordered.append(candidate)
    return ordered


def _select_prompt_variant(context: dict[str, Any], strategy_name: str) -> str:
    strategy = context.get("strategy") or {}
    trend = context.get("trend_snapshot") or {}
    risk_flag = int(strategy.get("float_risk_7d") or 0)
    final_score = int(strategy.get("final_score") or 0)
    window_return = float(trend.get("window_return_pct") or 0.0)

    normalized = (strategy_name or "auto").strip().lower()
    if normalized in PROMPT_TEMPLATE_MAP:
        return normalized
    if normalized == "risk_first":
        return "risk_guarded"
    if normalized == "trend_first":
        return "momentum"
    if risk_flag:
        return "risk_guarded"
    if final_score >= 70 and window_return > 0:
        return "momentum"
    return "balanced"


def _load_prompt_template(variant: str) -> str:
    path = PROMPT_TEMPLATE_MAP.get(variant, PROMPT_TEMPLATE_MAP["balanced"])
    return path.read_text(encoding="utf-8")


def build_rule_based_advice(context: dict[str, Any]) -> tuple[str, str]:
    strategy = context.get("strategy") or {}
    stock = context.get("stock") or {}
    score = int(strategy.get("final_score") or 0)
    pct_chg = float(strategy.get("pct_chg") or 0.0)
    winner_rate = float(strategy.get("winner_rate") or 0.0)
    risk_flag = int(strategy.get("float_risk_7d") or 0)

    advice_lines = [
        f"### {stock.get('name') or context.get('stock', {}).get('ts_code') or '个股'}分析",
        f"- {strategy_field_label('final_score')}: {score}",
        f"- {strategy_field_label('pct_chg')}: {pct_chg:.2f}%",
        f"- {strategy_field_label('winner_rate')}: {winner_rate:.2f}%",
        "- 当前输出为本地规则分析。",
    ]
    if risk_flag:
        advice_lines.append("- 未来 7 天存在较高解禁风险，建议降低仓位或回避。")
        warning = "已识别到未来 7 天较高解禁风险。"
    else:
        warning = "当前未识别到近 7 天高解禁风险。"
    return "\n".join(advice_lines), warning


def _call_openai_compatible(ai_config: AiConfig, model: str, prompt_variant: str, context: dict[str, Any], symbol: str, market: str) -> str:
    if not (ai_config.enabled and ai_config.base_url and ai_config.api_key and model):
        raise RuntimeError("AI configuration incomplete")
    parsed = urlparse(ai_config.base_url.rstrip("/"))
    base_path = parsed.path.rstrip("/")
    if base_path.endswith("/chat/completions"):
        endpoint = ai_config.base_url.rstrip("/")
    elif base_path.endswith("/v1"):
        endpoint = ai_config.base_url.rstrip("/") + "/chat/completions"
    else:
        endpoint = ai_config.base_url.rstrip("/") + "/v1/chat/completions"
    safe_context = _json_safe(context)
    system_prompt = "你是 A 股研究助手。请严格遵守用户提供的模板和约束。"
    user_prompt = _load_prompt_template(prompt_variant).format(
        symbol=symbol,
        market=market,
        retrieval_digest=_build_retrieval_digest(safe_context),
        context_json=json.dumps(safe_context, ensure_ascii=False, separators=(",", ":")),
    )
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
    ).encode("utf-8")
    request = Request(
        endpoint,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {ai_config.api_key}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=ai_config.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"LLM request failed: {exc}") from exc

    try:
        return str(body["choices"][0]["message"]["content"]).strip()
    except Exception as exc:
        raise RuntimeError("LLM response format invalid") from exc


def generate_stock_advice(database, ai_config: AiConfig, symbol: str, market: str) -> dict[str, Any]:
    context = build_stock_analysis_context(database, symbol)
    current_price = None
    strategy = context.get("strategy") or {}
    if strategy.get("pct_chg") is not None:
        current_price = None

    fallback_markdown, fallback_warning = build_rule_based_advice(context)
    prompt_variant = _select_prompt_variant(context, ai_config.prompt_strategy)
    candidate_models = _candidate_models(ai_config)
    if not ai_config.enabled:
        return {
            "symbol": symbol,
            "current_price": current_price,
            "advice_markdown": fallback_markdown,
            "risk_warning": fallback_warning + " 当前未启用 LLM 分析。",
            "analysis_mode": "rule_fallback",
            "analysis_meta": {"prompt_variant": prompt_variant, "model": None, "fallback_reason": "ai_disabled"},
        }

    last_error = "AI configuration incomplete"
    for model in candidate_models:
        try:
            llm_markdown = _call_openai_compatible(ai_config, model, prompt_variant, context, symbol, market)
            risk_warning = fallback_warning
            if int(strategy.get("float_risk_7d") or 0):
                risk_warning = fallback_warning + " LLM 输出仅供辅助判断。"
            else:
                risk_warning = "LLM 输出仅供辅助判断，不构成投资建议。"
            return {
                "symbol": symbol,
                "current_price": current_price,
                "advice_markdown": llm_markdown or fallback_markdown,
                "risk_warning": risk_warning,
                "analysis_mode": "llm",
                "analysis_meta": {"prompt_variant": prompt_variant, "model": model, "fallback_reason": None},
            }
        except RuntimeError as exc:
            last_error = str(exc)

    return {
        "symbol": symbol,
        "current_price": current_price,
        "advice_markdown": fallback_markdown,
        "risk_warning": f"{fallback_warning} LLM 调用失败，已回退为规则分析：{last_error}",
        "analysis_mode": "rule_fallback",
        "analysis_meta": {"prompt_variant": prompt_variant, "model": None, "fallback_reason": last_error},
    }
