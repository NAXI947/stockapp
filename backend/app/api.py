from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.app.analysis_service import generate_stock_advice
from backend.app.config import get_desktop_tushare_status, load_config, save_desktop_tushare_token
from backend.app.data_health import build_data_health_report
from backend.app.schemas import (
    AmbushPoolCreate,
    AmbushPoolUpdate,
    AmbushPoolResponse,
    ApiResponse,
    DetailPayload,
    DetailResponse,
    DailyDateJobRunRequest,
    HistoryJobRunRequest,
    JobFailureDetailPayload,
    JobFailureDetailResponse,
    JobFailureTrendPayload,
    JobFailureTrendResponse,
    JobLogReportPayload,
    JobLogReportResponse,
    JobRunsPayload,
    JobRunsResponse,
    JobStageMetricsPayload,
    JobStageMetricsResponse,
    JobTableTrendPayload,
    JobTableTrendResponse,
    KlineResponse,
    PicksResponse,
    BatchSearchRequest,
    BatchSearchPayload,
    BatchSearchResponse,
    RuntimeConfigPayload,
    RuntimeConfigResponse,
    RuntimeConfigUpdateRequest,
    StockAdviceRequest,
    StockAdvicePayload,
    StockAdviceResponse,
    TushareTokenUpdateRequest,
)
from backend.app.job_log_report import build_job_log_report
from backend.app.job_ops_report import (
    build_job_stage_metrics,
    get_job_failure_detail,
    list_job_runs,
    summarize_failure_trends,
    summarize_table_trends,
)
from backend.app.job_runner import list_job_definitions, list_manual_tasks, run_manual_job
from backend.app.runtime_config import get_runtime_jobs_config, set_runtime_jobs_config
from backend.app.utils import to_float, to_int, parse_extra_json, row_get
from backend.core.deps import get_prepared_database

router = APIRouter(prefix="/api/v1")


router = APIRouter(prefix="/api/v1")


