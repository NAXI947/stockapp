from __future__ import annotations

from typing import Any


STRATEGY_FIELD_CATALOG: dict[str, dict[str, Any]] = {
    "pct_chg": {"label": "涨跌幅", "implemented": True},
    "turnover_rate": {"label": "换手率", "implemented": True},
    "volume_ratio": {"label": "量比", "implemented": True},
    "winner_rate": {"label": "获利盘比例", "implemented": True},
    "ma5": {"label": "MA5", "implemented": True},
    "ma10": {"label": "MA10", "implemented": True},
    "ma20": {"label": "MA20", "implemented": True},
    "ma60": {"label": "MA60", "implemented": True},
    "upper_space": {"label": "上方空间", "implemented": True},
    "vol_score": {"label": "成交量稳定性得分", "implemented": True},
    "is_limit_up": {"label": "当日涨停", "implemented": True},
    "limit_up_20d": {"label": "近20日涨停记忆", "implemented": True},
    "bull_trend": {"label": "多头趋势", "implemented": True},
    "float_risk_7d": {"label": "7日解禁风险", "implemented": True},
    "final_score": {"label": "策略分", "implemented": True},
    "trend_baseline": {"label": "趋势基线", "implemented": True},
    "chip_vacuum": {"label": "筹码真空", "implemented": True},
    "kline_body": {"label": "K线实体", "implemented": True},
    "liquidity_base": {"label": "量能活跃", "implemented": True},
    "safety_margin": {"label": "安全边际", "implemented": True},
    "top_list_3d": {"label": "近3日龙虎榜净流入", "implemented": True},
    "st_risk": {"label": "ST风险", "implemented": True},
    "rejected": {"label": "准入结果", "implemented": True},
    "reject_reason": {"label": "未通过原因", "implemented": True},
}


UNIMPLEMENTED_STRATEGY_FIELDS = sorted(
    field_name
    for field_name, meta in STRATEGY_FIELD_CATALOG.items()
    if not bool(meta.get("implemented"))
)


def strategy_field_label(field_name: str) -> str:
    meta = STRATEGY_FIELD_CATALOG.get(field_name) or {}
    return str(meta.get("label") or field_name)
