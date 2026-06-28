# HTTP API 规范

## 基础约定

- 业务前缀：`/api/v1`。
- 系统探针：`GET /health`，不放入业务前缀。
- 结构化响应优先使用 `ApiResponse` 体系：`code`、`message`、`data`。
- 日期字段使用 `YYYYMMDD` 字符串，与现有数据库保持兼容。
- 股票代码使用 Tushare `ts_code` 形式，例如 `000001.SZ`。
- 现有字段只允许向后兼容扩展；重命名或删除必须创建版本化迁移决策。

## 接口分组

| Tag | 接口范围 |
|---|---|
| `stocks` | `/picks`、`/kline/{ts_code}`、`/detail/{ts_code}`、批量搜索 |
| `analysis` | `/analysis/stock_advice` |
| `data-health` | 数据健康与受控回填 |
| `jobs` | 任务定义、执行、运行记录和趋势 |
| `settings` | Tushare token 与运行配置 |
| `watchlist` | 埋伏池维护 |
| `system` | `/health` |

完整字段和状态码以 `openapi-final.yaml` 为准。更新接口时应从 `backend.main:create_app()` 重新生成契约，并运行 API 测试。

## 兼容约束

- `is_sniper=true` 会让选股和详情接口读取 `t_sniper_daily`，但保持通用 `final_score/rejected/reject_reason` 字段。
- `sniper_score/sniper_rejected/sniper_reject_reason` 是狙击手显式字段。
- `s_holder_score` 暂时等于 `score_chaos`，仅为旧客户端兼容；新代码使用 `score_chaos`。
- 未声明 Pydantic response model 的运维接口是后续规范化债务，不应借本轮结构整理偷偷改变返回形状。
