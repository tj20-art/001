"""Bounded autocommit connections for fresh, independent SELECT operations.

Writer connections/transactions stay separate. No user, stock or auth-version
results are cached, so a committed role/reset/stock update is visible immediately.
"""
from contextlib import contextmanager
from queue import Queue, Empty
import time
import pymysql


class ReadConnectionPool:
    def __init__(self, config, size=2, timeout=5):
        self._config = {k: config[k] for k in ['host','port','user','password','db','charset']}
        self._slots = Queue(maxsize=size)
        self._timeout = timeout
        self._closed = False
        for _ in range(size): self._slots.put((None, 0))

    @contextmanager
    def cursor(self, *, consistent=False):
        if self._closed:
            raise RuntimeError('Read connection pool is closed')
        try:
            conn, used = self._slots.get(timeout=self._timeout)
        except Empty as exc:
            raise TimeoutError('Read connection pool is busy') from exc
        try:
            if conn is not None and time.monotonic()-used > 30:
                try:
                    conn.ping(reconnect=False)
                except pymysql.MySQLError:
                    conn.close()
                    conn = None
            if conn is None:
                conn = pymysql.connect(**self._config, autocommit=True,
                    connect_timeout=5, read_timeout=15, write_timeout=15,
                    init_command='SET SESSION TRANSACTION READ ONLY',
                    cursorclass=pymysql.cursors.DictCursor)
            if consistent:
                conn.begin()
            with conn.cursor() as cursor:
                yield cursor
            if consistent:
                conn.commit()
        except Exception:
            if conn is not None:
                try: conn.close()
                finally: conn = None
            raise
        finally:
            if self._closed:
                if conn is not None: conn.close()
            else:
                self._slots.put((conn, time.monotonic()))

    def close(self):
        self._closed = True
        while True:
            try: conn, _ = self._slots.get_nowait()
            except Empty: break
            if conn is not None: conn.close()
