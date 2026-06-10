from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    code: int = 200
    msg: str = "success"


class PickItem(BaseModel):
    ts_code: str
    name: Optional[str] = None
    industry: Optional[str] = None
    concept_names: List[str] = Field(default_factory=list)
    concept_text: Optional[str] = None
    trade_date: Optional[str] = None
    pct_chg: Optional[float] = None
    turnover_rate: Optional[float] = None
    volume_ratio: Optional[float] = None
    winner_rate: Optional[float] = None
    upper_space: Optional[float] = None
    vol_score: Optional[float] = None
    final_score: Optional[int] = None
    trend_baseline: Optional[int] = None
    chip_vacuum: Optional[int] = None
    kline_body: Optional[int] = None
    liquidity_base: Optional[int] = None
    safety_margin: Optional[int] = None
    top_list_3d: Optional[int] = None
    st_risk: Optional[int] = None
    rejected: Optional[int] = None
    reject_reason: Optional[str] = None
    # v1.2 新增：埋伏池相关动态字段
    is_action_triggered: Optional[bool] = Field(False, description="是否触发异动（量能活跃或K线实体达标）")
    ambush_add_date: Optional[str] = Field(None, description="加入埋伏池的日期")
    expected_logic: Optional[str] = Field(None, description="埋伏预期逻辑")


class PicksResponse(ApiResponse):
    data: List[PickItem]


class KlineItem(BaseModel):
    trade_date: str
    open: Optional[float] = None
    close: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    vol: Optional[float] = None
    amount: Optional[float] = None
    pct_chg: Optional[float] = None
    turnover_rate: Optional[float] = None
    ma5: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None


class KlineResponse(ApiResponse):
    data: List[KlineItem]


class DetailPayload(BaseModel):
    ts_code: str
    name: Optional[str] = None
    industry: Optional[str] = None
    concept_names: List[str] = Field(default_factory=list)
    concept_text: Optional[str] = None
    trade_date: Optional[str] = None
    cost_50: Optional[float] = None
    cost_85: Optional[float] = None
    winner_rate: Optional[float] = None
    float_risk_7d: Optional[int] = None
    limit_up_20d: Optional[int] = None
    is_limit_up: Optional[int] = None
    bull_trend: Optional[int] = None
    # 策略相关字段
    final_score: Optional[int] = None
    pct_chg: Optional[float] = None
    turnover_rate: Optional[float] = None
    volume_ratio: Optional[float] = None
    upper_space: Optional[float] = None
    vol_score: Optional[float] = None
    # v1.1 新增字段
    trend_baseline: Optional[int] = None
    chip_vacuum: Optional[int] = None
    kline_body: Optional[int] = None
    liquidity_base: Optional[int] = None
    safety_margin: Optional[int] = None
    top_list_3d: Optional[int] = None
    st_risk: Optional[int] = None
    rejected: Optional[int] = None
    reject_reason: Optional[str] = None
    top_list: List[dict]
    upcoming_float: List[dict]
    fin_indicator: Optional[dict] = None


class DetailResponse(ApiResponse):
    data: DetailPayload


class StockAdviceRequest(BaseModel):
    symbol: str
    market: str = "CN"


class StockAdvicePayload(BaseModel):
    symbol: str
    current_price: Optional[float] = None
    advice_markdown: str
    risk_warning: str
    analysis_mode: Optional[str] = None
    analysis_meta: Optional[dict[str, Any]] = None


class StockAdviceResponse(ApiResponse):
    data: StockAdvicePayload


class BatchSearchRequest(BaseModel):
    queries: List[str]


class BatchSearchResultItem(BaseModel):
    ts_code: str
    name: str
    industry: Optional[str] = None
    concept_names: List[str] = Field(default_factory=list)
    concept_text: Optional[str] = None


class BatchSearchPayload(BaseModel):
    items: List[BatchSearchResultItem]


class BatchSearchResponse(ApiResponse):
    data: BatchSearchPayload


class JobStageItem(BaseModel):
    id: int
    run_id: Optional[int] = None
    job_name: str
    stage_name: str
    status: str
    duration_ms: int
    created_at: Optional[str] = None
    extra: dict[str, Any]
    message: Optional[str] = None


class JobStageSummaryItem(BaseModel):
    stage_name: str
    total_count: int
    failed_count: int
    total_duration_ms: int
    avg_duration_ms: float
    max_duration_ms: int


class JobStageMetricsPayload(BaseModel):
    items: List[JobStageItem]
    summary: List[JobStageSummaryItem]


class JobStageMetricsResponse(ApiResponse):
    data: JobStageMetricsPayload


class JobLogRunItem(BaseModel):
    run_id: int
    job_name: Optional[str] = None
    run_mode: Optional[str] = None
    target_range: Optional[str] = None
    max_workers: Optional[int] = None
    timeout_seconds: Optional[int] = None
    started_ts: Optional[int] = None
    started_at: Optional[str] = None
    finished_ts: Optional[int] = None
    finished_at: Optional[str] = None
    status: str
    timed_out: bool = False
    duration_seconds: Optional[int] = None
    message: Optional[str] = None


class JobLogStageSummaryItem(BaseModel):
    stage_name: str
    count: int
    failed_count: int
    total_duration_ms: int
    avg_duration_ms: float
    max_duration_ms: int
    latest_status: str
    latest_run_id: int
    latest_at: Optional[str] = None


