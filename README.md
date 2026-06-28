# stockapp

stockapp 是一个本地优先的股票数据同步与策略分析桌面应用。FastAPI 提供本地 API，Vue 3 提供界面，PyWebView/PyInstaller 提供桌面运行与打包，SQLite 是当前默认数据存储。

## 快速验证

```powershell
$env:APP_ENV='desktop'
python -m pytest -q
cd frontend
npm test
npm run build
```

启动桌面应用：

```powershell
python run_desktop.py
```

## 文档

- [当前状态](docs/current-status.md)
- [架构与模块边界](docs/architecture.md)
- [HTTP API 规范](docs/api.md)
- [策略与指标算法](docs/algorithms.md)
- [开发与发布](docs/development.md)

`openapi-final.yaml` 是 API 契约快照；代码中的 FastAPI schema 是生成来源。
