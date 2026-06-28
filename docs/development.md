# 开发、验证与发布

## 环境

- Python 依赖：`requirements-desktop.txt`（递归包含 `backend/requirements.txt`）。
- Node 依赖：`frontend/package-lock.json`，使用 `npm ci` 安装。
- 桌面配置：`config.desktop.yaml`；密钥和本地数据库不提交。

## 必跑验证

```powershell
$env:APP_ENV='desktop'
python -m pytest -q
python -m compileall -q backend jobs scripts

cd frontend
npm test
npm run build
```

`npm run build` 会把生产资源写入 `backend/app/static/vue/`。构建后应确认旧哈希资源已移除、新资源与 `index.html` 一致。

## 数据库

- 当前桌面主路径为 SQLite：`data/stocknew.db`。
- `database/init.sqlite.sql` 是新库 schema 基线。
- `Database.init_schema()` 必须幂等处理受支持的存量列补齐。
- 修改 schema 前先备份真实库，并以旧库副本执行迁移回放、`PRAGMA quick_check` 和关键字段统计。
- MySQL 路径尚未获得与 SQLite 等价的发布验证，不得默认为完整支持。

## 主力控盘度回填

```powershell
python scripts/backfill_chaos_scores.py --database dist\data\stocknew.db --days 7
```

发布前检查 `chaos_index_val` 有效率、`score_chaos` 值域、`s_holder_score != score_chaos` 数量和 `HOLDER_SURGE` 样本。

## 契约快照

接口变更完成后，从 `backend.main:create_app()` 生成 OpenAPI 并覆盖 `openapi-final.yaml`。快照必须与 API 测试和前端消费字段同批提交。

## 发布边界

- 不把大型数据库嵌入 EXE；保留 `dist/data`、`dist/logs` 与用户配置。
- 打包成功不等于数据或策略有效性通过。
- 发布声明必须列出测试版本、测试结果、数据库快照范围和仍未验证的外部依赖。
