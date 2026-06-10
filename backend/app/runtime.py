from __future__ import annotations

from .config import load_config
from .db import Database
from .tushare_client import MockTushareClient, TushareClient


def build_database(config=None) -> Database:
    cfg = config or load_config()
    return Database.from_config(cfg.database)


def build_client(config=None):
    cfg = config or load_config()
    if cfg.tushare.use_mock:
        return MockTushareClient()
    return TushareClient(cfg.tushare.token, cfg.tushare.base_url, cfg.tushare.timeout_seconds)


def build_client_factory(config=None):
    cfg = config or load_config()

    def factory():
        return build_client(cfg)

    return factory
