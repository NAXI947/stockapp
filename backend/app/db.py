from __future__ import annotations

import time
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from queue import Empty, LifoQueue
from threading import Lock
from typing import Iterable, Iterator, Sequence

from backend.app.paths import resource_path, runtime_root

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:  # pragma: no cover - runtime dependency
    pymysql = None
    DictCursor = None


class Database:
    def __init__(
        self,
        driver: str,
        host: str,
        port: int,
        user: str,
        password: str,
        name: str,
        pool_size: int = 10,
        pool_timeout: int = 15,
        path: str = '',
        sqlite_path: str = '',
    ):
        self.driver = driver
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.name = name
        self.pool_size = pool_size
        self.pool_timeout = pool_timeout
        self.path = path or sqlite_path
        self._sqlite_fallback_path: Path | None = None
        self._pool = None
        self._pool_lock = Lock()
        self._pool_created = 0
        self._pool_connections = []
        self._connect()

    @classmethod
    def from_config(cls, config) -> 'Database':
        return cls(
            driver=config.driver,
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            name=config.name,
            pool_size=getattr(config, 'pool_size', 10),
            pool_timeout=getattr(config, 'pool_timeout', 15),
            path=getattr(config, 'path', '') or getattr(config, 'sqlite_path', ''),
        )

    def _connect(self) -> None:
        if self.driver == 'mysql':
            if pymysql is None:
                raise RuntimeError('pymysql is required for MySQL mode. Install dependencies first.')
            self._ensure_mysql_database()
            self._pool = LifoQueue(maxsize=self.pool_size)
            return
        if self.driver == 'sqlite':
            db_path = self._sqlite_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._pool = LifoQueue(maxsize=self.pool_size)
            return
        raise ValueError(f'Unsupported driver: {self.driver}. Supported drivers: mysql, sqlite.')

    def _sqlite_path(self) -> Path:
        raw_path = self.path or self.name or 'data/stocknew.db'
        path = Path(raw_path)
        if not path.is_absolute():
            path = runtime_root() / path
        return path

    def _new_mysql_connection(self):
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.name,
            charset='utf8mb4',
            autocommit=False,
            cursorclass=DictCursor,
        )

    def _new_sqlite_connection(self):
        db_target = self._sqlite_fallback_path or self._sqlite_path()
        try:
            connection = sqlite3.connect(
                db_target,
                timeout=self.pool_timeout,
                check_same_thread=False,
            )
        except sqlite3.OperationalError:
            if self.path:
                self._sqlite_fallback_path = Path(str(self._sqlite_path()) + '.sqlite')
                connection = sqlite3.connect(
                    self._sqlite_fallback_path,
                    timeout=self.pool_timeout,
                    check_same_thread=False,
                )
            else:
                raise
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=5000')
        return connection

    def _checkout_mysql_connection(self):
        if self._pool is None:
            raise RuntimeError('MySQL pool is not initialized.')
        try:
            connection = self._pool.get_nowait()
        except Empty:
            with self._pool_lock:
                if self._pool_created < self.pool_size:
                    connection = self._new_mysql_connection()
                    self._pool_created += 1
                    self._pool_connections.append(connection)
                    return connection
            try:
                connection = self._pool.get(timeout=self.pool_timeout)
            except Empty as exc:
                raise RuntimeError(
                    f'MySQL connection pool exhausted after waiting {self.pool_timeout}s '
                    f'(pool_size={self.pool_size})'
                ) from exc
        connection.ping(reconnect=True)
        return connection

    def _checkout_sqlite_connection(self):
        if self._pool is None:
            raise RuntimeError('SQLite pool is not initialized.')
        try:
            connection = self._pool.get_nowait()
        except Empty:
            with self._pool_lock:
                if self._pool_created < self.pool_size:
                    connection = self._new_sqlite_connection()
                    self._pool_created += 1
                    self._pool_connections.append(connection)
                    return connection
            try:
                connection = self._pool.get(timeout=self.pool_timeout)
            except Empty as exc:
                raise RuntimeError(
                    f'SQLite connection pool exhausted after waiting {self.pool_timeout}s '
                    f'(pool_size={self.pool_size})'
                ) from exc
        return connection

    def _return_mysql_connection(self, connection) -> None:
        if self._pool is None:
            connection.close()
            return
        self._pool.put(connection)

    def _return_sqlite_connection(self, connection) -> None:
        if self._pool is None:
            connection.close()
            return
        self._pool.put(connection)

    @contextmanager
    def _connection_scope(self):
        if self.driver == 'sqlite':
            connection = self._checkout_sqlite_connection()
        else:
            connection = self._checkout_mysql_connection()
        try:
            yield connection
        finally:
            if self.driver == 'sqlite':
                self._return_sqlite_connection(connection)
            else:
                self._return_mysql_connection(connection)

    def _ensure_mysql_database(self) -> None:
        last_exc: Exception | None = None
        for attempt in range(1, 21):
            try:
                bootstrap = pymysql.connect(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    charset='utf8mb4',
                    autocommit=True,
                    cursorclass=DictCursor,
                    connect_timeout=5,
                )
                try:
                    with bootstrap.cursor() as cursor:
                        cursor.execute(
                            f'CREATE DATABASE IF NOT EXISTS `{self.name}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'
                        )
                    return
                finally:
                    bootstrap.close()
            except Exception as exc:
                last_exc = exc
                if attempt < 20:
                    time.sleep(3)
                    continue
                break
        raise RuntimeError(
            f'Failed to connect MySQL after retries host={self.host} port={self.port} user={self.user}'
        ) from last_exc

    def init_schema(self) -> None:
        with self._connection_scope() as connection:
            cursor = connection.cursor()
            try:
                schema_file = 'init.sqlite.sql' if self.driver == 'sqlite' else 'init.sql'
                init_sql_path = resource_path(f'database/{schema_file}')
                sql = init_sql_path.read_text(encoding='utf-8')
                if self.driver == 'sqlite':
                    cursor.executescript(sql)
                    try:
                        cursor.execute("PRAGMA table_info(t_strategy_daily)")
                        columns = [row[1] for row in cursor.fetchall()]
                        if 'ma10' not in columns:
                            cursor.execute("ALTER TABLE t_strategy_daily ADD COLUMN ma10 REAL")
                        if 'trend_reason' not in columns:
                            cursor.execute("ALTER TABLE t_strategy_daily ADD COLUMN trend_reason TEXT")
                        cursor.execute("PRAGMA table_info(t_sniper_daily)")
                        sniper_columns = [row[1] for row in cursor.fetchall()]
                        if 'chaos_index_val' not in sniper_columns:
                            cursor.execute("ALTER TABLE t_sniper_daily ADD COLUMN chaos_index_val REAL DEFAULT NULL")
                        if 'score_chaos' not in sniper_columns:
                            cursor.execute("ALTER TABLE t_sniper_daily ADD COLUMN score_chaos INTEGER NOT NULL DEFAULT 0")
                    except Exception as e:
                        print(f"[db migration] Failed to check/add columns: {e}")
                    connection.commit()
                    return
                for statement in [part.strip() for part in sql.split(';') if part.strip()]:
                    upper = statement.upper()
                    if upper.startswith('CREATE DATABASE') or upper.startswith('USE '):
                        continue
                    cursor.execute(statement)
                try:
                    cursor.execute("SHOW COLUMNS FROM t_strategy_daily LIKE 'ma10'")
                    if not cursor.fetchone():
                        cursor.execute("ALTER TABLE t_strategy_daily ADD COLUMN ma10 REAL")
                    cursor.execute("SHOW COLUMNS FROM t_strategy_daily LIKE 'trend_reason'")
                    if not cursor.fetchone():
                        cursor.execute("ALTER TABLE t_strategy_daily ADD COLUMN trend_reason TEXT")
                    cursor.execute("SHOW COLUMNS FROM t_sniper_daily LIKE 'chaos_index_val'")
                    if not cursor.fetchone():
                        cursor.execute("ALTER TABLE t_sniper_daily ADD COLUMN chaos_index_val DOUBLE DEFAULT NULL")
                    cursor.execute("SHOW COLUMNS FROM t_sniper_daily LIKE 'score_chaos'")
                    if not cursor.fetchone():
                        cursor.execute("ALTER TABLE t_sniper_daily ADD COLUMN score_chaos INT NOT NULL DEFAULT 0")
                except Exception as e:
                    print(f"[db migration] Failed to check/add columns in MySQL: {e}")
                connection.commit()
            finally:
                cursor.close()

    def drop_tables(self, tables: Sequence[str]) -> None:
        with self._connection_scope() as connection:
            cursor = connection.cursor()
            try:
                for table in tables:
                    cursor.execute(f'DROP TABLE IF EXISTS {table}')
                connection.commit()
            finally:
                cursor.close()

    def upsert_many(self, table: str, columns: Sequence[str], rows: Iterable[Sequence[object]], key_columns: Sequence[str]) -> int:
        placeholders = ', '.join([self.placeholder] * len(columns))
        update_columns = [c for c in columns if c not in key_columns]
        if self.driver == 'sqlite':
            if assignments := ', '.join([f"{col}=excluded.{col}" for col in update_columns]):
                sql = (
                    f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
                    f"ON CONFLICT({', '.join(key_columns)}) DO UPDATE SET {assignments}"
                )
            else:
                sql = f"INSERT OR IGNORE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
        else:
            assignments = ', '.join([f"{col}=VALUES({col})" for col in update_columns])
            sql = (
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
                f"ON DUPLICATE KEY UPDATE {assignments}"
            ) if assignments else (
                f"INSERT IGNORE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
            )
        total_rows = 0
        row_iter = iter(rows)
        for batch in self._chunk_iterable(row_iter, 1000):
            with self._connection_scope() as connection:
                cursor = connection.cursor()
                try:
                    cursor.executemany(sql, batch)
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                finally:
                    cursor.close()
            total_rows += len(batch)
        return total_rows

    @staticmethod
    def _chunk_iterable(rows: Iterator[Sequence[object]], size: int) -> Iterable[list[Sequence[object]]]:
        batch: list[Sequence[object]] = []
        for row in rows:
            batch.append(row)
            if len(batch) >= size:
                yield batch
                batch = []
        if batch:
            yield batch

    def fetch_count(self, table: str) -> int:
        sql = f'SELECT COUNT(1) AS c FROM {table}'
        with self._connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(sql)
                row = cursor.fetchone()
            finally:
                cursor.close()
        return int(row['c'])

    def fetch_one(self, sql: str, params: Sequence[object] = ()):
        sql = self.prepare_sql(sql)
        with self._connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(sql, params)
                row = cursor.fetchone()
            finally:
                cursor.close()
        return dict(row) if self.driver == 'sqlite' and row is not None else row

    def fetch_all(self, sql: str, params: Sequence[object] = ()):
        sql = self.prepare_sql(sql)
        with self._connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
            finally:
                cursor.close()
        return [dict(row) for row in rows] if self.driver == 'sqlite' else rows

    def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        sql = self.prepare_sql(sql)
        with self._connection_scope() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(sql, params)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()

    @property
    def placeholder(self) -> str:
        return '?' if self.driver == 'sqlite' else '%s'

    def placeholders(self, count: int) -> str:
        return ', '.join([self.placeholder] * count)

    def prepare_sql(self, sql: str) -> str:
        if self.driver != 'sqlite':
            return sql
        return sql.replace('%s', '?')

    def close(self) -> None:
        for connection in self._pool_connections:
            try:
                connection.close()
            except Exception:
                pass
        self._pool_connections = []
        self._pool = None
