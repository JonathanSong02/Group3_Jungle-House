"""Tests for reading PDF / Word attachment text. No database, network or AI.
Run: python -m unittest discover -s backend/src -p test_document_text_service.py
"""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import document_text_service as dts


def make_pdf(text):
    """A minimal real PDF with one line of text (no extra libraries)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return out


def make_docx(path, paragraphs, table_cell=None):
    import docx
    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    if table_cell:
        document.add_table(rows=1, cols=1).cell(0, 0).text = table_cell
    document.save(str(path))


class FakeCursor:
    """Answers the statements sync_article uses and records writes."""
    def __init__(self, existing=None, stored_text="Stored text"):
        # file_url -> file_hash, or file_url -> (file_hash, status, needs_summary)
        self.existing = {url: (v if isinstance(v, tuple) else (v, "ok", 0)) for url, v in dict(existing or {}).items()}
        self.stored_text = stored_text
        self.upserts = []
        self.deletes = []
        self.summary_updates = []
        self._rows = []

    def execute(self, sql, params=()):
        text = " ".join(sql.split())
        if text.startswith("SELECT file_url, file_hash"):
            self._rows = [{"file_url": url, "file_hash": h, "status": st, "needs_summary": ns}
                          for url, (h, st, ns) in self.existing.items()]
        elif text.startswith("SELECT text FROM article_attachment_text"):
            self._rows = [{"text": self.stored_text}]
        elif text.startswith("INSERT INTO article_attachment_text"):
            self.upserts.append(params)
        elif text.startswith("UPDATE article_attachment_text SET summary"):
            self.summary_updates.append(params)
        elif text.startswith("DELETE FROM article_attachment_text"):
            self.deletes.append(params)
        else:
            raise AssertionError("unexpected SQL: " + text)

    def fetchall(self):
        return self._rows


class DocumentTextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        path = self.folder / name
        path.write_bytes(data)
        return path

    # ---- extract_text ----
    def test_pdf_text_extracted(self):
        path = self.write("guide.pdf", make_pdf("Kiosk opening needs the cash drawer key"))
        status, text = dts.extract_text(path)
        self.assertEqual(status, "ok")
        self.assertIn("cash drawer key", text)

    def test_docx_text_and_table_extracted(self):
        path = self.folder / "policy.docx"
        make_docx(path, ["Refund policy", "Refunds within 7 days"], table_cell="Manager approval needed")
        status, text = dts.extract_text(path)
        self.assertEqual(status, "ok")
        self.assertIn("Refunds within 7 days", text)
        self.assertIn("Manager approval needed", text)

    def test_missing_file(self):
        self.assertEqual(dts.extract_text(self.folder / "gone.pdf"), ("missing", ""))

    def test_old_doc_and_images_unsupported(self):
        for name in ["old.doc", "photo.png"]:
            path = self.write(name, b"whatever")
            with self.subTest(name=name):
                self.assertEqual(dts.extract_text(path)[0], "unsupported")

    def test_corrupt_pdf_is_error_not_crash(self):
        path = self.write("broken.pdf", b"%PDF-1.4 this is not really a pdf")
        self.assertIn(dts.extract_text(path)[0], {"error", "empty"})

    def test_pdf_with_no_text_is_empty(self):
        path = self.write("scan.pdf", make_pdf(""))
        self.assertEqual(dts.extract_text(path)[0], "empty")

    def test_text_is_capped(self):
        path = self.folder / "long.docx"
        make_docx(path, ["word " * 5000] * 20)
        status, text = dts.extract_text(path, max_chars=1000)
        self.assertEqual(status, "ok")
        self.assertLessEqual(len(text), 1000)

    # ---- document_files ----
    def test_document_files_from_image_files_json(self):
        article = {"image_files": json.dumps([
            {"url": "/static/uploads/articles/1_a_guide.pdf", "type": "application/pdf"},
            {"url": "/static/uploads/articles/2_b_photo.png", "type": "image/png"},
            {"url": "/static/uploads/articles/3_c_policy.DOCX", "type": "x"},
            {"url": "/static/uploads/articles/4_d_old.doc", "type": "x"},
            {"url": "https://example.com/remote.pdf", "type": "application/pdf"},
            {"url": "/static/uploads/articles/../secret.pdf", "type": "application/pdf"},
        ]), "attachment_url": None}
        self.assertEqual(dts.document_files(article), [
            "/static/uploads/articles/1_a_guide.pdf",
            "/static/uploads/articles/3_c_policy.DOCX",
        ])

    def test_document_files_falls_back_to_attachment_url(self):
        article = {"image_files": None, "attachment_url": "/static/uploads/articles/9_x_manual.pdf"}
        self.assertEqual(dts.document_files(article), ["/static/uploads/articles/9_x_manual.pdf"])

    def test_document_files_from_article_content_links(self):
        # Notion-synced files are linked inside the article HTML with an absolute URL.
        article = {"image_files": json.dumps([{"url": "/static/uploads/articles/1_a_guide.pdf"}]),
                   "attachment_url": None,
                   "content": '<p><a href="https://api.example.app/static/uploads/articles/99_notion_import.pdf" '
                              'target="_blank">Attached file</a></p><a href="/static/uploads/articles/5_x_rules.docx">r</a>'
                              '<img src="https://api.example.app/static/uploads/articles/7_notion_import.png">'
                              '<a href="/static/uploads/articles/1_a_guide.pdf">dup</a>'}
        self.assertEqual(dts.document_files(article), [
            "/static/uploads/articles/1_a_guide.pdf",
            "/static/uploads/articles/99_notion_import.pdf",
            "/static/uploads/articles/5_x_rules.docx",
        ])

    def test_document_files_bad_json(self):
        self.assertEqual(dts.document_files({"image_files": "{not json", "attachment_url": None}), [])

    # ---- best_passages ----
    def test_best_passages_picks_matching_passage(self):
        text = ("Opening hours are nine to six. " * 30) + "The cash drawer key is kept in the safe. " + ("Uniform rules apply. " * 30)
        excerpt = dts.best_passages(text, {"cash", "drawer", "key"}, limit=300)
        self.assertIn("cash drawer key", excerpt)
        self.assertLessEqual(len(excerpt), 300)

    def test_best_passages_no_match_is_empty(self):
        self.assertEqual(dts.best_passages("Nothing relevant here.", {"refund"}, limit=300), "")

    # ---- sync_article ----
    def test_sync_upserts_new_and_deletes_removed(self):
        pdf = self.write("1_a_guide.pdf", make_pdf("Closing checklist"))
        article = {"article_id": 7, "attachment_url": None, "image_files": json.dumps(
            [{"url": "/static/uploads/articles/1_a_guide.pdf", "type": "application/pdf"}])}
        cursor = FakeCursor(existing={"/static/uploads/articles/old.pdf": "abc"})
        dts.sync_article(cursor, article, self.folder)
        self.assertEqual(len(cursor.upserts), 1)
        article_id, url, file_hash, status, text, summary = cursor.upserts[0]
        self.assertEqual((article_id, url, status), (7, "/static/uploads/articles/1_a_guide.pdf", "ok"))
        self.assertEqual(file_hash, hashlib.sha256(pdf.read_bytes()).hexdigest())
        self.assertIn("Closing checklist", text)
        self.assertEqual(cursor.deletes, [(7, "/static/uploads/articles/old.pdf")])

    def test_sync_skips_unchanged_file(self):
        pdf = self.write("1_a_guide.pdf", make_pdf("Closing checklist"))
        url = "/static/uploads/articles/1_a_guide.pdf"
        article = {"article_id": 7, "attachment_url": url, "image_files": None}
        cursor = FakeCursor(existing={url: hashlib.sha256(pdf.read_bytes()).hexdigest()})
        dts.sync_article(cursor, article, self.folder)
        self.assertEqual(cursor.upserts, [])
        self.assertEqual(cursor.deletes, [])

    def test_new_file_summarised_once(self):
        self.write("1_a_guide.pdf", make_pdf("Lab ten covers resistors"))
        calls = []
        def summarize(text):
            calls.append(text)
            return "  A lab manual about resistors.  "
        cursor = FakeCursor()
        dts.sync_article(cursor, {"article_id": 7, "attachment_url": "/static/uploads/articles/1_a_guide.pdf",
                                  "image_files": None}, self.folder, summarize=summarize)
        self.assertEqual(len(calls), 1)
        self.assertIn("resistors", calls[0])
        self.assertEqual(cursor.upserts[0][5], "A lab manual about resistors.")

    def test_unchanged_file_without_summary_gets_one(self):
        pdf = self.write("1_a_guide.pdf", make_pdf("Closing checklist"))
        url = "/static/uploads/articles/1_a_guide.pdf"
        cursor = FakeCursor(existing={url: (hashlib.sha256(pdf.read_bytes()).hexdigest(), "ok", 1)})
        dts.sync_article(cursor, {"article_id": 7, "attachment_url": url, "image_files": None},
                         self.folder, summarize=lambda text: "Summary of " + text)
        self.assertEqual(cursor.upserts, [])
        self.assertEqual(cursor.summary_updates, [("Summary of Stored text", 7, url)])

    def test_unchanged_file_with_summary_not_resummarised(self):
        pdf = self.write("1_a_guide.pdf", make_pdf("Closing checklist"))
        url = "/static/uploads/articles/1_a_guide.pdf"
        cursor = FakeCursor(existing={url: (hashlib.sha256(pdf.read_bytes()).hexdigest(), "ok", 0)})
        dts.sync_article(cursor, {"article_id": 7, "attachment_url": url, "image_files": None},
                         self.folder, summarize=lambda text: self.fail("should not summarise"))
        self.assertEqual(cursor.summary_updates, [])

    def test_summary_failure_keeps_text(self):
        self.write("1_a_guide.pdf", make_pdf("Closing checklist"))
        def summarize(text):
            raise RuntimeError("AI down")
        cursor = FakeCursor()
        dts.sync_article(cursor, {"article_id": 7, "attachment_url": "/static/uploads/articles/1_a_guide.pdf",
                                  "image_files": None}, self.folder, summarize=summarize)
        self.assertEqual(cursor.upserts[0][3], "ok")
        self.assertIsNone(cursor.upserts[0][5])

    def test_no_summary_for_empty_or_missing(self):
        self.write("1_scan.pdf", make_pdf(""))
        cursor = FakeCursor()
        dts.sync_article(cursor, {"article_id": 7, "attachment_url": "/static/uploads/articles/1_scan.pdf",
                                  "image_files": None}, self.folder, summarize=lambda text: self.fail("no text"))
        self.assertIsNone(cursor.upserts[0][5])

    def test_sync_records_missing_file(self):
        url = "/static/uploads/articles/1_gone.pdf"
        cursor = FakeCursor()
        dts.sync_article(cursor, {"article_id": 3, "attachment_url": url, "image_files": None}, self.folder)
        self.assertEqual(cursor.upserts[0][3], "missing")


class LoadCacheTests(unittest.TestCase):
    class Cursor:
        def __init__(self, rows):
            self.rows, self.queries = rows, 0
        def execute(self, sql, params=()):
            self.queries += 1
        def fetchall(self):
            return self.rows

    def setUp(self):
        dts.invalidate_cache()

    def test_texts_reused_within_max_age(self):
        cursor = self.Cursor([{"article_id": 1, "text": "a"}, {"article_id": 1, "text": "b"}])
        self.assertEqual(dts.load_texts(cursor), {1: "a b"})
        self.assertEqual(dts.load_texts(cursor), {1: "a b"})
        self.assertEqual(cursor.queries, 1)

    def test_sync_invalidates_cache(self):
        cursor = self.Cursor([{"article_id": 1, "text": "old"}])
        dts.load_texts(cursor)
        sync_cursor = FakeCursor()
        dts.sync_article(sync_cursor, {"article_id": 1, "attachment_url": "/static/uploads/articles/1_x.pdf",
                                       "image_files": None}, Path(tempfile.gettempdir()))
        cursor.rows = [{"article_id": 1, "text": "new"}]
        self.assertEqual(dts.load_texts(cursor), {1: "new"})

    def test_load_documents_lists_files_with_names_and_summaries(self):
        cursor = self.Cursor([
            {"article_id": 1, "file_url": "/static/uploads/articles/1700000000000_a1b2c3_Lab_10_Manual.pdf",
             "status": "ok", "text": "lab text", "summary": "A lab manual."},
            {"article_id": 1, "file_url": "/static/uploads/articles/1700000000001_notion_import.pdf",
             "status": "empty", "text": "", "summary": None},
            {"article_id": 2, "file_url": "/static/uploads/articles/1700000000002_abc123_rules.docx",
             "status": "ok", "text": "rules", "summary": None},
        ])
        docs = dts.load_documents(cursor)
        self.assertEqual(docs[1]["text"], "lab text")
        self.assertEqual([f["name"] for f in docs[1]["files"]], ["Lab_10_Manual.pdf", "notion_import.pdf"])
        self.assertEqual(docs[1]["files"][0]["summary"], "A lab manual.")
        self.assertEqual(docs[1]["files"][1]["status"], "empty")
        self.assertEqual(docs[2]["files"][0]["name"], "rules.docx")

    def test_max_age_zero_always_reads(self):
        cursor = self.Cursor([])
        dts.load_texts(cursor, max_age=0)
        dts.load_texts(cursor, max_age=0)
        self.assertEqual(cursor.queries, 2)


if __name__ == "__main__":
    unittest.main()
