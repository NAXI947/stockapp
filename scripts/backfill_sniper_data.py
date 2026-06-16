"""
极简狙击手数据补齐脚本 (Sniper Data Backfill)

用途：检查并补齐 SQLite 数据库中缺失的数据表，使极简狙击手策略能正常运行。
包括：t_adj_factor, t_daily_basic, t_cyq_perf, t_weekly_bar,
      t_stk_holdernumber, t_block_trade, t_top_list, t_strategy_daily

使用方式：
  cd d:\\python\\stockapp
  .venv\\Scripts\\python scripts/backfill_sniper_data.py            # 诊断模式（仅检查）
  .venv\\Scripts\\python scripts/backfill_sniper_data.py --sync      # 执行补齐
  .venv\\Scripts\\python scripts/backfill_sniper_data.py --sync --skip-confirm  # 跳过确认

注意：需要有效的 Tushare token 配置在 config.desktop.yaml 中。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Setup project root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_ENV", "desktop")


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _fmt_count(n: int) -> str:
    """格式化数字，添加千分位"""
    return f"{n:,}"


def _print_header(title: str) -> None:
    width = 60
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def _print_table(headers: List[str], rows: List[List[str]], min_widths: List[int] | None = None) -> None:
    """简易表格打印"""
    if not rows:
        print("  (无数据)")
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    if min_widths:
        for i, mw in enumerate(min_widths):
            widths[i] = max(widths[i], mw)
    
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(f"  {header_line}")
    print(f"  {'  '.join('-' * w for w in widths)}")
    for row in rows:
        line = "  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row))
        print(f"  {line}")


# ──────────────────────────────────────────────────────────────
# Diagnostic: Check current data status
# ──────────────────────────────────────────────────────────────

def run_diagnostics(database) -> Dict[str, int]:
    """检查所有关键表的数据量，返回 {table_name: row_count}"""
    tables = [
        "t_stock_basic",
        "t_trade_cal",
        "t_daily_bar",
        "t_adj_factor",
        "t_daily_basic",
        "t_cyq_perf",
        "t_top_list",
        "t_share_float",
        "t_fin_indicator",
        "t_strategy_daily",
        "t_weekly_bar",
        "t_stk_holdernumber",
        "t_block_trade",
        "t_concept_detail",
    ]
    
    counts: Dict[str, int] = {}
    for table in tables:
        try:
            row = database.fetch_all(f"SELECT COUNT(*) AS cnt FROM {table}")
            counts[table] = int(row[0]["cnt"]) if row else 0
        except Exception as e:
            counts[table] = -1  # table doesn't exist
    
    return counts


def print_diagnostic_report(counts: Dict[str, int]) -> None:
    """打印诊断报告"""
    _print_header("📊 数据库诊断报告")
    
    # 数据分级
    REQUIRED_FOR_SNIPER = {
        "t_daily_bar": "日线行情（核心）",
        "t_adj_factor": "复权因子（均线计算）",
        "t_daily_basic": "换手率/量比（动态信号）",
        "t_stock_basic": "股票基本信息",
    }
    IMPORTANT_FOR_SNIPER = {
        "t_weekly_bar": "周线行情（MACD周线评分 15分）",
        "t_stk_holdernumber": "股东户数（筹码结构 15分）",
        "t_cyq_perf": "筹码绩效（真空度参考）",
        "t_top_list": "龙虎榜（动态信号 7分）",
        "t_block_trade": "大宗交易（龙虎榜补充）",
    }
    SUPPLEMENTAL = {
        "t_strategy_daily": "策略评分表",
        "t_share_float": "限售股解禁",
        "t_fin_indicator": "财务指标",
        "t_concept_detail": "概念板块",
        "t_trade_cal": "交易日历",
    }
    
    headers = ["表名", "行数", "状态", "用途"]
    rows = []
    
    missing_critical = []
    missing_important = []
    
    for table, desc in {**REQUIRED_FOR_SNIPER, **IMPORTANT_FOR_SNIPER, **SUPPLEMENTAL}.items():
        count = counts.get(table, -1)
        if count == -1:
            status = "❌ 不存在"
        elif count == 0:
            status = "⚠️  空表"
        else:
            status = "✅ 正常"
        
        priority = ""
        if table in REQUIRED_FOR_SNIPER:
            priority = "[必需]"
            if count <= 0:
                missing_critical.append(table)
        elif table in IMPORTANT_FOR_SNIPER:
            priority = "[重要]"
            if count <= 0:
                missing_important.append(table)
        else:
            priority = "[补充]"
        
        rows.append([table, _fmt_count(count) if count >= 0 else "N/A", status, f"{priority} {desc}"])
    
    _print_table(headers, rows, [22, 10, 10, 30])
    
    # 日期范围检查
    print()
    if counts.get("t_daily_bar", 0) > 0:
        print(f"  ✓ t_daily_bar 有 {_fmt_count(counts['t_daily_bar'])} 条记录")
    
    # 汇总
    print()
    if missing_critical:
        print(f"  🔴 缺失必需表: {', '.join(missing_critical)}")
        print(f"     → 狙击手策略将无法正常计算，需要补齐！")
    if missing_important:
        print(f"  🟡 缺失重要表: {', '.join(missing_important)}")
        print(f"     → 部分评分维度将使用默认保守分（0分），建议补齐。")
    if not missing_critical and not missing_important:
        print(f"  🟢 所有数据表正常，狙击手策略可以正常运行！")
    
    return missing_critical, missing_important


def check_date_coverage(database) -> Dict[str, Any]:
    """检查各表的日期覆盖范围"""
    date_tables = {
        "t_daily_bar": "trade_date",
        "t_adj_factor": "trade_date",
        "t_daily_basic": "trade_date",
        "t_cyq_perf": "trade_date",
        "t_top_list": "trade_date",
        "t_weekly_bar": "trade_date",
        "t_block_trade": "trade_date",
        "t_strategy_daily": "trade_date",
    }
    
    report = {}
    for table, date_col in date_tables.items():
        try:
            row = database.fetch_all(
                f"SELECT MIN({date_col}) AS min_date, MAX({date_col}) AS max_date, "
                f"COUNT(DISTINCT {date_col}) AS date_count FROM {table}"
            )
            if row and row[0].get("min_date"):
                report[table] = {
                    "min_date": row[0]["min_date"],
                    "max_date": row[0]["max_date"],
                    "date_count": int(row[0]["date_count"]),
                }
            else:
                report[table] = {"min_date": "-", "max_date": "-", "date_count": 0}
        except Exception:
            report[table] = {"min_date": "ERR", "max_date": "ERR", "date_count": -1}
    
    _print_header("📅 日期覆盖范围")
    headers = ["表名", "最早日期", "最晚日期", "交易日数"]
    rows = []
    for table, info in report.items():
        rows.append([
            table,
            str(info["min_date"]),
            str(info["max_date"]),
            str(info["date_count"]) if info["date_count"] >= 0 else "ERR",
        ])
    _print_table(headers, rows, [22, 10, 10, 8])
    
    return report


# ──────────────────────────────────────────────────────────────
# Sync: Run data backfill
# ──────────────────────────────────────────────────────────────

def run_backfill(config, database) -> None:
    """执行数据补齐"""
    from backend.app.ingest import (
        DataIngestionService,
        COMMON_DATE_SUPPLEMENTAL_SPECS,
        FEATURED_DATE_SUPPLEMENTAL_SPECS,
        FULL_MARKET_SUPPLEMENTAL_SPECS,
        print_sync_summary,
    )
    from backend.app.runtime import build_client, build_client_factory
    
    client = build_client(config)
    service = DataIngestionService(
        client,
        database,
        max_workers=config.jobs.max_workers,
        client_factory=build_client_factory(config),
        qps_limit=config.jobs.qps_limit,
        qps_burst=config.jobs.qps_burst,
        retry_max_attempts=config.jobs.retry_max_attempts,
        retry_base_delay=config.jobs.retry_base_delay,
        retry_max_delay=config.jobs.retry_max_delay,
        api_qps_limits=config.jobs.api_qps_limits,
        api_concurrency_limits=config.jobs.api_concurrency_limits,
        table_concurrency_limits=config.jobs.table_concurrency_limits,
        heartbeat_interval_seconds=config.jobs.heartbeat_interval_seconds,
        verbose_request_logs=config.jobs.verbose_request_logs,
    )
    
    # 获取现有交易日范围
    date_rows = database.fetch_all(
        "SELECT DISTINCT trade_date FROM t_daily_bar ORDER BY trade_date"
    )
    trade_dates = [str(r["trade_date"]) for r in date_rows if r.get("trade_date")]
    
    if not trade_dates:
        print("\n  ❌ t_daily_bar 中没有交易日数据，无法执行补齐。")
        print("     请先运行 job_daily 或 job_history 获取基础行情数据。")
        return
    
    print(f"\n  交易日范围: {trade_dates[0]} ~ {trade_dates[-1]} (共 {len(trade_dates)} 天)")
    
    overall_summary: Dict[str, Dict[str, Any]] = {}
    
    # ──────────────────────────────────────────────────────────
    # Step 1: 同步基础参考表 (stock_basic, trade_cal)
    # ──────────────────────────────────────────────────────────
    _print_header("Step 1/5: 同步基础参考表")
    try:
        ref_summary = service.run_common_sync(
            trade_date=trade_dates[-1],
            include_static_supplemental=True,
        )
        overall_summary.update(ref_summary)
        print("  ✅ 基础参考表同步完成")
    except Exception as e:
        print(f"  ⚠️  基础参考表同步失败 (可能已有数据): {e}")
    
    # ──────────────────────────────────────────────────────────
    # Step 2: 按日补齐 COMMON 日期驱动表
    #         (top_list, weekly_bar, stk_holdernumber, block_trade)
    # ──────────────────────────────────────────────────────────
    _print_header("Step 2/5: 补齐日期驱动表 (周线/股东户数/龙虎榜/大宗)")
    
    # 这些表使用 COMMON_DATE_SUPPLEMENTAL_SPECS 进行同步
    common_date_summary: Dict[str, Dict[str, Any]] = {}
    try:
        service._sync_date_supplemental_tables(
            common_date_summary,
            trade_dates,
            COMMON_DATE_SUPPLEMENTAL_SPECS,
        )
        overall_summary.update(common_date_summary)
        for table, info in common_date_summary.items():
            rows = info.get("rows", 0)
            warning = info.get("warning", "")
            if warning:
                print(f"  ⚠️  {table}: 同步受限 - {warning[:80]}")
            else:
                print(f"  ✅ {table}: 补齐 {_fmt_count(rows)} 条")
    except Exception as e:
        print(f"  ⚠️  日期驱动表同步部分失败: {e}")
    
    # ──────────────────────────────────────────────────────────
    # Step 3: 补齐 FEATURED 日期驱动表 (cyq_perf)
    # ──────────────────────────────────────────────────────────
    _print_header("Step 3/5: 补齐筹码绩效表 (cyq_perf)")
    
    featured_summary: Dict[str, Dict[str, Any]] = {}
    try:
        service._sync_date_supplemental_tables(
            featured_summary,
            trade_dates,
            FEATURED_DATE_SUPPLEMENTAL_SPECS,
        )
        overall_summary.update(featured_summary)
        for table, info in featured_summary.items():
            rows = info.get("rows", 0)
            warning = info.get("warning", "")
            if warning:
                print(f"  ⚠️  {table}: 同步受限 - {warning[:80]}")
            else:
                print(f"  ✅ {table}: 补齐 {_fmt_count(rows)} 条")
    except Exception as e:
        print(f"  ⚠️  筹码绩效同步失败 (需要 2000+ 积分): {e}")
    
    # ──────────────────────────────────────────────────────────
    # Step 4: 补齐全市场补充表 (share_float, fina_indicator)
    # ──────────────────────────────────────────────────────────
    _print_header("Step 4/5: 补齐全市场补充表 (限售解禁/财务指标)")
    
    for spec in FULL_MARKET_SUPPLEMENTAL_SPECS:
        try:
            param_list = service._build_query_param_list(spec.api_name, None)
            result = service._sync_spec_in_batches(spec, param_list)
            overall_summary[spec.table_name] = result
            rows = result.get("rows", 0)
            warning = result.get("warning", "")
            if warning:
                print(f"  ⚠️  {spec.table_name}: 同步受限 - {warning[:80]}")
            else:
                print(f"  ✅ {spec.table_name}: 补齐 {_fmt_count(rows)} 条")
        except Exception as e:
            print(f"  ⚠️  {spec.table_name} 同步失败: {e}")
    
    # ──────────────────────────────────────────────────────────
    # Step 5: 重建策略评分表 (t_strategy_daily & t_sniper_daily)
    # ──────────────────────────────────────────────────────────
    _print_header("Step 5/5: 重建策略评分表 (t_strategy_daily & t_sniper_daily)")
    
    try:
        strategy_result = service._build_strategy_daily()
        overall_summary["t_strategy_daily"] = strategy_result
        rows = strategy_result.get("rows", 0)
        print(f"  ✅ t_strategy_daily: 生成 {_fmt_count(rows)} 条评分记录")
    except Exception as e:
        print(f"  ❌ 策略评分重建失败: {e}")
        import traceback
        traceback.print_exc()

    try:
        sniper_result = service._build_sniper_daily()
        overall_summary["t_sniper_daily"] = sniper_result
        rows = sniper_result.get("rows", 0)
        print(f"  ✅ t_sniper_daily: 生成 {_fmt_count(rows)} 条评分记录")
    except Exception as e:
        print(f"  ❌ 狙击手评分重建失败: {e}")
        import traceback
        traceback.print_exc()
    
    # ──────────────────────────────────────────────────────────
    # 汇总
    # ──────────────────────────────────────────────────────────
    _print_header("📋 补齐汇总")
    print_sync_summary(overall_summary, job_name="backfill_sniper_data")


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="极简狙击手数据补齐脚本 - 检查并补齐数据库缺失数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python scripts/backfill_sniper_data.py              # 仅诊断（不修改数据）
  python scripts/backfill_sniper_data.py --sync       # 诊断后执行补齐
  python scripts/backfill_sniper_data.py --sync --skip-confirm  # 跳过确认
        """,
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="执行数据补齐（不带此参数仅执行诊断）",
    )
    parser.add_argument(
        "--skip-confirm",
        action="store_true",
        help="跳过确认提示，直接执行",
    )
    args = parser.parse_args()
    
    # 加载配置
    from backend.app.config import load_config
    from backend.app.runtime import build_database
    
    config = load_config(ROOT / "config.desktop.yaml")
    database = build_database(config)
    database.init_schema()
    
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║        🎯 极简狙击手 - 数据补齐工具                      ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"  数据库: {config.database.path}")
    print(f"  API:    {config.tushare.base_url}")
    print(f"  Token:  {'已配置' if config.tushare.token else '❌ 未配置'}")
    
    # 诊断
    counts = run_diagnostics(database)
    missing_critical, missing_important = print_diagnostic_report(counts)
    date_report = check_date_coverage(database)
    
    if not args.sync:
        print()
        print("  ────────────────────────────────────────────")
        print("  ℹ️  当前为诊断模式，不会修改数据。")
        print("  ℹ️  如需执行补齐，请添加 --sync 参数：")
        print("      .venv\\Scripts\\python scripts/backfill_sniper_data.py --sync")
        print()
        database.close()
        return
    
    # 确认
    if not args.skip_confirm:
        print()
        print("  ⚠️  即将执行数据补齐，这将：")
        print("     1. 从 Tushare API 拉取缺失数据")
        print("     2. 写入 SQLite 数据库")
        print("     3. 重建策略评分表")
        print()
        answer = input("  确认执行？(y/N): ").strip().lower()
        if answer not in ("y", "yes"):
            print("  已取消。")
            database.close()
            return
    
    if not config.tushare.token:
        print("\n  ❌ Tushare token 未配置！请先在 config.desktop.yaml 中设置 tushare.token")
        database.close()
        return
    
    # 执行补齐
    start_time = time.time()
    try:
        run_backfill(config, database)
    except KeyboardInterrupt:
        print("\n\n  ⚠️  用户中断操作")
    except Exception as e:
        print(f"\n  ❌ 补齐过程出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        elapsed = time.time() - start_time
        print(f"\n  ⏱️  总耗时: {elapsed:.1f} 秒")
        
        # 补齐后再次诊断
        _print_header("📊 补齐后数据状态")
        new_counts = run_diagnostics(database)
        print_diagnostic_report(new_counts)
        
        database.close()


if __name__ == "__main__":
    main()