@router.get("/picks", response_model=PicksResponse)
def get_picks(date: Optional[str] = None, is_ambush: bool = False, is_sniper: bool = False, database=Depends(get_prepared_database)):
    target_date = date
    if not target_date:
        table_name = "t_sniper_daily" if is_sniper else "t_strategy_daily"
        latest = database.fetch_all(f"SELECT MAX(trade_date) AS trade_date FROM {table_name}")
        if not latest or not latest[0]["trade_date"]:
            return PicksResponse(data=[])
        target_date = latest[0]["trade_date"]

    if is_ambush:
        # 埋伏池筛选逻辑（v1.1 修正：移除硬过滤，增加动态异动判定）
        rows = database.fetch_all(
            """
            SELECT a.ts_code, b.name, b.industry, s.pct_chg, s.turnover_rate,
                   s.volume_ratio, s.winner_rate, s.upper_space, s.vol_score, s.final_score,
                   s.trend_baseline, s.chip_vacuum, s.kline_body, s.liquidity_base,
                   s.safety_margin, s.top_list_3d, s.st_risk, s.rejected, s.reject_reason,
                   a.expected_logic, a.add_date as ambush_add_date,
                   (COALESCE(s.liquidity_base, 0) = 1 OR COALESCE(s.kline_body, 0) = 1) AS is_action_triggered,
                   s.trend_reason,
                   (s.final_score - COALESCE((
                       SELECT prev.final_score 
                       FROM t_strategy_daily prev 
                       WHERE prev.ts_code = s.ts_code AND prev.trade_date < s.trade_date 
                       ORDER BY prev.trade_date DESC LIMIT 1
                   ), s.final_score)) AS score_change
            FROM t_ambush_pool a
            LEFT JOIN t_strategy_daily s ON s.ts_code = a.ts_code AND s.trade_date = %s
            LEFT JOIN t_stock_basic b ON b.ts_code = a.ts_code
            WHERE a.status = 1
            ORDER BY is_action_triggered DESC, s.chip_vacuum DESC, s.safety_margin DESC
            """,
            (target_date,),
        )
    elif is_sniper:
        # 极简狙击手独立选股逻辑
        rows = database.fetch_all(
            """
            SELECT s.ts_code, b.name, b.industry, s.pct_chg, s.turnover_rate,
                   s.volume_ratio, s.sniper_score as final_score, s.sniper_score,
                   s.sniper_rejected as rejected, s.sniper_rejected, s.sniper_reject_reason as reject_reason, s.sniper_reject_reason,
                   s.s_holder_score, s.s_chip_vacuum_score, s.s_ma_state_score,
                   s.s_safety_margin_score, s.s_macd_weekly_score, s.s_low_volume_score,
                   s.s_golden_pit_score, s.s_ignition_score, s.s_top_list_score,
                   s.s_news_score, s.s_base_total, s.s_dynamic_total,
                   s.trend_reason,
                   (s.sniper_score - COALESCE((
                        SELECT prev.sniper_score 
                        FROM t_sniper_daily prev 
                        WHERE prev.ts_code = s.ts_code AND prev.trade_date < s.trade_date 
                        ORDER BY prev.trade_date DESC LIMIT 1
                    ), s.sniper_score)) AS score_change
            FROM t_sniper_daily s
            LEFT JOIN t_stock_basic b ON b.ts_code = s.ts_code
            WHERE s.trade_date = %s
            ORDER BY s.sniper_score DESC, s.ts_code ASC
            LIMIT 10
            """,
            (target_date,),
        )
    else:
        # 原有选股逻辑
        rows = database.fetch_all(
            """
            SELECT s.ts_code, b.name, b.industry, s.pct_chg, s.turnover_rate,
                   s.volume_ratio, s.winner_rate, s.upper_space, s.vol_score, s.final_score,
                   s.trend_baseline, s.chip_vacuum, s.kline_body, s.liquidity_base,
                   s.safety_margin, s.top_list_3d, s.st_risk, s.rejected, s.reject_reason,
                   s.trend_reason,
                   (s.final_score - COALESCE((
                       SELECT prev.final_score 
                       FROM t_strategy_daily prev 
                       WHERE prev.ts_code = s.ts_code AND prev.trade_date < s.trade_date 
                       ORDER BY prev.trade_date DESC LIMIT 1
                   ), s.final_score)) AS score_change
            FROM t_strategy_daily s
            LEFT JOIN t_stock_basic b ON b.ts_code = s.ts_code
            WHERE s.trade_date = %s
            ORDER BY s.final_score DESC, s.ts_code ASC
            """,
            (target_date,),
        )
    
    concept_map: dict[str, list[str]] = {}
    score_trend_map: dict[str, list[int]] = {}
    if rows:
        source_table = "t_sniper_daily" if is_sniper else "t_strategy_daily"
        concept_sql = f"""
        SELECT DISTINCT c.ts_code, c.concept_name
        FROM t_concept_detail c
        INNER JOIN {source_table} s ON s.ts_code = c.ts_code
        WHERE s.trade_date = %s
        ORDER BY c.concept_name ASC
        """
        concept_rows = database.fetch_all(concept_sql, (target_date,))
        for row in concept_rows:
            ts_code = row_get(row, "ts_code")
            concept_name = row_get(row, "concept_name")
            if not ts_code or not concept_name:
                continue
            concept_list = concept_map.setdefault(ts_code, [])
            if concept_name not in concept_list:
                concept_list.append(concept_name)

        # 获取最近 7 个交易日的时间序列
        dates_rows = database.fetch_all(
            f"SELECT DISTINCT trade_date FROM {source_table} WHERE trade_date <= %s ORDER BY trade_date DESC LIMIT 7",
            (target_date,),
        )
        last_7_dates = sorted([r["trade_date"] for r in dates_rows])
        if last_7_dates:
            history_placeholders = ", ".join(["%s"] * len(last_7_dates))
            score_col = "sniper_score" if is_sniper else "final_score"
            history_sql = f"""
            SELECT ts_code, trade_date, {score_col} AS final_score
            FROM {source_table}
            WHERE trade_date IN ({history_placeholders})
            """
            history_rows = database.fetch_all(history_sql, tuple(last_7_dates))
            history_rows_sorted = sorted(history_rows, key=lambda x: x["trade_date"])
            for h_row in history_rows_sorted:
                code = h_row["ts_code"]
                score = to_int(h_row["final_score"])
                score_trend_map.setdefault(code, []).append(score)
    
    items = [
        {
            "ts_code": row["ts_code"],
            "name": row_get(row, "name"),
            "industry": row_get(row, "industry"),
            "concept_names": concept_map.get(row_get(row, "ts_code"), []),
            "concept_text": " / ".join(concept_map.get(row_get(row, "ts_code"), [])),
            "trade_date": target_date,
            "pct_chg": to_float(row_get(row, "pct_chg")),
            "turnover_rate": to_float(row_get(row, "turnover_rate")),
            "volume_ratio": to_float(row_get(row, "volume_ratio")),
            "winner_rate": to_float(row_get(row, "winner_rate")) if not is_sniper else None,
            "upper_space": to_float(row_get(row, "upper_space")) if not is_sniper else None,
            "vol_score": to_float(row_get(row, "vol_score")) if not is_sniper else None,
            "final_score": to_int(row_get(row, "final_score")),
            # v1.1 新增字段
            "trend_baseline": to_int(row_get(row, "trend_baseline")) if not is_sniper else None,
            "chip_vacuum": to_int(row_get(row, "chip_vacuum")) if not is_sniper else None,
            "kline_body": to_int(row_get(row, "kline_body")) if not is_sniper else None,
            "liquidity_base": to_int(row_get(row, "liquidity_base")) if not is_sniper else None,
            "safety_margin": to_int(row_get(row, "safety_margin")) if not is_sniper else None,
            "top_list_3d": to_int(row_get(row, "top_list_3d")) if not is_sniper else None,
            "st_risk": to_int(row_get(row, "st_risk")) if not is_sniper else None,
            "rejected": to_int(row_get(row, "rejected")),
            "reject_reason": row_get(row, "reject_reason"),
            # v1.2 新增：埋伏池相关动态字段
            "is_action_triggered": bool(row_get(row, "is_action_triggered")) if is_ambush else False,
            "ambush_add_date": row_get(row, "ambush_add_date") if is_ambush else None,
            "expected_logic": row_get(row, "expected_logic") if is_ambush else None,
            # v1.3 新增：狙击手归因与分数变化
            "trend_reason": row_get(row, "trend_reason"),
            "score_change": to_int(row_get(row, "score_change")),
            # v1.4 新增：7天评分趋势
            "score_trend": score_trend_map.get(row["ts_code"], [to_int(row_get(row, "final_score"))]) if row["ts_code"] in score_trend_map else [to_int(row_get(row, "final_score"))],
            # Sniper fields
            "sniper_score": to_int(row_get(row, "sniper_score")) if is_sniper else None,
            "sniper_rejected": to_int(row_get(row, "sniper_rejected")) if is_sniper else None,
            "sniper_reject_reason": row_get(row, "sniper_reject_reason") if is_sniper else None,
            "s_holder_score": to_int(row_get(row, "s_holder_score")) if is_sniper else None,
            "s_chip_vacuum_score": to_int(row_get(row, "s_chip_vacuum_score")) if is_sniper else None,
            "s_ma_state_score": to_int(row_get(row, "s_ma_state_score")) if is_sniper else None,
            "s_safety_margin_score": to_int(row_get(row, "s_safety_margin_score")) if is_sniper else None,
            "s_macd_weekly_score": to_int(row_get(row, "s_macd_weekly_score")) if is_sniper else None,
            "s_low_volume_score": to_int(row_get(row, "s_low_volume_score")) if is_sniper else None,
            "s_golden_pit_score": to_int(row_get(row, "s_golden_pit_score")) if is_sniper else None,
            "s_ignition_score": to_int(row_get(row, "s_ignition_score")) if is_sniper else None,
            "s_top_list_score": to_int(row_get(row, "s_top_list_score")) if is_sniper else None,
            "s_news_score": to_int(row_get(row, "s_news_score")) if is_sniper else None,
            "s_base_total": to_int(row_get(row, "s_base_total")) if is_sniper else None,
            "s_dynamic_total": to_int(row_get(row, "s_dynamic_total")) if is_sniper else None,
        }
        for row in rows
    ]
    return PicksResponse(data=items)

