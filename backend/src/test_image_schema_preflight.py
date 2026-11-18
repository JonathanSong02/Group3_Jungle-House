"""Read-only deployment gate and redacted failure diagnostics; no real DB/HTTP."""
import unittest
from unittest.mock import Mock

import check_image_schema as check
from image_service_errors import failure_response


class ImageSchemaPreflightTests(unittest.TestCase):
    def connection(self, columns):
        cursor = Mock()
        cursor.fetchall.return_value = [{"TABLE_NAME": table, "COLUMN_NAME": column} for table, column in columns]
        conn = Mock()
        conn.cursor.return_value = cursor
        return conn, cursor

    def test_complete_schema_uses_only_information_schema_select(self):
        columns = [(table, column) for table, names in check.REQUIRED_COLUMNS.items() for column in names]
        conn, cursor = self.connection(columns)
        output = []
        self.assertEqual(check.main(lambda: conn, output.append), 0)
        sql = cursor.execute.call_args.args[0].strip()
        self.assertTrue(sql.startswith("SELECT "))
        self.assertIn("information_schema.COLUMNS", sql)
        self.assertEqual(cursor.execute.call_count, 1)
        conn.commit.assert_not_called()
        conn.close.assert_called_once()

    def test_missing_attachment_table_blocks_release_without_ddl(self):
        conn, cursor = self.connection([("image_retrieval", name) for name in check.REQUIRED_COLUMNS["image_retrieval"]])
        output = []
        self.assertEqual(check.main(lambda: conn, output.append), 1)
        self.assertIn("IMAGE_SCHEMA_NOT_READY", output[0])
        self.assertIn("chat_attachments.attachment_id", output[1])
        conn.commit.assert_not_called()
        cursor.close.assert_called_once()

    def test_connection_error_does_not_print_credentials(self):
        output = []
        def connect():
            raise RuntimeError("password=synthetic-private-value")
        self.assertEqual(check.main(connect, output.append), 2)
        self.assertNotIn("synthetic-private-value", " ".join(output))

    def test_safe_error_categories_and_correlation_id(self):
        for errno, code in [(1146, "IMAGE_SCHEMA_NOT_READY"), (1054, "IMAGE_SCHEMA_NOT_READY"),
                            (2003, "IMAGE_STORAGE_UNAVAILABLE"), (None, "IMAGE_PROCESSING_FAILED")]:
            with self.subTest(errno=errno):
                error = RuntimeError("password=synthetic-private-value")
                error.errno = errno
                logger = Mock()
                result = failure_response(error, logger, "attachment_register")
                self.assertEqual(result["code"], code)
                self.assertEqual(result["confidence_kind"], "not_calibrated")
                self.assertRegex(result["error_id"], r"^[a-f0-9]{16}$")
                self.assertNotIn("synthetic-private-value", str(result))
                self.assertNotIn("synthetic-private-value", str(logger.error.call_args))


if __name__ == "__main__":
    unittest.main()
