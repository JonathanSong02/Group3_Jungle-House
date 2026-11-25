"""Decode and normalize user avatars; never store original uploaded bytes."""
import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_AVATAR_BYTES = 5 * 1024 * 1024
MAX_AVATAR_PIXELS = 20_000_000
AVATAR_SIZE = 256
AVATAR_FORMATS = {"JPEG", "PNG", "WEBP"}


class AvatarValidationError(ValueError):
    pass


def normalize_avatar(data):
    if not data or len(data) > MAX_AVATAR_BYTES:
        raise AvatarValidationError("Invalid photo size.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in AVATAR_FORMATS:
                    raise AvatarValidationError("Unsupported image format.")
                width, height = image.size
                if width < 1 or height < 1 or width * height > MAX_AVATAR_PIXELS:
                    raise AvatarValidationError("Image dimensions exceed the limit.")
                if getattr(image, "is_animated", False):
                    raise AvatarValidationError("Animated images are not supported.")
                image.load()
                oriented = ImageOps.exif_transpose(image)
                square = ImageOps.fit(oriented.convert("RGBA"), (AVATAR_SIZE, AVATAR_SIZE),
                                      method=Image.Resampling.LANCZOS)
                flattened = Image.new("RGB", square.size, "white")
                flattened.paste(square, mask=square.getchannel("A"))
                output = io.BytesIO()
                flattened.save(output, format="JPEG", quality=85, optimize=True)
                return output.getvalue()
    except AvatarValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise AvatarValidationError("Invalid or unsupported image.") from exc
