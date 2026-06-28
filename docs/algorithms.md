# 策略与指标算法

本文记录实现契约，不构成投资建议或收益有效性证明。

## 策略注册

| 策略 ID | 结果表 | 主要用途 |
|---|---|---|
| `vacuum_strategy_v1_2` | `t_strategy_daily` | 阻力最小爆发选股 |
| `sniper_strategy_v1` | `t_sniper_daily` | 极简狙击手评分 |

两套策略通过 `StockStrategy.calculate` 接受统一基础输入；周线和大宗交易是可选上下文。共享数值与复权指标位于 `backend/app/strategy/indicators.py`。

## 主力控盘度（量价无序度）

需要目标日前后共 21 条连续交易记录：20 个交易日的摩擦观测，以及第一个观测日前的收盘价。

```text
daily_amplitude = (high - low) / previous_close × 100
daily_friction  = daily_amplitude × turnover_rate
mean_friction   = 最近 20 日 daily_friction 平均值
net_return_abs  = abs((current_close - close_20d_ago) / close_20d_ago × 100)
chaos_index_val = mean_friction / (net_return_abs + 0.1)
```

结果保留两位小数。无效、非有限或不足输入返回 `NULL/0`。

| `chaos_index_val` | `score_chaos` |
|---|---:|
| `< 1.0` | 15 |
| `[1.0, 3.0)` | 10 |
| `[3.0, 8.0)` | 5 |
| `>= 8.0` | 0 |

`chaos_index_val >= 8.0` 触发兼容拒绝码 `HOLDER_SURGE`。常量和纯计算实现集中在 `backend/app/strategy/chaos.py`，策略组合层不得复制阈值。

## 兼容与变更规则

- `s_holder_score == score_chaos` 是当前强兼容约束。
- 阈值、窗口、稳定项、权重或拒绝顺序任何变化都属于行为变更，必须新增策略版本或明确迁移决策。
- 单纯抽取函数、消除重复和增加有限数值保护属于行为保持型重构，必须通过 golden/边界测试。
- `vacuum_strategy_v1_2` 的历史评分和拒绝语义保持不变；未经产品/量化确认不纠正其注释与业务争议。