@router.get("/kline/{ts_code}", response_model=KlineResponse)
def get_kline(ts_code: str, limit: int = 60, database=Depends(get_prepared_database)):
    sql = """
    SELECT d.trade_date, d.open, d.close, d.low, d.high, d.vol, d.amount, d.pct_chg,
           s.ma5, s.ma20, s.ma60, s.turnover_rate
    FROM t_daily_bar d
    LEFT JOIN t_strategy_daily s
      ON s.ts_code = d.ts_code AND s.trade_date = d.trade_date
    WHERE d.ts_code = %s
    ORDER BY d.trade_date DESC
    LIMIT %s
    """
    rows = database.fetch_all(sql, (ts_code, limit))
    data = [
        {
            "trade_date": row["trade_date"],
            "open": to_float(row_get(row, "open")),
            "close": to_float(row_get(row, "close")),
            "low": to_float(row_get(row, "low")),
            "high": to_float(row_get(row, "high")),
            "vol": to_float(row_get(row, "vol")),
            "amount": to_float(row_get(row, "amount")),
            "pct_chg": to_float(row_get(row, "pct_chg")),
            "turnover_rate": to_float(row_get(row, "turnover_rate")),
            "ma5": to_float(row_get(row, "ma5")),
            "ma20": to_float(row_get(row, "ma20")),
            "ma60": to_float(row_get(row, "ma60")),
        }
        for row in reversed(rows)
    ]
    return KlineResponse(data=data)


