from __future__ import annotations

from typing import Generator

from fastapi import Depends

from backend.app.config import load_config
from backend.app.runtime import build_database


def get_database() -> Generator:
    config = load_config()
    database = build_database(config)
    try:
        yield database
    finally:
        database.close()


class PreparedDatabaseProxy:
    def __init__(self, database):
        self._database = database

    def __getattr__(self, name: str):
        return getattr(self._database, name)

    def _prepare_sql(self, sql: str) -> str:
        if hasattr(self._database, 'prepare_sql'):
            return sql
        if getattr(self._database, 'driver', None) == 'sqlite':
            return sql.replace('%s', '?')
        return sql

    def fetch_all(self, sql: str, params=()):
        return self._database.fetch_all(self._prepare_sql(sql), params)

    def fetch_one(self, sql: str, params=()):
        return self._database.fetch_one(self._prepare_sql(sql), params)

    def execute(self, sql: str, params=()):
        return self._database.execute(self._prepare_sql(sql), params)


def get_prepared_database(database=Depends(get_database)):
    return PreparedDatabaseProxy(database)
