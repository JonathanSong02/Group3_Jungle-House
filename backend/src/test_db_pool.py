"""Database connection reuse ("线不挂断") in app.get_db_connection.

Extracts the real code from app.py (no app import, no database). Run:
python -m unittest discover -s backend/src -p test_db_pool.py
"""

import ast
import hashlib
import types
import unittest
from pathlib import Path

source = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
tree = ast.parse(source)
start = next(i for i, n in enumerate(tree.body)
             if isinstance(n, ast.Import) and n.names[0].asname == "db_pool_queue")
end = next(i for i, n in enumerate(tree.body)
           if isinstance(n, ast.FunctionDef) and n.name == "get_db_connection")
POOL_CODE = ast.Module(body=tree.body[start:end + 1], type_ignores=[])

ENV = {"DB_HOST": "db", "DB_USER": "u", "DB_PASSWORD": "p", "DB_NAME": "wiki"}


class FakeConnection:
    def __init__(self, number):
        self.number = number
        self.rollbacks = 0
        self.closed = False
        self.alive = True
        self.rollback_error = None

    def rollback(self):
        if self.rollback_error:
            raise self.rollback_error
        self.rollbacks += 1

    def is_connected(self):
        return self.alive

    def close(self):
        self.closed = True

    def cursor(self, **kwargs):
        return ("cursor", self.number, kwargs)


class PoolTests(unittest.TestCase):
    def load(self, pool_size="10", env=None):
        self.env_vars = dict(ENV if env is None else env)
        self.env_vars["DB_POOL_SIZE"] = pool_size
        self.opened = []
        self.clock = [1000.0]

        def connect(**kwargs):
            connection = FakeConnection(len(self.opened) + 1)
            connection.kwargs = kwargs
            self.opened.append(connection)
            return connection

        class Error(Exception):
            pass

        class OperationalError(Error):
            pass

        connector = types.SimpleNamespace(connect=connect, Error=Error,
                                          errors=types.SimpleNamespace(OperationalError=OperationalError))
        self.ns = {
            "os": types.SimpleNamespace(getenv=lambda key, default=None: self.env_vars.get(key, default)),
            "time": types.SimpleNamespace(monotonic=lambda: self.clock[0]),
            "hashlib": hashlib,
            "mysql": types.SimpleNamespace(connector=connector),
        }
        exec(compile(POOL_CODE, "db_pool.py", "exec"), self.ns)
        return self.ns["get_db_connection"]

    def test_closed_connection_is_reused(self):
        get = self.load()
        first = get()
        first.close()
        second = get()
        self.assertEqual(len(self.opened), 1)
        self.assertEqual(second.cursor(dictionary=True), ("cursor", 1, {"dictionary": True}))

    def test_two_requests_at_once_get_two_connections(self):
        get = self.load()
        first, second = get(), get()
        self.assertEqual(len(self.opened), 2)
        first.close()
        second.close()
        get(), get()
        self.assertEqual(len(self.opened), 2)

    def test_every_returned_connection_is_rolled_back(self):
        get = self.load()
        get().close()
        self.assertEqual(self.opened[0].rollbacks, 1)

    def test_closing_twice_is_harmless(self):
        get = self.load()
        connection = get()
        connection.close()
        connection.close()
        self.assertEqual(self.ns["_DB_POOL_IDLE"].qsize(), 1)
        self.assertFalse(self.opened[0].closed)

    def test_using_a_closed_connection_fails_like_before(self):
        get = self.load()
        connection = get()
        connection.close()
        with self.assertRaises(Exception):
            connection.cursor()

    def test_failed_rollback_closes_instead_of_reusing(self):
        get = self.load()
        connection = get()
        self.opened[0].rollback_error = RuntimeError("Unread result found")
        connection.close()   # never raises
        self.assertTrue(self.opened[0].closed)
        get()
        self.assertEqual(len(self.opened), 2)

    def test_long_idle_connection_is_checked_and_replaced_when_dead(self):
        get = self.load()
        get().close()
        self.opened[0].alive = False
        self.clock[0] += 31
        get()
        self.assertTrue(self.opened[0].closed)
        self.assertEqual(len(self.opened), 2)

    def test_long_idle_connection_still_alive_is_reused(self):
        get = self.load()
        get().close()
        self.clock[0] += 600
        get()
        self.assertEqual(len(self.opened), 1)

    def test_recent_connection_is_not_pinged(self):
        get = self.load()
        get().close()
        self.opened[0].is_connected = lambda: self.fail("pinged a connection returned a moment ago")
        get()

    def test_full_basket_really_closes(self):
        get = self.load(pool_size="2")
        connections = [get() for _ in range(3)]
        for connection in connections:
            connection.close()
        self.assertEqual(self.ns["_DB_POOL_IDLE"].qsize(), 2)
        self.assertEqual(sum(c.closed for c in self.opened), 1)

    def test_changed_settings_do_not_reuse_old_connections(self):
        get = self.load()
        get().close()
        self.env_vars["DB_HOST"] = "other-db"
        get()
        self.assertTrue(self.opened[0].closed)
        self.assertEqual(self.opened[1].kwargs["host"], "other-db")

    def test_setting_an_attribute_reaches_the_real_connection(self):
        get = self.load()
        connection = get()
        connection.autocommit = True
        self.assertTrue(self.opened[0].autocommit)

    def test_pool_size_zero_is_the_old_behaviour(self):
        get = self.load(pool_size="0")
        connection = get()
        self.assertIs(connection, self.opened[0])
        connection.close()
        self.assertTrue(self.opened[0].closed)
        get()
        self.assertEqual(len(self.opened), 2)

    def test_missing_settings_still_raise(self):
        get = self.load(env={})
        with self.assertRaises(RuntimeError):
            get()


if __name__ == "__main__":
    unittest.main()