@router.get("/detail/{ts_code}", response_model=DetailResponse)
def get_detail(ts_code: str, date: Optional[str] = None, is_sniper: bool = False, database=Depends(get_prepared_database)):
    target_date = date
    table_name = "t_sniper_daily" if is_sniper else "t_strategy_daily"
    if not target_date:
        latest = database.fetch_all(
            f"SELECT MAX(trade_date) AS trade_date FROM {table_name} WHERE ts_code = %s",
            (ts_code,),
        )
        if not latest or not latest[0]["trade_date"]:
            raise HTTPException(status_code=404, detail="stock not found")
        target_date = latest[0]["trade_date"]

    if is_sniper:
        core_sql = """
        SELECT c.cost_50, c.cost_85, c.winner_rate, 
               s.sniper_score as final_score, s.pct_chg, s.turnover_rate, s.volume_ratio,
               s.sniper_score, s.sniper_rejected as rejected, s.sniper_reject_reason as reject_reason,
               s.s_holder_score, s.s_chip_vacuum_score, s.s_ma_state_score,
               s.s_safety_margin_score, s.s_macd_weekly_score, s.s_low_volume_score,
               s.s_golden_pit_score, s.s_ignition_score, s.s_top_list_score,
               s.s_news_score, s.s_base_total, s.s_dynamic_total
        FROM t_sniper_daily s
        LEFT JOIN t_cyq_perf c
          ON c.ts_code = s.ts_code AND c.trade_date = s.trade_date
        WHERE s.ts_code = %s AND s.trade_date = %s
        """
    else:
        core_sql = """
        SELECT c.cost_50, c.cost_85, c.winner_rate, s.float_risk_7d, s.limit_up_20d,
               s.is_limit_up, s.bull_trend,
               s.final_score, s.pct_chg, s.turnover_rate, s.volume_ratio, s.upper_space, s.vol_score,
               s.trend_baseline, s.chip_vacuum, s.kline_body, s.liquidity_base,
               s.safety_margin, s.top_list_3d, s.st_risk, s.rejected, s.reject_reason
        FROM t_strategy_daily s
        LEFT JOIN t_cyq_perf c
          ON c.ts_code = s.ts_code AND c.trade_date = s.trade_date
        WHERE s.ts_code = %s AND s.trade_date = %s
        """
    core_rows = database.fetch_all(core_sql, (ts_code, target_date))
    core = core_rows[0] if core_rows else {}
    
    # 获取股票基本信息
    basic_sql = """
    SELECT name, industry FROM t_stock_basic WHERE ts_code = %s
    """
    basic_rows = database.fetch_all(basic_sql, (ts_code,))
    stock_name = basic_rows[0]["name"] if basic_rows else None
    stock_industry = row_get(basic_rows[0], "industry") if basic_rows else None

    concept_sql = """
    SELECT DISTINCT concept_name
    FROM t_concept_detail
    WHERE ts_code = %s
    ORDER BY concept_name ASC
    """
    concept_rows = database.fetch_all(concept_sql, (ts_code,))
    concept_names = [
        row_get(row, "concept_name")
        for row in concept_rows
        if row_get(row, "concept_name")
    ]

    top_sql = """
    SELECT trade_date, name, net, buy, sell, reason
    FROM t_top_list
    WHERE ts_code = %s
    ORDER BY trade_date DESC, id DESC
    LIMIT 10
    """
    top_rows = database.fetch_all(top_sql, (ts_code,))

    upcoming_float = []
    try:
        base_date = datetime.strptime(target_date, "%Y%m%d")
        end_date = (base_date + timedelta(days=7)).strftime("%Y%m%d")
        float_sql = """
        SELECT ann_date, float_date, float_share, float_ratio, holder_name, share_type
        FROM t_share_float
        WHERE ts_code = %s AND float_date > %s AND float_date <= %s
        ORDER BY float_date ASC
        """
        float_rows = database.fetch_all(float_sql, (ts_code, target_date, end_date))
        upcoming_float = [
            {
                "ann_date": row_get(row, "ann_date"),
                "float_date": row_get(row, "float_date"),
                "float_share": to_float(row_get(row, "float_share")),
                "float_ratio": to_float(row_get(row, "float_ratio")),
                "holder_name": row_get(row, "holder_name"),
                "share_type": row_get(row, "share_type"),
            }
            for row in float_rows
        ]
    except Exception:
        upcoming_float = []

    fin_sql = """
    SELECT ann_date, end_date, debt_to_assets, roe
    FROM t_fin_indicator
    WHERE ts_code = %s
    ORDER BY end_date DESC, ann_date DESC
    LIMIT 1
    """
    fin_rows = database.fetch_all(fin_sql, (ts_code,))
    fin_payload = None
    if fin_rows:
        fin_row = fin_rows[0]
        fin_payload = {
            "ann_date": row_get(fin_row, "ann_date"),
            "end_date": row_get(fin_row, "end_date"),
            "debt_to_assets": to_float(row_get(fin_row, "debt_to_assets")),
            "roe": to_float(row_get(fin_row, "roe")),
        }

    # 获取最近 7 天的爆发右侧评分历史
    history_sql = """
    SELECT trade_date, final_score, pct_chg, turnover_rate, volume_ratio, winner_rate,
           trend_baseline, chip_vacuum, kline_body, liquidity_base, safety_margin,
           top_list_3d, float_risk_7d, is_limit_up, bull_trend, limit_up_20d
    FROM t_strategy_daily
    WHERE ts_code = %s AND trade_date <= %s
    ORDER BY trade_date DESC
    LIMIT 7
    """
    history_rows = database.fetch_all(history_sql, (ts_code, target_date))
    history_7d = [
        {
            "trade_date": row["trade_date"],
            "final_score": to_int(row_get(row, "final_score")),
            "pct_chg": to_float(row_get(row, "pct_chg")),
            "turnover_rate": to_float(row_get(row, "turnover_rate")),
            "volume_ratio": to_float(row_get(row, "volume_ratio")),
            "winner_rate": to_float(row_get(row, "winner_rate")),
            "trend_baseline": to_int(row_get(row, "trend_baseline")),
            "chip_vacuum": to_int(row_get(row, "chip_vacuum")),
            "kline_body": to_int(row_get(row, "kline_body")),
            "liquidity_base": to_int(row_get(row, "liquidity_base")),
            "safety_margin": to_int(row_get(row, "safety_margin")),
            "top_list_3d": to_int(row_get(row, "top_list_3d")),
            "float_risk_7d": to_int(row_get(row, "float_risk_7d")),
            "is_limit_up": to_int(row_get(row, "is_limit_up")),
            "bull_trend": to_int(row_get(row, "bull_trend")),
            "limit_up_20d": to_int(row_get(row, "limit_up_20d")),
        }
        for row in reversed(history_rows)
    ]

    # 获取最近 7 天的极简狙击手评分历史
    sniper_history_sql = """
    SELECT trade_date, sniper_score as final_score, pct_chg, turnover_rate, volume_ratio,
           s_holder_score, s_chip_vacuum_score, s_ma_state_score, s_safety_margin_score, s_macd_weekly_score,
           s_low_volume_score, s_golden_pit_score, s_ignition_score, s_top_list_score, s_news_score,
           s_base_total, s_dynamic_total, sniper_rejected as rejected, sniper_reject_reason as reject_reason
    FROM t_sniper_daily
    WHERE ts_code = %s AND trade_date <= %s
    ORDER BY trade_date DESC
    LIMIT 7
    """
    sniper_history_rows = database.fetch_all(sniper_history_sql, (ts_code, target_date))
    sniper_history_7d = [
        {
            "trade_date": row["trade_date"],
            "final_score": to_int(row_get(row, "final_score")),
            "pct_chg": to_float(row_get(row, "pct_chg")),
            "turnover_rate": to_float(row_get(row, "turnover_rate")),
            "volume_ratio": to_float(row_get(row, "volume_ratio")),
            "sniper_score": to_int(row_get(row, "final_score")),
            "sniper_rejected": to_int(row_get(row, "rejected")),
            "sniper_reject_reason": row_get(row, "reject_reason"),
            "s_holder_score": to_int(row_get(row, "s_holder_score")),
            "s_chip_vacuum_score": to_int(row_get(row, "s_chip_vacuum_score")),
            "s_ma_state_score": to_int(row_get(row, "s_ma_state_score")),
            "s_safety_margin_score": to_int(row_get(row, "s_safety_margin_score")),
            "s_macd_weekly_score": to_int(row_get(row, "s_macd_weekly_score")),
            "s_low_volume_score": to_int(row_get(row, "s_low_volume_score")),
            "s_golden_pit_score": to_int(row_get(row, "s_golden_pit_score")),
            "s_ignition_score": to_int(row_get(row, "s_ignition_score")),
            "s_top_list_score": to_int(row_get(row, "s_top_list_score")),
            "s_news_score": to_int(row_get(row, "s_news_score")),
            "s_base_total": to_int(row_get(row, "s_base_total")),
            "s_dynamic_total": to_int(row_get(row, "s_dynamic_total")),
        }
        for row in reversed(sniper_history_rows)
    ]

    return DetailResponse(
        data=DetailPayload(
            ts_code=ts_code,
            name=stock_name,
            industry=stock_industry,
            concept_names=concept_names,
            concept_text=" / ".join(concept_names),
            trade_date=target_date,
            cost_50=to_float(core.get("cost_50")),
            cost_85=to_float(core.get("cost_85")),
            winner_rate=to_float(core.get("winner_rate")),
            float_risk_7d=to_int(core.get("float_risk_7d")) if not is_sniper else None,
            limit_up_20d=to_int(core.get("limit_up_20d")) if not is_sniper else None,
            is_limit_up=to_int(core.get("is_limit_up")) if not is_sniper else None,
            bull_trend=to_int(core.get("bull_trend")) if not is_sniper else None,
            final_score=to_int(core.get("final_score")),
            pct_chg=to_float(core.get("pct_chg")),
            turnover_rate=to_float(core.get("turnover_rate")),
            volume_ratio=to_float(core.get("volume_ratio")),
            upper_space=to_float(core.get("upper_space")) if not is_sniper else None,
            vol_score=to_float(core.get("vol_score")) if not is_sniper else None,
            trend_baseline=to_int(core.get("trend_baseline")) if not is_sniper else None,
            chip_vacuum=to_int(core.get("chip_vacuum")) if not is_sniper else None,
            kline_body=to_int(core.get("kline_body")) if not is_sniper else None,
            liquidity_base=to_int(core.get("liquidity_base")) if not is_sniper else None,
            safety_margin=to_int(core.get("safety_margin")) if not is_sniper else None,
            top_list_3d=to_int(core.get("top_list_3d")) if not is_sniper else None,
            st_risk=to_int(core.get("st_risk")) if not is_sniper else None,
            rejected=to_int(core.get("rejected")),
            reject_reason=row_get(core, "reject_reason"),
            top_list=[
                {
                    "trade_date": row_get(row, "trade_date"),
                    "name": row_get(row, "name"),
                    "net": to_float(row_get(row, "net")),
                    "buy": to_float(row_get(row, "buy")),
                    "sell": to_float(row_get(row, "sell")),
                    "reason": row_get(row, "reason"),
                }
                for row in top_rows
            ],
            upcoming_float=upcoming_float,
            fin_indicator=fin_payload,
            history_7d=history_7d,
            sniper_history_7d=sniper_history_7d,
            # Sniper fields
            sniper_score=to_int(core.get("sniper_score")) if is_sniper else None,
            sniper_rejected=to_int(core.get("sniper_rejected")) if is_sniper else None,
            sniper_reject_reason=row_get(core, "sniper_reject_reason") if is_sniper else None,
            s_holder_score=to_int(core.get("s_holder_score")) if is_sniper else None,
            s_chip_vacuum_score=to_int(core.get("s_chip_vacuum_score")) if is_sniper else None,
            s_ma_state_score=to_int(core.get("s_ma_state_score")) if is_sniper else None,
            s_safety_margin_score=to_int(core.get("s_safety_margin_score")) if is_sniper else None,
            s_macd_weekly_score=to_int(core.get("s_macd_weekly_score")) if is_sniper else None,
            s_low_volume_score=to_int(core.get("s_low_volume_score")) if is_sniper else None,
            s_golden_pit_score=to_int(core.get("s_golden_pit_score")) if is_sniper else None,
            s_ignition_score=to_int(core.get("s_ignition_score")) if is_sniper else None,
            s_top_list_score=to_int(core.get("s_top_list_score")) if is_sniper else None,
            s_news_score=to_int(core.get("s_news_score")) if is_sniper else None,
            s_base_total=to_int(core.get("s_base_total")) if is_sniper else None,
            s_dynamic_total=to_int(core.get("s_dynamic_total")) if is_sniper else None,
        )
    )



