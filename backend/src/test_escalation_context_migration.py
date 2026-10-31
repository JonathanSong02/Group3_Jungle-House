"""Isolated pre-deploy checks: no Flask import, credentials or live database.

Run: python -m unittest discover -s backend/src -p test_escalation_context_migration.py
"""

import contextlib
import io
import json
import os
import re
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import migrate_escalation_context as migration


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.cursor = Mock()
        self.connection = Mock()
        self.connection.cursor.return_value = self.cursor
        self.cursor.fetchone.side_effect = [
            {"selected_database": "isolated_test"},
            {"COLUMN_TYPE": "int", "COLUMN_KEY": "PRI", "ENGINE": "InnoDB"},
        ]
        self.cursor.fetchall.return_value = [
            {"COLUMN_NAME": name} for name in migration.REQUIRED_COLUMNS
        ]

    def test_creates_only_reviewed_sidecar_table(self):
        migration.migrate(self.connection)
        queries = [call.args[0] for call in self.cursor.execute.call_args_list]
        ddl = [query for query in queries if "CREATE TABLE" in query]
        self.assertEqual(ddl, [migration.CREATE_CONTEXT_TABLE])
        self.assertFalse(any(re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER)\b", query)
                             for query in queries if query not in ddl))
        self.cursor.close.assert_called_once()

    def test_redeploy_uses_idempotent_ddl(self):
        self.cursor.fetchone.side_effect = [
            {"selected_database": "isolated_test"},
            {"COLUMN_TYPE": "int(11)", "COLUMN_KEY": "PRI", "ENGINE": "InnoDB"},
        ] * 2
        migration.migrate(self.connection)
        migration.migrate(self.connection)
        self.assertEqual(sum(call.args[0] == migration.CREATE_CONTEXT_TABLE
                             for call in self.cursor.execute.call_args_list), 2)
        self.assertIn("CREATE TABLE IF NOT EXISTS", migration.CREATE_CONTEXT_TABLE)

    def test_missing_target_or_parent_never_runs_ddl(self):
        for rows in ([{"selected_database": None}],
                     [{"selected_database": "isolated_test"}, None]):
            with self.subTest(rows=rows):
                self.cursor.reset_mock()
                self.cursor.fetchone.side_effect = rows
                with self.assertRaises(migration.MigrationError):
                    migration.migrate(self.connection)
                self.assertFalse(any("CREATE TABLE" in call.args[0]
                                     for call in self.cursor.execute.call_args_list))
                self.cursor.close.assert_called_once()

    def test_incompatible_parent_never_runs_ddl(self):
        for changes in ({"COLUMN_TYPE": "int unsigned"}, {"COLUMN_TYPE": "bigint"},
                        {"COLUMN_KEY": ""}, {"ENGINE": "MyISAM"}):
            with self.subTest(changes=changes):
                self.cursor.reset_mock()
                parent = {"COLUMN_TYPE": "int", "COLUMN_KEY": "PRI", "ENGINE": "InnoDB"}
                parent.update(changes)
                self.cursor.fetchone.side_effect = [{"selected_database": "isolated_test"}, parent]
                with self.assertRaises(migration.MigrationError):
                    migration.migrate(self.connection)
                self.assertFalse(any("CREATE TABLE" in call.args[0]
                                     for call in self.cursor.execute.call_args_list))

    def test_existing_incomplete_table_is_not_silently_accepted(self):
        self.cursor.fetchall.return_value = [{"COLUMN_NAME": "escalation_id"}]
        with self.assertRaisesRegex(migration.MigrationError, "manual review"):
            migration.migrate(self.connection)
        self.cursor.close.assert_called_once()

    def test_embedded_ddl_matches_reviewed_sql(self):
        sql_path = Path(__file__).resolve().parents[2] / "mysql" / "escalation_context.sql"
        sql = re.sub(r"--[^\n]*", "", sql_path.read_text(encoding="utf-8"))
        normalize = lambda text: " ".join(text.strip().rstrip(";").split())
        self.assertEqual(normalize(sql), normalize(migration.CREATE_CONTEXT_TABLE))

    def test_railway_runs_migration_before_start(self):
        config = json.loads(Path(__file__).with_name("railway.json").read_text(encoding="utf-8"))
        self.assertEqual(config["deploy"]["preDeployCommand"],
                         ["python src/migrate_escalation_context.py"])


class CommandTests(unittest.TestCase):
    def run_command(self, env, error=None):
        connector = types.ModuleType("mysql.connector")
        connector.connect = Mock(side_effect=error)
        mysql = types.ModuleType("mysql")
        mysql.connector = connector
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = Mock()
        output = io.StringIO()
        with patch.dict(os.environ, env, clear=True), patch.dict("sys.modules", {
            "mysql": mysql, "mysql.connector": connector, "dotenv": dotenv,
        }), contextlib.redirect_stderr(output):
            code = migration.main()
        return code, output.getvalue(), connector

    def test_missing_configuration_does_not_connect(self):
        code, output, connector = self.run_command({})
        self.assertEqual(code, 1)
        self.assertIn("MYSQL_DATABASE", output)
        connector.connect.assert_not_called()

    def test_invalid_port_does_not_connect(self):
        code, output, connector = self.run_command({
            "MYSQL_HOST": "test.invalid", "MYSQL_USER": "test",
            "MYSQL_PASSWORD": "test-only", "MYSQL_DATABASE": "isolated_test", "MYSQL_PORT": "0",
        })
        self.assertEqual(code, 1)
        self.assertIn("MYSQL_PORT", output)
        connector.connect.assert_not_called()

    def test_driver_failure_logs_only_numeric_code(self):
        error = RuntimeError("sensitive-driver-detail")
        error.errno = 1142
        code, output, _ = self.run_command({
            "MYSQL_HOST": "test.invalid", "MYSQL_USER": "test",
            "MYSQL_PASSWORD": "test-only", "MYSQL_DATABASE": "isolated_test",
        }, error)
        self.assertEqual(code, 1)
        self.assertIn("1142", output)
        self.assertNotIn("sensitive-driver-detail", output)
        self.assertNotIn("test-only", output)


if __name__ == "__main__":
    unittest.main()
