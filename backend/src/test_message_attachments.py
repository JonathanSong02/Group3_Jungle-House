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

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.datastructures import FileStorage, MultiDict
import message_attachment_service as service


class MessageAttachmentsTests(unittest.TestCase):
    def attachment_validator(self):
        module = ast.parse(Path(__file__).with_name("app.py").read_text(encoding="utf-8"))
        node = next(node for node in module.body if isinstance(node, ast.FunctionDef)
                    and node.name == "_validate_message_attachment")
        scope = dict(request=request, jsonify=jsonify, message_attachment_service=service,
                     UploadValidationError=ValueError,
                     validate_uploaded_file=Mock(return_value="image/png"))
        exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), scope)
        return scope["_validate_message_attachment"], scope["validate_uploaded_file"]

    def test_real_attachment_validator_accepts_text_only_requests(self):
        validator, inspect_file = self.attachment_validator()
        app = Flask(__name__)
        with app.test_request_context(json={"message": "Text only"}):
            self.assertEqual(validator(), (None, None, None))
        with app.test_request_context(data={"message": "Text only"}, content_type="multipart/form-data"):
            self.assertEqual(validator(), (None, None, None))
        inspect_file.assert_not_called()

    def test_real_attachment_validator_accepts_one_file(self):
        validator, inspect_file = self.attachment_validator()
        with Flask(__name__).test_request_context(data={
            "attachment": (io.BytesIO(b"synthetic image"), "image.png"), "message": "Image caption"
        }):
            file, mime, error = validator()
            self.assertIsNone(error)
            self.assertEqual(file.filename, "image.png")
            self.assertEqual(file.stream.tell(), 0)
            self.assertEqual(mime, "image/png")
            inspect_file.assert_called_once_with(file)

    def test_real_attachment_validator_rejects_multiple_files_including_same_field(self):
        for keys in (("attachment", "attachment"), ("attachment", "other")):
            with self.subTest(keys=keys):
                validator, inspect_file = self.attachment_validator()
                data = MultiDict((key, (io.BytesIO(b"synthetic"), "image.png")) for key in keys)
                with Flask(__name__).test_request_context(data=data):
                    file, mime, error = validator()
                    self.assertIsNone(file)
                    self.assertIsNone(mime)
                    self.assertEqual(error[1], 400)
                inspect_file.assert_not_called()

    def test_missing_optional_table_leaves_text_messages_readable(self):
        cursor = Mock()
        error = RuntimeError("Synthetic missing table")
        error.errno = 1146
        cursor.execute.side_effect = error
        messages = [{"message_id": 1, "message": "Text still works"}]
        self.assertIs(service.add_attachments(cursor, messages), messages)
        self.assertEqual(messages[0]["attachments"], [])
        cursor.fetchall.assert_not_called()

    def test_unrelated_database_errors_are_not_hidden(self):
        cursor = Mock()
        error = RuntimeError("Synthetic connection failure")
        error.errno = 2013
        cursor.execute.side_effect = error
        with self.assertRaises(RuntimeError):
            service.add_attachments(cursor, [{"message_id": 1}])

    def test_missing_table_upload_reports_schema_error_and_cleans_file(self):
        with tempfile.TemporaryDirectory() as folder:
            cursor = Mock()
            error = RuntimeError("Synthetic missing table")
            error.errno = 1146
            cursor.execute.side_effect = error
            with self.assertRaises(service.AttachmentSchemaNotReady):
                service.save_attachment(cursor, 1,
                    FileStorage(stream=io.BytesIO(b"test"), filename="x.pdf"), folder, "application/pdf")
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_text_send_and_reply_commit_without_attachment_table(self):
        module = ast.parse(Path(__file__).with_name("app.py").read_text(encoding="utf-8"))
        for name in ("send_message", "reply_message"):
            with self.subTest(route=name):
                cursor = Mock(lastrowid=12)
                error = RuntimeError("Synthetic missing table")
                error.errno = 1146

                def execute(sql, params):
                    if "FROM message_attachments" in sql:
                        raise error

                cursor.execute.side_effect = execute
                connection = Mock()
                connection.cursor.return_value = cursor
                node = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == name)
                node.decorator_list = []
                scope = dict(request=request, jsonify=jsonify, message_attachment_service=service,
                    get_db_connection=lambda: connection, current_auth_user_id=lambda: 1,
                    _validate_message_attachment=self.attachment_validator()[0],
                    _message_payload=lambda *_: {"message_id": 12, "message": "Text still works"})
                exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), scope)
                with Flask(__name__).test_request_context(json={
                    "receiver_id": 2, "subject": "Direct message", "message": "Text still works", "thread_id": 10
                }):
                    response, status = scope[name]()
                self.assertEqual(status, 201)
                self.assertEqual(response.json["sent_message"]["attachments"], [])
                connection.commit.assert_called_once()
                connection.rollback.assert_not_called()

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
