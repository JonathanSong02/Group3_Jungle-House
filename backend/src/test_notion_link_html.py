"""Notion links in converted HTML: escaped, and only http:, https:, mailto: and Notion page links are kept.

Run (from backend/src):
    python -m unittest test_notion_link_html -v
"""

import os
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("NOTION_AUTO_SYNC_ENABLED", "false")

import notion_sync_service as svc  # noqa: E402


class Elements(HTMLParser):
    """Every start tag with its attributes, as the browser would read them."""

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs), len(attrs)))


def link_span(text, href, **annotations):
    return {"plain_text": text, "href": href, "annotations": annotations}


def rich(*spans):
    return svc.notion_rich_text_to_html(list(spans))


class RichTextLinkTests(unittest.TestCase):
    def anchors(self, html):
        return [(attrs, count) for tag, attrs, count in Elements(html).tags if tag == "a"]

    def test_a_normal_https_link_is_unchanged(self):
        self.assertEqual(
            rich(link_span("Opening SOP", "https://example.com/sop")),
            '<a href="https://example.com/sop" target="_blank" rel="noopener noreferrer">Opening SOP</a>',
        )

    def test_a_quote_in_the_link_cannot_add_attributes(self):
        html = rich(link_span("x", 'https://example.com/"onmouseover="alert(1)" x="'))
        (attrs, count), = self.anchors(html)
        self.assertEqual(count, 3)                                   # href, target, rel: nothing added
        self.assertEqual(attrs["href"], 'https://example.com/"onmouseover="alert(1)" x="')
        self.assertNotIn("onmouseover", attrs)
        self.assertIn("&quot;", html)

    def test_angle_brackets_and_ampersands_are_escaped(self):
        html = rich(link_span("q", "https://example.com/?a=1&b=<tag>"))
        self.assertIn('href="https://example.com/?a=1&amp;b=&lt;tag&gt;"', html)
        (attrs, _), = self.anchors(html)
        self.assertEqual(attrs["href"], "https://example.com/?a=1&b=<tag>")   # the browser reads the real URL

    def test_unsafe_links_become_plain_text(self):
        for href in ("javascript:alert(1)", "JavaScript:alert(1)", "java\tscript:alert(1)", " javascript:alert(1)",
                     "java\nscript:alert(1)", "vbscript:x", "data:text/html,<script>alert(1)</script>",
                     "file:///etc/passwd", "ftp://example.com", "www.example.com", "notion://www.notion.so/x"):
            with self.subTest(href=href):
                html = rich(link_span("click", href))
                self.assertEqual(html, "click")
                self.assertEqual(self.anchors(html), [])

    def test_notion_page_mentions_and_mailto_are_kept(self):
        (attrs, _), = self.anchors(rich(link_span("Page", "/21ca360a8b9c")))
        self.assertEqual(attrs["href"], "https://www.notion.so/21ca360a8b9c")
        (attrs, _), = self.anchors(rich(link_span("Mail", "mailto:help@junglehouse.com")))
        self.assertEqual(attrs["href"], "mailto:help@junglehouse.com")

    def test_link_text_is_still_escaped_and_formatting_kept(self):
        html = rich(link_span("<b>bold</b>", "https://example.com", bold=True))
        self.assertEqual(
            html,
            '<a href="https://example.com" target="_blank" rel="noopener noreferrer">'
            "<strong>&lt;b&gt;bold&lt;/b&gt;</strong></a>",
        )

    def test_text_without_a_link_is_unchanged(self):
        self.assertEqual(rich({"plain_text": "a < b & c", "annotations": {}}), "a &lt; b &amp; c")


class EmbedLinkTests(unittest.TestCase):
    def convert(self, block_type, url, caption=None):
        block = {"type": block_type, block_type: {"url": url, "caption": caption or []}}
        return svc.notion_blocks_to_html("token-not-used", [block], upload_folder=None)

    def test_a_normal_bookmark_is_unchanged(self):
        self.assertEqual(
            self.convert("bookmark", "https://youtu.be/abc"),
            '<p><a href="https://youtu.be/abc" target="_blank" rel="noopener noreferrer">https://youtu.be/abc</a></p>',
        )

    def test_a_quote_in_an_embed_url_cannot_add_attributes(self):
        html = self.convert("embed", 'https://example.com/"onclick="alert(1)')
        tags = Elements(html).tags
        (attrs, count), = [(attrs, count) for tag, attrs, count in tags if tag == "a"]
        self.assertEqual(count, 3)
        self.assertNotIn("onclick", attrs)
        self.assertNotIn('"onclick', html.replace("&quot;", ""))

    def test_an_unsafe_embed_url_becomes_escaped_plain_text(self):
        html = self.convert("video", "javascript:alert('<x>')")
        self.assertEqual(html, "<p>javascript:alert(&#x27;&lt;x&gt;&#x27;)</p>")
        self.assertEqual([tag for tag, _, _ in Elements(html).tags], ["p"])

    def test_a_caption_is_used_as_the_label(self):
        caption = [{"plain_text": "Watch <this>", "annotations": {}}]
        self.assertEqual(
            self.convert("video", "https://youtu.be/abc", caption),
            '<p><a href="https://youtu.be/abc" target="_blank" rel="noopener noreferrer">Watch &lt;this&gt;</a></p>',
        )


if __name__ == "__main__":
    unittest.main()
