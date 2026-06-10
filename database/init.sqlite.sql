CREATE TABLE IF NOT EXISTS t_stock_basic (
  ts_code TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  name TEXT NOT NULL,
  industry TEXT,
  sw_level1_name TEXT DEFAULT NULL,
  sw_level2_name TEXT DEFAULT NULL,
  list_date TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS t_trade_cal (
  cal_date TEXT PRIMARY KEY,
  is_open INTEGER NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS t_daily_bar (
  ts_code TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  vol REAL,
  amount REAL,
  pct_chg REAL,
  PRIMARY KEY (ts_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_daily_bar_trade_date ON t_daily_bar (trade_date);

CREATE TABLE IF NOT EXISTS t_adj_factor (
  ts_code TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  adj_factor REAL,
  PRIMARY KEY (ts_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_adj_factor_trade_date ON t_adj_factor (trade_date);

CREATE TABLE IF NOT EXISTS t_daily_basic (
  ts_code TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  turnover_rate REAL,
  volume_ratio REAL,
  circ_mv REAL,
  PRIMARY KEY (ts_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_daily_basic_trade_date ON t_daily_basic (trade_date);

CREATE TABLE IF NOT EXISTS t_concept_detail (
  id TEXT NOT NULL,
  concept_name TEXT NOT NULL,
  ts_code TEXT NOT NULL,
  name TEXT,
  PRIMARY KEY (id, ts_code)
);
CREATE INDEX IF NOT EXISTS idx_concept_ts_code ON t_concept_detail (ts_code);
CREATE INDEX IF NOT EXISTS idx_concept_name ON t_concept_detail (concept_name);

CREATE TABLE IF NOT EXISTS t_cyq_perf (
  ts_code TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  winner_rate REAL,
  cost_50 REAL,
  cost_85 REAL,
  concentration REAL,
  PRIMARY KEY (ts_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_cyq_perf_trade_date ON t_cyq_perf (trade_date);

CREATE TABLE IF NOT EXISTS t_top_list (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_code TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  name TEXT,
  net REAL,
  buy REAL,
  sell REAL,
  reason TEXT,
  UNIQUE (ts_code, trade_date, reason)
);
CREATE INDEX IF NOT EXISTS idx_top_list_trade_date ON t_top_list (trade_date);
CREATE INDEX IF NOT EXISTS idx_top_list_ts_code ON t_top_list (ts_code);
CREATE INDEX IF NOT EXISTS idx_top_list_code_date ON t_top_list (ts_code, trade_date);

CREATE TABLE IF NOT EXISTS t_share_float (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_code TEXT NOT NULL,
  ann_date TEXT,
  float_date TEXT NOT NULL,
  float_share REAL,
  float_ratio REAL,
  holder_name TEXT,
  share_type TEXT,
  UNIQUE (ts_code, float_date, holder_name, share_type)
);
CREATE INDEX IF NOT EXISTS idx_share_float_date ON t_share_float (float_date);
CREATE INDEX IF NOT EXISTS idx_share_float_ts_code ON t_share_float (ts_code);
CREATE INDEX IF NOT EXISTS idx_share_float_code_date ON t_share_float (ts_code, float_date);

CREATE TABLE IF NOT EXISTS t_fin_indicator (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_code TEXT NOT NULL,
  ann_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  debt_to_assets REAL,
  roe REAL,
  UNIQUE (ts_code, ann_date, end_date)
);
CREATE INDEX IF NOT EXISTS idx_fin_indicator_end_date ON t_fin_indicator (end_date);
CREATE INDEX IF NOT EXISTS idx_fin_indicator_ts_code ON t_fin_indicator (ts_code);
CREATE INDEX IF NOT EXISTS idx_fin_indicator_code_end_ann ON t_fin_indicator (ts_code, end_date, ann_date);

CREATE TABLE IF NOT EXISTS t_strategy_daily (
  ts_code TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  ma5 REAL,
  ma20 REAL,
  ma60 REAL,
  upper_space REAL,
  vol_score REAL,
  is_limit_up INTEGER NOT NULL DEFAULT 0,
  limit_up_20d INTEGER NOT NULL DEFAULT 0,
  bull_trend INTEGER NOT NULL DEFAULT 0,
  avg_price_support INTEGER NOT NULL DEFAULT 0,
  float_risk_7d INTEGER NOT NULL DEFAULT 0,
  final_score INTEGER NOT NULL DEFAULT 0,
  pct_chg REAL,
  turnover_rate REAL,
  volume_ratio REAL,
  winner_rate REAL,
  trend_baseline INTEGER NOT NULL DEFAULT 0,
  chip_vacuum INTEGER NOT NULL DEFAULT 0,
  kline_body INTEGER NOT NULL DEFAULT 0,
  liquidity_base INTEGER NOT NULL DEFAULT 0,
  safety_margin INTEGER NOT NULL DEFAULT 0,
  top_list_3d INTEGER NOT NULL DEFAULT 0,
  st_risk INTEGER NOT NULL DEFAULT 0,
  rejected INTEGER NOT NULL DEFAULT 0,
  reject_reason TEXT,
  PRIMARY KEY (ts_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_strategy_trade_date ON t_strategy_daily (trade_date);
CREATE INDEX IF NOT EXISTS idx_strategy_score ON t_strategy_daily (final_score);
CREATE INDEX IF NOT EXISTS idx_strategy_trade_score_code ON t_strategy_daily (trade_date, final_score, ts_code);

CREATE TABLE IF NOT EXISTS t_job_run_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_name TEXT NOT NULL,
  run_mode TEXT NOT NULL,
  target_range TEXT,
  max_workers INTEGER NOT NULL,
  timeout_seconds INTEGER NOT NULL DEFAULT 21600,
  status TEXT NOT NULL,
  timed_out INTEGER NOT NULL DEFAULT 0,
  duration_seconds INTEGER,
  message TEXT,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_run_log_job_name ON t_job_run_log (job_name);
CREATE INDEX IF NOT EXISTS idx_job_run_log_status ON t_job_run_log (status);
CREATE INDEX IF NOT EXISTS idx_job_run_log_started_at ON t_job_run_log (started_at);

CREATE TABLE IF NOT EXISTS t_job_checkpoint (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_name TEXT NOT NULL,
  target_range TEXT NOT NULL,
  last_completed_trade_date TEXT,
  status TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (job_name, target_range)
);
CREATE INDEX IF NOT EXISTS idx_job_checkpoint_status ON t_job_checkpoint (status);

CREATE TABLE IF NOT EXISTS t_job_lock (
  job_name TEXT PRIMARY KEY,
  lock_token TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_job_lock_expires_at ON t_job_lock (expires_at);

CREATE TABLE IF NOT EXISTS t_job_stage_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER,
  job_name TEXT NOT NULL,
  stage_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'success',
  duration_ms INTEGER NOT NULL,
  extra_json TEXT,
  message TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_job_stage_run_id ON t_job_stage_log (run_id);
CREATE INDEX IF NOT EXISTS idx_job_stage_job_name ON t_job_stage_log (job_name);
CREATE INDEX IF NOT EXISTS idx_job_stage_stage_name ON t_job_stage_log (stage_name);
CREATE INDEX IF NOT EXISTS idx_job_stage_created_at ON t_job_stage_log (created_at);

CREATE TABLE IF NOT EXISTS t_job_table_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER,
  job_name TEXT NOT NULL,
  table_name TEXT NOT NULL,
  fetched_rows INTEGER NOT NULL DEFAULT 0,
  missing_fields_json TEXT,
  null_fields_json TEXT,
  status TEXT NOT NULL DEFAULT 'success',
  message TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_job_table_run_id ON t_job_table_log (run_id);
CREATE INDEX IF NOT EXISTS idx_job_table_job_name ON t_job_table_log (job_name);
CREATE INDEX IF NOT EXISTS idx_job_table_table_name ON t_job_table_log (table_name);
CREATE INDEX IF NOT EXISTS idx_job_table_created_at ON t_job_table_log (created_at);

CREATE TABLE IF NOT EXISTS t_runtime_config (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  config_key TEXT NOT NULL,
  config_value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (config_key)
);
CREATE INDEX IF NOT EXISTS idx_runtime_config_updated_at ON t_runtime_config (updated_at);

CREATE TABLE IF NOT EXISTS t_ambush_pool (
  ts_code TEXT PRIMARY KEY,
  expected_logic TEXT NOT NULL,
  add_date TEXT NOT NULL,
  status INTEGER NOT NULL DEFAULT 1,
  update_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ambush_status ON t_ambush_pool (status);
CREATE INDEX IF NOT EXISTS idx_ambush_add_date ON t_ambush_pool (add_date);
