"""Notion file download keeps the right extension, so Word files can be read.
No network: requests.get is replaced. Run:
python -m unittest discover -s backend/src -p test_notion_file_download.py
"""

import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("NOTION_AUTO_SYNC_ENABLED", "false")
import notion_sync_service as nss  # noqa: E402


def fake_response(content_type):
    return types.SimpleNamespace(content=b"data", headers={"Content-Type": content_type},
                                 raise_for_status=lambda: None)


class NotionFileDownloadTests(unittest.TestCase):
    def download(self, content_type, url="https://files.notion.so/abc/file?X-Amz=1"):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(nss.requests, "get", return_value=fake_response(content_type)), \
                patch.object(nss, "get_public_base_url", return_value="https://api.example.app"):
            hosted = nss.download_and_host_notion_file(url, Path(folder))
            saved = os.listdir(folder)
        return hosted, saved

    def test_existing_types_unchanged(self):
        for content_type, ext in [("image/jpeg", "jpg"), ("image/gif", "gif"), ("application/pdf", "pdf"),
                                  ("image/png", "png"), ("application/octet-stream", "png")]:
            with self.subTest(content_type=content_type):
                hosted, saved = self.download(content_type)
                self.assertTrue(hosted.endswith("." + ext))
                self.assertTrue(saved[0].endswith("." + ext))

    def test_word_docx_kept_as_docx(self):
        hosted, _ = self.download("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.assertTrue(hosted.endswith(".docx"))

    def test_old_word_kept_as_doc(self):
        hosted, _ = self.download("application/msword")
        self.assertTrue(hosted.endswith(".doc"))

    def test_extension_from_url_when_type_is_generic(self):
        hosted, _ = self.download("application/octet-stream",
                                  url="https://prod-files.s3.amazonaws.com/x/Lab%2010%20Manual.docx?sig=1")
        self.assertTrue(hosted.endswith(".docx"))
        hosted, _ = self.download("binary/octet-stream", url="https://s3.amazonaws.com/x/Guide.PDF?sig=1")
        self.assertTrue(hosted.endswith(".pdf"))


if __name__ == "__main__":
    unittest.main()
