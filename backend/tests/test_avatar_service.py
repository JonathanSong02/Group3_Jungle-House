import io
import sys
import unittest
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from avatar_service import normalize_avatar, AvatarValidationError, MAX_AVATAR_BYTES

class AvatarTests(unittest.TestCase):
    def test_supported_formats_are_normalized(self):
        for fmt in ("JPEG", "PNG", "WEBP"):
            with self.subTest(fmt=fmt):
                raw = io.BytesIO()
                Image.new("RGB", (640, 480), "green").save(raw, format=fmt)
                with Image.open(io.BytesIO(normalize_avatar(raw.getvalue()))) as photo:
                    self.assertEqual(photo.size, (256, 256))
                    self.assertEqual(photo.format, "JPEG")
                    self.assertFalse(photo.getexif())

    def test_invalid_and_oversized_inputs(self):
        for data in (b"", b"not an image", b"<svg/>", b"x" * (MAX_AVATAR_BYTES + 1)):
            with self.subTest(size=len(data)):
                with self.assertRaises(AvatarValidationError):
                    normalize_avatar(data)

    def test_gif_is_rejected(self):
        raw = io.BytesIO()
        Image.new("RGB", (8, 8)).save(raw, format="GIF")
        with self.assertRaises(AvatarValidationError):
            normalize_avatar(raw.getvalue())

if __name__ == "__main__":
    unittest.main()