class JobLogTableItem(BaseModel):
    table_name: str
    fetched_rows: int
    status: str
    missing_fields: List[str]
    null_fields: dict[str, Any]
    metrics: dict[str, Any] = {}
    message: Optional[str] = None
    logged_at: Optional[str] = None


class JobLogReportPayload(BaseModel):
    log_dir: str
    generated_at: str
    window_days: int
    job_name: Optional[str] = None
    latest_run: Optional[JobLogRunItem] = None
    recent_failures: List[JobLogRunItem]
    stage_summary: List[JobLogStageSummaryItem]
    status_counts: dict[str, int]
    latest_run_tables: List[JobLogTableItem]


class JobLogReportResponse(ApiResponse):
    data: JobLogReportPayload


class JobRunsPayload(BaseModel):
    log_dir: str
    generated_at: str
    window_days: int
    job_name: Optional[str] = None
    status: Optional[str] = None
    items: List[JobLogRunItem]
    total: int


class JobRunsResponse(ApiResponse):
    data: JobRunsPayload


class JobFailureStageItem(BaseModel):
    stage_name: str
    status: str
    duration_ms: int
    message: Optional[str] = None
    logged_at: Optional[str] = None
    extra: dict[str, Any]


class JobFailureTableItem(BaseModel):
    table_name: str
    fetched_rows: int
    status: str
    message: Optional[str] = None
    missing_fields: List[str]
    null_fields: dict[str, Any]
    metrics: dict[str, Any] = {}
    logged_at: Optional[str] = None


class JobFailureDetailPayload(BaseModel):
    log_dir: str
    generated_at: str
    run: JobLogRunItem
    failed_stages: List[JobFailureStageItem]
    failed_tables: List[JobFailureTableItem]
    recent_failures: List[JobLogRunItem]


class JobFailureDetailResponse(ApiResponse):
    data: JobFailureDetailPayload


class JobTableTrendItem(BaseModel):
    table_name: str
    run_count: int
    failed_count: int
    total_rows: int
    avg_rows: float
    max_rows: int
    total_null_field_count: int
    latest_run_id: int
    latest_at: Optional[str] = None
    latest_status: str
    latest_message: Optional[str] = None
    latest_null_fields: dict[str, Any]
    latest_metrics: dict[str, Any] = {}


class JobTableTrendPayload(BaseModel):
    log_dir: str
    generated_at: str
    window_days: int
    job_name: Optional[str] = None
    items: List[JobTableTrendItem]
    total: int


class JobTableTrendResponse(ApiResponse):
    data: JobTableTrendPayload


class JobFailureTrendDayItem(BaseModel):
    date: str
    total_runs: int
    failed_runs: int
    failure_rate: float


class JobFailureTrendJobItem(BaseModel):
    job_name: str
    total_runs: int
    failed_runs: int
    failure_rate: float
    latest_status: str
    latest_run_id: int
    latest_at: Optional[str] = None


class JobFailureTrendPayload(BaseModel):
    log_dir: str
    generated_at: str
    window_days: int
    job_name: Optional[str] = None
    current_failure_streak: int
    max_failure_streak: int
    latest_failure: Optional[JobLogRunItem] = None
    daily: List[JobFailureTrendDayItem]
    jobs: List[JobFailureTrendJobItem]


class JobFailureTrendResponse(ApiResponse):
    data: JobFailureTrendPayload


class RuntimeConfigPayload(BaseModel):
    jobs: dict[str, Any]


class RuntimeConfigResponse(ApiResponse):
    data: RuntimeConfigPayload


class RuntimeConfigUpdateRequest(BaseModel):
    jobs: dict[str, Any]


class TushareTokenUpdateRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=255)


class HistoryJobRunRequest(BaseModel):
    start_date: str = Field(..., pattern=r'^\d{8}$')
    end_date: str = Field(..., pattern=r'^\d{8}$')
    force: bool = False


class DailyDateJobRunRequest(BaseModel):
    trade_date: str = Field(..., pattern=r'^\d{8}$')


# 埋伏池相关模型
class AmbushPoolCreate(BaseModel):
    ts_code: str = Field(..., min_length=9, max_length=16, description="股票代码")
    expected_logic: str = Field(..., min_length=1, max_length=255, description="埋伏预期逻辑")
    add_date: Optional[str] = Field(None, pattern=r'^\d{8}$', description="调入日期，格式YYYYMMDD")
    status: int = Field(1, description="状态：1=监控中, 0=已爆发调出, -1=逻辑证伪剔除")


class AmbushPoolUpdate(BaseModel):
    expected_logic: Optional[str] = Field(None, min_length=1, max_length=255, description="埋伏预期逻辑")
    status: Optional[int] = Field(None, description="状态")


class AmbushPoolResponse(BaseModel):
    ts_code: str
    name: Optional[str] = None
    industry: Optional[str] = None
    expected_logic: str
    add_date: str
    status: int
    update_time: Optional[str] = None
    # 关联的策略指标
    chip_vacuum: Optional[int] = None
    safety_margin: Optional[int] = None
    trend_baseline: Optional[int] = None
    liquidity_base: Optional[int] = None
    kline_body: Optional[int] = None
