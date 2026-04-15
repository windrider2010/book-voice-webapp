from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}


class ImageValidationError(ValueError):
    """Raised when uploaded image input is invalid."""


@dataclass(slots=True)
class NormalizedImage:
    image: Image.Image
    width: int
    height: int


def normalize_uploaded_image(
    raw_bytes: bytes,
    *,
    content_type: str | None,
    max_upload_bytes: int,
    image_max_side: int,
) -> NormalizedImage:
    if not raw_bytes:
        raise ImageValidationError("Image upload is empty.")
    if len(raw_bytes) > max_upload_bytes:
        raise ImageValidationError(f"Image exceeds the {max_upload_bytes} byte upload limit.")
    if content_type and content_type.lower() not in ALLOWED_IMAGE_TYPES:
        raise ImageValidationError(f"Unsupported image content type: {content_type}")

    try:
        with Image.open(io.BytesIO(raw_bytes)) as incoming:
            image = ImageOps.exif_transpose(incoming).convert("RGB")
    except UnidentifiedImageError as exc:
        raise ImageValidationError("Uploaded file is not a valid image.") from exc

    if max(image.size) > image_max_side:
        image.thumbnail((image_max_side, image_max_side), Image.Resampling.LANCZOS)

    return NormalizedImage(image=image, width=image.width, height=image.height)
