"""Browser caching of /static/ files (2026-11-25, speed).

Calls the real after_request hook from app.py on hand-made responses, so no
database, login or files are needed. Run:
python -m unittest discover -s backend/src -p test_static_cache.py
"""

import os
import unittest

os.environ.setdefault("FLASK_SECRET_KEY", "dummy-test-only-key-not-a-secret-0123456789")
os.environ.setdefault("NOTION_AUTO_SYNC_ENABLED", "false")
os.environ.setdefault("IMAGE_INDEX_WORKER_ENABLED", "false")
os.environ.setdefault("DOCUMENT_TEXT_BACKFILL", "false")

import app as app_module  # noqa: E402

app = app_module.app


def headers_for(path, status=200, method="GET"):
    with app.test_request_context(path, method=method):
        response = app.response_class(b"x", status=status)
        response = app_module.prevent_private_static_caching(response)
        return response.headers


class StaticCacheTests(unittest.TestCase):
    def test_article_image_kept_by_the_browser_only_for_ten_minutes(self):
        headers = headers_for("/static/uploads/articles/1_abc_photo.png")
        self.assertEqual(headers["Cache-Control"], "private, max-age=600")
        self.assertNotIn("Pragma", headers)
        # Vary: Cookie would defeat it: the session cookie changes every request.
        self.assertNotIn("Cookie", headers.get("Vary", ""))
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_public_sop_image_is_kept_too(self):
        self.assertEqual(headers_for("/static/sop_images/step1.jpg")["Cache-Control"], "private, max-age=600")

    def test_chat_uploads_are_never_kept(self):
        headers = headers_for("/static/uploads/chat/7/abc.png")
        self.assertEqual(headers["Cache-Control"], "private, no-store, max-age=0")
        self.assertIn("Cookie", headers["Vary"])

    def test_errors_and_denied_files_are_never_kept(self):
        for status in (401, 403, 404, 503, 206, 304):
            with self.subTest(status=status):
                headers = headers_for("/static/uploads/articles/x.png", status=status)
                self.assertEqual(headers["Cache-Control"], "private, no-store, max-age=0")
                self.assertEqual(headers["Pragma"], "no-cache")

    def test_api_responses_are_untouched(self):
        headers = headers_for("/api/articles")
        self.assertNotIn("max-age=600", headers.get("Cache-Control", ""))

    def test_zero_turns_it_off(self):
        original = app_module.STATIC_BROWSER_CACHE_SECONDS
        app_module.STATIC_BROWSER_CACHE_SECONDS = 0
        try:
            headers = headers_for("/static/uploads/articles/x.png")
            self.assertEqual(headers["Cache-Control"], "private, no-store, max-age=0")
        finally:
            app_module.STATIC_BROWSER_CACHE_SECONDS = original


if __name__ == "__main__":
    unittest.main()