@router.post("/stocks/batch-search", response_model=BatchSearchResponse)
def batch_search(payload: BatchSearchRequest, database=Depends(get_prepared_database)):
    queries = [q.strip() for q in payload.queries if q.strip()]
    if not queries:
        return BatchSearchResponse(data=BatchSearchPayload(items=[]))
    
    conditions = []
    params = []
    for q in set(queries):
        if q.isdigit():
            conditions.append("(ts_code LIKE %s)")
            params.append(f"%{q}%")
        else:
            conditions.append("(name = %s OR ts_code LIKE %s)")
            params.extend([q, f"%{q}%"])
            
    if not conditions:
        return BatchSearchResponse(data=BatchSearchPayload(items=[]))
        
    sql = f"""
    SELECT ts_code, name, industry
    FROM t_stock_basic
    WHERE {' OR '.join(conditions)}
    LIMIT 100
    """
    rows = database.fetch_all(sql, params)
    
    items = []
    for row in rows:
        ts_code = row["ts_code"]
        c_sql = "SELECT concept_name FROM t_concept_detail WHERE ts_code = %s"
        c_rows = database.fetch_all(c_sql, (ts_code,))
        concept_names = [row_get(cr, "concept_name") for cr in c_rows if row_get(cr, "concept_name")]
        
        items.append({
            "ts_code": ts_code,
            "name": row["name"],
            "industry": row_get(row, "industry"),
            "concept_names": concept_names,
            "concept_text": " / ".join(concept_names) if concept_names else ""
        })
        
    return BatchSearchResponse(data=BatchSearchPayload(items=items))


@router.get("/data-health")
def get_data_health(database=Depends(get_prepared_database)):
    return {"code": 200, "msg": "success", "data": build_data_health_report(database)}


def _count_scalar(database, sql: str, params: tuple[object, ...] = ()) -> int:
    rows = database.fetch_all(sql, params)
    if not rows:
        return 0
    row = rows[0]
    value = row_get(row, "count_value")
    if value is None:
        value = next(iter(row.values())) if isinstance(row, dict) and row else 0
    return int(value or 0)


def _executemany(database, sql: str, rows: list[tuple[object, ...]]) -> int:
    if not rows:
        return 0
    if hasattr(database, "_connection_scope"):
        prepared_sql = database.prepare_sql(sql)
        with database._connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.executemany(prepared_sql, rows)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()
        return len(rows)
    for row in rows:
        database.execute(sql, row)
    return len(rows)


