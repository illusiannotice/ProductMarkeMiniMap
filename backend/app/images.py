import warnings
from dataclasses import dataclass
from typing import BinaryIO

from PIL import Image, UnidentifiedImageError

ALLOWED_FORMATS: dict[str, tuple[str, str]] = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
}


class InvalidImageError(Exception):
    pass


class ImageTooLargeError(InvalidImageError):
    pass


@dataclass(frozen=True)
class ImageInfo:
    extension: str
    content_type: str
    size: int


def file_size(fileobj: BinaryIO) -> int:
    fileobj.seek(0, 2)
    size = fileobj.tell()
    fileobj.seek(0)
    return size


def inspect_image(fileobj: BinaryIO, max_bytes: int, max_pixels: int) -> ImageInfo:
    """Identify the image by decoding its bytes; the client-declared content type is ignored."""
    size = file_size(fileobj)
    if size == 0:
        raise InvalidImageError("image is empty")
    if size > max_bytes:
        raise ImageTooLargeError("image is too large")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(fileobj, formats=list(ALLOWED_FORMATS)) as image:
                image_format = image.format
                width, height = image.size
                if width * height > max_pixels:
                    raise ImageTooLargeError("image dimensions are too large")
                image.verify()
    except InvalidImageError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise InvalidImageError("unsupported image") from exc
    except (OSError, SyntaxError, ValueError) as exc:
        raise InvalidImageError("corrupted image") from exc
    finally:
        fileobj.seek(0)

    if image_format not in ALLOWED_FORMATS:
        raise InvalidImageError("unsupported image format")
    extension, content_type = ALLOWED_FORMATS[image_format]
    return ImageInfo(extension=extension, content_type=content_type, size=size)
