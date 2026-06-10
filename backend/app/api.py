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





@router.get("/picks", response_model=PicksResponse)
def get_picks(date: Optional[str] = None, is_ambush: bool = False, database=Depends(get_prepared_database)):
    target_date = date
    if not target_date:
        latest = database.fetch_all("SELECT MAX(trade_date) AS trade_date FROM t_strategy_daily")
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
                   (COALESCE(s.liquidity_base, 0) = 1 OR COALESCE(s.kline_body, 0) = 1) AS is_action_triggered
            FROM t_ambush_pool a
            LEFT JOIN t_strategy_daily s ON s.ts_code = a.ts_code AND s.trade_date = %s
            LEFT JOIN t_stock_basic b ON b.ts_code = a.ts_code
            WHERE a.status = 1
            ORDER BY is_action_triggered DESC, s.chip_vacuum DESC, s.safety_margin DESC
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
                   s.safety_margin, s.top_list_3d, s.st_risk, s.rejected, s.reject_reason
            FROM t_strategy_daily s
            LEFT JOIN t_stock_basic b ON b.ts_code = s.ts_code
            WHERE s.trade_date = %s
            ORDER BY s.final_score DESC, s.ts_code ASC
            """,
            (target_date,),
        )
    
    concept_map: dict[str, list[str]] = {}
    if rows:
        concept_sql = """
        SELECT DISTINCT c.ts_code, c.concept_name
        FROM t_concept_detail c
        INNER JOIN t_strategy_daily s ON s.ts_code = c.ts_code
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
            "winner_rate": to_float(row_get(row, "winner_rate")),
            "upper_space": to_float(row_get(row, "upper_space")),
            "vol_score": to_float(row_get(row, "vol_score")),
            "final_score": to_int(row_get(row, "final_score")),
            # v1.1 新增字段
            "trend_baseline": to_int(row_get(row, "trend_baseline")),
            "chip_vacuum": to_int(row_get(row, "chip_vacuum")),
            "kline_body": to_int(row_get(row, "kline_body")),
            "liquidity_base": to_int(row_get(row, "liquidity_base")),
            "safety_margin": to_int(row_get(row, "safety_margin")),
            "top_list_3d": to_int(row_get(row, "top_list_3d")),
            "st_risk": to_int(row_get(row, "st_risk")),
            "rejected": to_int(row_get(row, "rejected")),
            "reject_reason": row_get(row, "reject_reason"),
            # v1.2 新增：埋伏池相关动态字段
            "is_action_triggered": bool(row_get(row, "is_action_triggered")) if is_ambush else False,
            "ambush_add_date": row_get(row, "ambush_add_date") if is_ambush else None,
            "expected_logic": row_get(row, "expected_logic") if is_ambush else None,
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
def get_detail(ts_code: str, date: Optional[str] = None, database=Depends(get_prepared_database)):
    target_date = date
    if not target_date:
        latest = database.fetch_all(
            "SELECT MAX(trade_date) AS trade_date FROM t_strategy_daily WHERE ts_code = %s",
            (ts_code,),
        )
        if not latest or not latest[0]["trade_date"]:
            raise HTTPException(status_code=404, detail="stock not found")
        target_date = latest[0]["trade_date"]

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
            float_risk_7d=to_int(core.get("float_risk_7d")),
            limit_up_20d=to_int(core.get("limit_up_20d")),
            is_limit_up=to_int(core.get("is_limit_up")),
            bull_trend=to_int(core.get("bull_trend")),
            final_score=to_int(core.get("final_score")),
            pct_chg=to_float(core.get("pct_chg")),
            turnover_rate=to_float(core.get("turnover_rate")),
            volume_ratio=to_float(core.get("volume_ratio")),
            upper_space=to_float(core.get("upper_space")),
            vol_score=to_float(core.get("vol_score")),
            trend_baseline=to_int(core.get("trend_baseline")),
            chip_vacuum=to_int(core.get("chip_vacuum")),
            kline_body=to_int(core.get("kline_body")),
            liquidity_base=to_int(core.get("liquidity_base")),
            safety_margin=to_int(core.get("safety_margin")),
            top_list_3d=to_int(core.get("top_list_3d")),
            st_risk=to_int(core.get("st_risk")),
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


@router.get("/jobs/definitions")
def get_manual_job_definitions():
    return {"code": 200, "msg": "success", "data": {"items": list_job_definitions()}}


@router.get("/jobs/tasks")
def get_manual_job_tasks():
    return {"code": 200, "msg": "success", "data": {"items": list_manual_tasks()}}


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