def _backfill_volume_ratio(database) -> dict[str, Any]:
    before_daily_basic = _count_scalar(
        database,
        "SELECT COUNT(1) AS count_value FROM t_daily_basic WHERE volume_ratio IS NULL",
    )
    candidates = database.fetch_all(
        """
        SELECT b.ts_code, b.trade_date, d.vol
        FROM t_daily_basic b
        JOIN t_daily_bar d ON d.ts_code = b.ts_code AND d.trade_date = b.trade_date
        WHERE b.volume_ratio IS NULL
          AND d.vol IS NOT NULL
        """
    )
    updates: list[tuple[object, ...]] = []
    if candidates:
        trade_dates = [str(row_get(row, "trade_date")) for row in candidates if row_get(row, "trade_date")]
        ts_codes = sorted({str(row_get(row, "ts_code")) for row in candidates if row_get(row, "ts_code")})
        try:
            lower_bound = (datetime.strptime(min(trade_dates), "%Y%m%d") - timedelta(days=90)).strftime("%Y%m%d")
        except Exception:
            lower_bound = min(trade_dates)
        upper_bound = max(trade_dates)

        rows_by_code: dict[str, list[dict[str, Any]]] = {}
        for index in range(0, len(ts_codes), 500):
            batch = ts_codes[index:index + 500]
            placeholders = ", ".join(["%s"] * len(batch))
            rows = database.fetch_all(
                f"""
                SELECT ts_code, trade_date, vol
                FROM t_daily_bar
                WHERE ts_code IN ({placeholders})
                  AND trade_date >= %s
                  AND trade_date <= %s
                ORDER BY ts_code, trade_date ASC
                """,
                tuple(batch + [lower_bound, upper_bound]),
            )
            for row in rows:
                rows_by_code.setdefault(str(row_get(row, "ts_code")), []).append(row)

        index_by_key: dict[tuple[str, str], int] = {}
        for ts_code, series in rows_by_code.items():
            for index, row in enumerate(series):
                index_by_key[(ts_code, str(row_get(row, "trade_date")))] = index

        for row in candidates:
            ts_code = str(row_get(row, "ts_code"))
            trade_date = str(row_get(row, "trade_date"))
            series = rows_by_code.get(ts_code) or []
            current_index = index_by_key.get((ts_code, trade_date))
            if current_index is None:
                continue
            try:
                current_vol = float(row_get(series[current_index], "vol"))
            except (TypeError, ValueError):
                continue
            previous_volumes: list[float] = []
            for item in reversed(series[:current_index]):
                if len(previous_volumes) >= 5:
                    break
                try:
                    previous_vol = float(row_get(item, "vol"))
                except (TypeError, ValueError):
                    continue
                if previous_vol > 0:
                    previous_volumes.append(previous_vol)
            if len(previous_volumes) < 5:
                continue
            avg_volume = sum(previous_volumes) / len(previous_volumes)
            if avg_volume <= 0:
                continue
            updates.append((round(current_vol / avg_volume, 4), ts_code, trade_date))

    updated_daily_basic = _executemany(
        database,
        """
        UPDATE t_daily_basic
        SET volume_ratio = %s
        WHERE ts_code = %s
          AND trade_date = %s
          AND volume_ratio IS NULL
        """,
        updates,
    )
    before_strategy = _count_scalar(
        database,
        """
        SELECT COUNT(1) AS count_value
        FROM t_strategy_daily s
        WHERE s.volume_ratio IS NULL
          AND EXISTS (
              SELECT 1 FROM t_daily_basic b
              WHERE b.ts_code = s.ts_code
                AND b.trade_date = s.trade_date
                AND b.volume_ratio IS NOT NULL
          )
        """,
    )
    before_sniper = _count_scalar(
        database,
        """
        SELECT COUNT(1) AS count_value
        FROM t_sniper_daily s
        WHERE s.volume_ratio IS NULL
          AND EXISTS (
              SELECT 1 FROM t_daily_basic b
              WHERE b.ts_code = s.ts_code
                AND b.trade_date = s.trade_date
                AND b.volume_ratio IS NOT NULL
          )
        """,
    )
    for table_name in ("t_strategy_daily", "t_sniper_daily"):
        database.execute(
            f"""
            UPDATE {table_name}
            SET volume_ratio = (
                SELECT b.volume_ratio
                FROM t_daily_basic b
                WHERE b.ts_code = {table_name}.ts_code
                  AND b.trade_date = {table_name}.trade_date
            )
            WHERE volume_ratio IS NULL
              AND EXISTS (
                  SELECT 1 FROM t_daily_basic b
                  WHERE b.ts_code = {table_name}.ts_code
                    AND b.trade_date = {table_name}.trade_date
                    AND b.volume_ratio IS NOT NULL
              )
            """
        )
    after_daily_basic = _count_scalar(
        database,
        "SELECT COUNT(1) AS count_value FROM t_daily_basic WHERE volume_ratio IS NULL",
    )
    return {
        "target": "volume_ratio",
        "daily_basic_null_before": before_daily_basic,
        "daily_basic_null_after": after_daily_basic,
        "daily_basic_filled": max(before_daily_basic - after_daily_basic, 0),
        "daily_basic_updates_attempted": updated_daily_basic,
        "strategy_synced": before_strategy,
        "sniper_synced": before_sniper,
    }


