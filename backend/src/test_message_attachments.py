"""Isolated attachment tests; no app import, background workers or shared database.

Run from backend: python -m unittest discover -s src -p test_message_attachments.py
"""
import ast
import io
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from flask import Flask, jsonify, send_from_directory
from werkzeug.datastructures import FileStorage
import message_attachment_service as service


class MessageAttachmentsTests(unittest.TestCase):
    def test_save_preserves_display_name_and_uses_random_storage_name(self):
        with tempfile.TemporaryDirectory() as folder:
            cursor = Mock()
            file = FileStorage(stream=io.BytesIO(b"test file"), filename="../团队截图.png")
            path = service.save_attachment(cursor, 12, file, folder, "image/png")
            self.assertEqual(path.read_bytes(), b"test file")
            self.assertRegex(path.name, r"^[a-f0-9]{64}$")
            values = cursor.execute.call_args.args[1]
            self.assertEqual(values[1], 12)
            self.assertEqual(values[3], "团队截图.png")
            self.assertEqual(values[5], 9)

    def test_failed_metadata_insert_removes_saved_file(self):
        with tempfile.TemporaryDirectory() as folder:
            cursor = Mock()
            cursor.execute.side_effect = RuntimeError("Synthetic database failure")
            with self.assertRaises(RuntimeError):
                service.save_attachment(cursor, 12,
                    FileStorage(stream=io.BytesIO(b"test"), filename="x.pdf"), folder, "application/pdf")
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_metadata_is_grouped_by_message(self):
        cursor = Mock()
        reference = "a" * 64
        cursor.fetchall.return_value = [{"attachment_id": reference, "message_id": 12,
            "name": "x.pdf", "type": "application/pdf", "size": 10}]
        messages = [{"message_id": 11}, {"message_id": 12}]
        service.add_attachments(cursor, messages)
        self.assertEqual(messages[0]["attachments"], [])
        self.assertEqual(messages[1]["attachments"][0]["url"], "/api/messages/attachments/" + reference)
        self.assertEqual(cursor.execute.call_args.args[1], (11, 12))

    def make_download_handler(self, folder, row):
        # Exercise the actual route body without importing app.py or starting its workers.
        module = ast.parse(Path(__file__).with_name("app.py").read_text(encoding="utf-8"))
        route = next(node for node in module.body if isinstance(node, ast.FunctionDef)
                     and node.name == "get_message_attachment")
        route.decorator_list = []
        cursor = Mock()
        cursor.fetchone.return_value = row
        connection = Mock()
        connection.cursor.return_value = cursor
        scope = dict(re=re, jsonify=jsonify, send_from_directory=send_from_directory,
            MESSAGE_UPLOAD_FOLDER=Path(folder), get_db_connection=lambda: connection,
            current_auth_user_id=lambda: 42)
        exec(compile(ast.Module(body=[route], type_ignores=[]), "app.py", "exec"), scope)
        return scope["get_message_attachment"], cursor

    def test_download_requires_visible_participating_message(self):
        handler, cursor = self.make_download_handler("unused", None)
        with Flask(__name__).test_request_context():
            response, status = handler("a" * 64)
            self.assertEqual(status, 404)
            self.assertEqual(response.json["message"], "Attachment not found.")
        sql, params = cursor.execute.call_args.args
        self.assertIn("m.is_deleted_by_sender = FALSE", sql)
        self.assertIn("m.is_deleted_by_receiver = FALSE", sql)
        self.assertEqual(params, ("a" * 64, 42, 42))
        cursor.close.assert_called_once()

    def test_document_download_is_private_and_forced_download(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "a" * 64).write_bytes(b"synthetic PDF")
            handler, _ = self.make_download_handler(folder, {
                "storage_name": "a" * 64, "mime_type": "application/pdf", "original_name": "guide.pdf"})
            with Flask(__name__).test_request_context():
                response = handler("a" * 64)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["Cache-Control"], "private, no-store")
                self.assertTrue(response.headers["Content-Disposition"].startswith("attachment;"))
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                response.close()

    def test_invalid_reference_never_queries_database(self):
        handler, cursor = self.make_download_handler("unused", None)
        with Flask(__name__).test_request_context():
            self.assertEqual(handler("../anything")[1], 404)
        cursor.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
