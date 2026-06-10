from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import load_config
from backend.app.runtime import build_database
from jobs.job_seed_runtime_config import apply_runtime_config_seed


def _mysql_column_exists(database, schema: str, table: str, column: str) -> bool:
    rows = database.fetch_all(
        """
        SELECT 1 AS ok
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s
        LIMIT 1
        """,
        (schema, table, column),
    )
    return bool(rows)


def _mysql_index_exists(database, schema: str, table: str, index_name: str) -> bool:
    rows = database.fetch_all(
        """
        SELECT 1 AS ok
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME=%s
        LIMIT 1
        """,
        (schema, table, index_name),
    )
    return bool(rows)


def _mysql_add_column_if_missing(
    database,
    schema: str,
    table: str,
    column: str,
    definition_sql: str,
) -> bool:
    if _mysql_column_exists(database, schema, table, column):
        return False
    # DDL 语句使用原生连接执行，避免参数化导致的 % 转义问题
    sql = f"ALTER TABLE `{table}` ADD COLUMN `{column}` {definition_sql}"
    with database._connection_scope() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(sql)
            conn.commit()
        finally:
            cursor.close()
    return True


def _mysql_add_index_if_missing(
    database,
    schema: str,
    table: str,
    index_name: str,
    definition_sql: str,
) -> bool:
    if _mysql_index_exists(database, schema, table, index_name):
        return False
    # DDL 语句使用原生连接执行，避免参数化导致的 % 转义问题
    sql = f"ALTER TABLE `{table}` ADD {definition_sql}"
    with database._connection_scope() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(sql)
            conn.commit()
        finally:
            cursor.close()
    return True


def _apply_mysql_upgrade_columns(database, schema: str) -> int:
    migrations: list[tuple[str, str, str]] = [
        ('t_stock_basic', 'sw_level1_name', "VARCHAR(50) DEFAULT NULL COMMENT '申万一级行业名称'"),
        ('t_stock_basic', 'sw_level2_name', "VARCHAR(50) DEFAULT NULL COMMENT '申万二级行业名称'"),
        ('t_cyq_perf', 'concentration', "DECIMAL(12,6) DEFAULT NULL COMMENT '筹码集中度(90%成本区间)'"),
        ('t_strategy_daily', 'upper_space', "DECIMAL(12,6) DEFAULT NULL COMMENT '上方空间(现价距离250日最高点百分比)'"),
        ('t_strategy_daily', 'vol_score', "DECIMAL(12,6) DEFAULT NULL COMMENT '成交量稳定性得分'"),
        # 策略 v1.1 新增字段
        ('t_strategy_daily', 'trend_baseline', "INT DEFAULT 0 COMMENT '趋势生命线: close>ma60'"),
        ('t_strategy_daily', 'chip_vacuum', "INT DEFAULT 0 COMMENT '筹码真空: 上方15%压力区筹码<10%'"),
        ('t_strategy_daily', 'kline_body', "INT DEFAULT 0 COMMENT 'K线实体: (close-low)/(high-low)>0.6'"),
        ('t_strategy_daily', 'liquidity_base', "INT DEFAULT 0 COMMENT '流动性: 量比>=1.8且换手>=2%'"),
        ('t_strategy_daily', 'safety_margin', "INT DEFAULT 0 COMMENT '安全边际: close/ma20<1.25'"),
        ('t_strategy_daily', 'top_list_3d', "INT DEFAULT 0 COMMENT '龙虎榜: 近3日上榜且净买入>0'"),
        ('t_strategy_daily', 'st_risk', "INT DEFAULT 0 COMMENT 'ST风险: 名称含ST'"),
        ('t_strategy_daily', 'rejected', "INT DEFAULT 0 COMMENT '准入拒绝: 0=通过,1=拒绝'"),
        ('t_strategy_daily', 'reject_reason', "TEXT COMMENT '拒绝原因: 未通过准入的条件'"),
    ]
    applied = 0
    for table, column, definition_sql in migrations:
        if _mysql_add_column_if_missing(
            database,
            schema=schema,
            table=table,
            column=column,
            definition_sql=definition_sql,
        ):
            applied += 1
    return applied


def _apply_mysql_upgrade_indexes(database, schema: str) -> int:
    migrations: list[tuple[str, str, str]] = [
        ('t_daily_bar', 'idx_daily_bar_trade_date', 'INDEX `idx_daily_bar_trade_date` (`trade_date`)'),
        ('t_adj_factor', 'idx_adj_factor_trade_date', 'INDEX `idx_adj_factor_trade_date` (`trade_date`)'),
        ('t_daily_basic', 'idx_daily_basic_trade_date', 'INDEX `idx_daily_basic_trade_date` (`trade_date`)'),
        ('t_cyq_perf', 'idx_cyq_perf_trade_date', 'INDEX `idx_cyq_perf_trade_date` (`trade_date`)'),
        ('t_top_list', 'idx_top_list_code_date', 'INDEX `idx_top_list_code_date` (`ts_code`, `trade_date`)'),
        ('t_share_float', 'idx_share_float_code_date', 'INDEX `idx_share_float_code_date` (`ts_code`, `float_date`)'),
        ('t_fin_indicator', 'idx_fin_indicator_code_end_ann', 'INDEX `idx_fin_indicator_code_end_ann` (`ts_code`, `end_date`, `ann_date`)'),
        ('t_strategy_daily', 'idx_strategy_trade_score_code', 'INDEX `idx_strategy_trade_score_code` (`trade_date`, `final_score`, `ts_code`)'),
    ]
    applied = 0
    for table, index_name, definition_sql in migrations:
        if _mysql_add_index_if_missing(
            database,
            schema=schema,
            table=table,
            index_name=index_name,
            definition_sql=definition_sql,
        ):
            applied += 1
    return applied


def main() -> None:
    config = load_config(ROOT / 'config.yaml')
    database = build_database(config)
    try:
        database.init_schema()
        print("bootstrap: schema ensured", flush=True)
        if database.driver == 'mysql':
            applied_columns = _apply_mysql_upgrade_columns(database, config.database.name)
            applied_indexes = _apply_mysql_upgrade_indexes(database, config.database.name)
            print(
                f"bootstrap: mysql upgrade columns applied={applied_columns} indexes applied={applied_indexes}",
                flush=True,
            )
        seeded = apply_runtime_config_seed(database, config)
        print(f"bootstrap: runtime config keys seeded={len(seeded)}", flush=True)
    finally:
        database.close()


if __name__ == '__main__':
    main()