def _backfill_premium(database) -> dict[str, Any]:
    before_null = _count_scalar(
        database,
        "SELECT COUNT(1) AS count_value FROM t_block_trade WHERE premium IS NULL",
    )
    database.execute(
        """
        UPDATE t_block_trade
        SET premium = ROUND(
            (price - (
                SELECT d.close
                FROM t_daily_bar d
                WHERE d.ts_code = t_block_trade.ts_code
                  AND d.trade_date = t_block_trade.trade_date
            )) / (
                SELECT d.close
                FROM t_daily_bar d
                WHERE d.ts_code = t_block_trade.ts_code
                  AND d.trade_date = t_block_trade.trade_date
            ) * 100.0,
            4
        )
        WHERE premium IS NULL
          AND price IS NOT NULL
          AND EXISTS (
              SELECT 1
              FROM t_daily_bar d
              WHERE d.ts_code = t_block_trade.ts_code
                AND d.trade_date = t_block_trade.trade_date
                AND d.close IS NOT NULL
                AND d.close > 0
          )
        """
    )
    after_null = _count_scalar(
        database,
        "SELECT COUNT(1) AS count_value FROM t_block_trade WHERE premium IS NULL",
    )
    eligible_sniper = _count_scalar(
        database,
        """
        SELECT COUNT(1) AS count_value
        FROM t_sniper_daily s
        WHERE COALESCE(s.sniper_rejected, 0) = 0
          AND COALESCE(s.s_top_list_score, 0) < 4
          AND EXISTS (
              SELECT 1
              FROM t_block_trade b
              WHERE b.ts_code = s.ts_code
                AND b.trade_date = s.trade_date
                AND b.premium > 0
          )
        """,
    )
    database.execute(
        """
        UPDATE t_sniper_daily
        SET
          sniper_score = COALESCE(sniper_score, 0) + (4 - COALESCE(s_top_list_score, 0)),
          s_dynamic_total = COALESCE(s_dynamic_total, 0) + (4 - COALESCE(s_top_list_score, 0)),
          s_top_list_score = 4
        WHERE COALESCE(sniper_rejected, 0) = 0
          AND COALESCE(s_top_list_score, 0) < 4
          AND EXISTS (
              SELECT 1
              FROM t_block_trade b
              WHERE b.ts_code = t_sniper_daily.ts_code
                AND b.trade_date = t_sniper_daily.trade_date
                AND b.premium > 0
          )
        """
    )
    return {
        "target": "premium",
        "block_trade_null_before": before_null,
        "block_trade_null_after": after_null,
        "block_trade_filled": max(before_null - after_null, 0),
        "sniper_scored": eligible_sniper,
    }


@router.post("/data-health/backfill/{target}")
def backfill_data_health_field(target: str, database=Depends(get_prepared_database)):
    if target == "volume_ratio":
        data = _backfill_volume_ratio(database)
    elif target == "premium":
        data = _backfill_premium(database)
    else:
        raise HTTPException(status_code=400, detail="target must be one of: volume_ratio, premium")
    data["health"] = build_data_health_report(database)
    return {"code": 200, "msg": "success", "data": data}


@router.post("/analysis/stock_advice", response_model=StockAdviceResponse)
def stock_advice(payload: StockAdviceRequest, database=Depends(get_prepared_database)):
    advice = generate_stock_advice(database, load_config().ai, payload.symbol, payload.market)
    return StockAdviceResponse(
        data=StockAdvicePayload(
            symbol=advice["symbol"],
            current_price=advice["current_price"],
            advice_markdown=advice["advice_markdown"],
            risk_warning=advice["risk_warning"],
            analysis_mode=advice.get("analysis_mode"),
            analysis_meta=advice.get("analysis_meta"),
        )
    )


@router.get("/job/stages", response_model=JobStageMetricsResponse)
def get_job_stage_metrics(
    job_name: Optional[str] = None,
    run_id: Optional[int] = None,
    limit: int = 200,
    days: int = 7,
    status: Optional[str] = None,
):
    safe_limit = max(1, min(limit, 1000))
    safe_days = max(1, min(days, 90))
    normalized_status = str(status).strip().lower() if status else None
    if normalized_status and normalized_status not in {"running", "success", "failed", "unknown"}:
        raise HTTPException(status_code=400, detail="status must be one of: running, success, failed, unknown")
    payload = build_job_stage_metrics(
        days=safe_days,
        limit=safe_limit,
        job_name=job_name,
        run_id=run_id,
        status=normalized_status,
    )
    return JobStageMetricsResponse(data=JobStageMetricsPayload(items=payload["items"], summary=payload["summary"]))


@router.get("/job/logs/summary", response_model=JobLogReportResponse)
def get_job_log_summary(days: int = 7, limit: int = 10, job_name: Optional[str] = None):
    safe_days = max(1, min(days, 90))
    safe_limit = max(1, min(limit, 50))
    report = build_job_log_report(days=safe_days, limit=safe_limit, job_name=job_name)
    return JobLogReportResponse(data=JobLogReportPayload(**report))


@router.get("/job/runs", response_model=JobRunsResponse)
def get_job_runs(days: int = 7, limit: int = 20, job_name: Optional[str] = None, status: Optional[str] = None):
    safe_days = max(1, min(days, 90))
    safe_limit = max(1, min(limit, 100))
    normalized_status = str(status).strip().lower() if status else None
    if normalized_status and normalized_status not in {"running", "success", "failed", "unknown"}:
        raise HTTPException(status_code=400, detail="status must be one of: running, success, failed, unknown")
    payload = list_job_runs(
        days=safe_days,
        limit=safe_limit,
        job_name=job_name,
        status=normalized_status,
    )
    return JobRunsResponse(data=JobRunsPayload(**payload))


@router.get("/jobs/tushare-latest")
def check_tushare_latest():
    try:
        from backend.app.config import load_config
        from backend.app.runtime import build_client
        import os
        from datetime import date, timedelta
        
        is_desktop = os.environ.get("APP_ENV") == "desktop"
        config_file = "config.desktop.yaml" if is_desktop else "config.yaml"
        config_path = os.path.join(os.getcwd(), config_file)
        if not os.path.exists(config_path):
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), config_file)
        config = load_config(config_path)
        client = build_client(config)
        
        end = date.today()
        start = end - timedelta(days=20)
        cal_params = {'start_date': start.strftime('%Y%m%d'), 'end_date': end.strftime('%Y%m%d')}
        cal_res = client.query('trade_cal', ['cal_date', 'is_open'], params=cal_params)
        cal_records = cal_res.to_dicts()
        trade_dates = sorted([r['cal_date'] for r in cal_records if r.get('is_open') == 1])
        
        for candidate in reversed(trade_dates):
            daily_res = client.query('daily', ['ts_code', 'trade_date'], params={'trade_date': candidate})
            if len(daily_res.to_dicts()) > 0:
                return {"code": 200, "msg": "success", "data": {"latest_date": candidate}}
                
        return {"code": 200, "msg": "success", "data": {"latest_date": None}}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/jobs/definitions")
