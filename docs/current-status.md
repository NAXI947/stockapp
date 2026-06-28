# 当前状态

更新日期：2026-06-28

## 已观察事实

- 桌面运行链为 PyWebView → Uvicorn/FastAPI → Vue SPA。
- 当前默认数据库模式为 SQLite；`backend/app/db.py` 仍保留 MySQL 兼容路径。
- 已注册 `vacuum_strategy_v1_2` 与 `sniper_strategy_v1` 两套策略。
- 主力控盘度已落在 `t_sniper_daily.chaos_index_val` 与 `score_chaos`；`s_holder_score` 是兼容别名。
- 日更、指定日期更新、历史更新和数据健康检查已切换到主力控盘度链路，不再把 `t_stk_holdernumber` 作为当前评分输入。
- FastAPI 业务接口稳定前缀为 `/api/v1`，契约快照为 `openapi-final.yaml`。

## 2026-06-28 验证基线

- Python：Python 3.14.5。
- 后端测试初始结果：87 passed、2 failed；失败来自狙击手新增 SQL 与测试假数据库契约不同步。
- Vue production build：通过，103 modules transformed。
- 代码整理边界：不修改策略阈值、评分权重、拒绝顺序、数据库字段含义和对外 JSON 字段。

整理后验证结果：94 passed、0 failed；前端 2 passed，production build 通过；Python compileall 通过。

## 已知风险

- `backend/app/ingest.py` 与 `backend/app/api.py` 仍是高集中度模块，应在契约测试保护下按领域继续拆分。
- MySQL 初始化与发布承诺缺少完整、持续验证；在负责人确认前不能视为与 SQLite 同等级支持。
- 策略算法通过单元测试只能证明实现一致性，不能证明投资收益或业务有效性。
- `s_holder_score` 的历史名称与当前含义不一致，只能在明确兼容窗口后移除。
- 发布库体积和真实数据量远高于测试 fixture，性能结论需要独立基准。

## WFF PhaseX 结论

本轮采用 `technical-refactor`，完成状态为 `direct-to-P3`，但只授权行为保持型结构整理。算法阈值变更、MySQL 退役、兼容字段删除和大规模数据库迁移仍属于 `decision-required`。