def get_manual_job_definitions():
    return {"code": 200, "msg": "success", "data": {"items": list_job_definitions()}}


@router.get("/jobs/tasks")
def get_manual_job_tasks(database=Depends(get_prepared_database)):
    items = list_manual_tasks()
    latest_date = None
    try:
        latest = database.fetch_all("SELECT MAX(trade_date) AS td FROM t_daily_bar")
        if latest and latest[0]["td"]:
            latest_date = latest[0]["td"]
    except Exception:
        pass
    return {"code": 200, "msg": "success", "data": {"items": items, "latest_trade_date": latest_date}}


@router.post("/jobs/history/run")
def start_history_job(payload: HistoryJobRunRequest):
    try:
        start_dt = datetime.strptime(payload.start_date, "%Y%m%d")
        end_dt = datetime.strptime(payload.end_date, "%Y%m%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="date must be valid YYYYMMDD") from exc
    if start_dt > end_dt:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")
    args = [payload.start_date, payload.end_date]
    if payload.force:
        args.append("--force")
    try:
        task = run_manual_job("history", args=args)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"code": 200, "msg": "success", "data": {"task": task.__dict__}}


@router.post("/jobs/daily-date/run")
def start_daily_date_job(payload: DailyDateJobRunRequest):
    try:
        datetime.strptime(payload.trade_date, "%Y%m%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="trade_date must be valid YYYYMMDD") from exc
    try:
        task = run_manual_job("update_date", args=[payload.trade_date])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"code": 200, "msg": "success", "data": {"task": task.__dict__}}


@router.post("/jobs/{job_name}/run")
def start_manual_job(job_name: str):
    try:
        task = run_manual_job(job_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"code": 200, "msg": "success", "data": {"task": task.__dict__}}


@router.get("/tushare-token")
def get_tushare_token_status():
    return {"code": 200, "msg": "success", "data": get_desktop_tushare_status()}


@router.put("/tushare-token")
def update_tushare_token(payload: TushareTokenUpdateRequest):
    try:
        data = save_desktop_tushare_token(payload.token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"code": 200, "msg": "success", "data": data}


@router.get("/job/tables/trends", response_model=JobTableTrendResponse)
def get_job_table_trends(days: int = 7, limit: int = 20, job_name: Optional[str] = None):
    safe_days = max(1, min(days, 90))
    safe_limit = max(1, min(limit, 100))
    payload = summarize_table_trends(days=safe_days, limit=safe_limit, job_name=job_name)
    return JobTableTrendResponse(data=JobTableTrendPayload(**payload))


@router.get("/job/failures/trends", response_model=JobFailureTrendResponse)
def get_job_failure_trends(days: int = 7, job_name: Optional[str] = None):
    safe_days = max(1, min(days, 90))
    payload = summarize_failure_trends(days=safe_days, job_name=job_name)
    return JobFailureTrendResponse(data=JobFailureTrendPayload(**payload))


@router.get("/job/failures/{run_id}", response_model=JobFailureDetailResponse)
def get_job_failure(run_id: int):
    try:
        payload = get_job_failure_detail(run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JobFailureDetailResponse(data=JobFailureDetailPayload(**payload))


@router.get("/runtime-config", response_model=RuntimeConfigResponse)
def get_runtime_config(database=Depends(get_prepared_database)):
    jobs = get_runtime_jobs_config(database)
    return RuntimeConfigResponse(data=RuntimeConfigPayload(jobs=jobs))


@router.put("/runtime-config", response_model=RuntimeConfigResponse)
def update_runtime_config(payload: RuntimeConfigUpdateRequest, database=Depends(get_prepared_database)):
    try:
        jobs = set_runtime_jobs_config(database, payload.jobs or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RuntimeConfigResponse(data=RuntimeConfigPayload(jobs=jobs))


@router.post("/ambush", response_model=ApiResponse)
def add_to_ambush_pool(payload: AmbushPoolCreate, database=Depends(get_prepared_database)):
    """添加股票到埋伏池"""
    # 检查股票是否存在
    stock = database.fetch_one(
        "SELECT ts_code FROM t_stock_basic WHERE ts_code = %s",
        (payload.ts_code,)
    )
    if not stock:
        raise HTTPException(status_code=404, detail="股票代码不存在")
    
    # 检查是否已在埋伏池中
    existing = database.fetch_one(
        "SELECT ts_code FROM t_ambush_pool WHERE ts_code = %s",
        (payload.ts_code,)
    )
    if existing:
        raise HTTPException(status_code=409, detail="该股票已在埋伏池中")
    
    add_date = payload.add_date or datetime.now().strftime("%Y%m%d")
    database.execute(
        """INSERT INTO t_ambush_pool (ts_code, expected_logic, add_date, status)
           VALUES (%s, %s, %s, %s)""",
        (payload.ts_code, payload.expected_logic, add_date, payload.status)
    )
    return ApiResponse(msg="添加成功")


@router.put("/ambush/{ts_code}", response_model=ApiResponse)
def update_ambush_pool(ts_code: str, payload: AmbushPoolUpdate, database=Depends(get_prepared_database)):
    """更新埋伏池中的股票信息"""
    existing = database.fetch_one(
        "SELECT ts_code FROM t_ambush_pool WHERE ts_code = %s",
        (ts_code,)
    )
    if not existing:
        raise HTTPException(status_code=404, detail="该股票不在埋伏池中")
    
    updates = []
    params = []
    if payload.expected_logic is not None:
        updates.append("expected_logic = %s")
        params.append(payload.expected_logic)
    if payload.status is not None:
        updates.append("status = %s")
        params.append(payload.status)
    
    if updates:
        params.append(ts_code)
        database.execute(
            f"UPDATE t_ambush_pool SET {', '.join(updates)} WHERE ts_code = %s",
            params
        )
    return ApiResponse(msg="更新成功")
