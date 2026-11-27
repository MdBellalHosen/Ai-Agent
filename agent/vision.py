"""Prepares a photo or screenshot for the model."""
import base64
import io
from pathlib import Path


def image_url(picture):
    from PIL import Image
    if isinstance(picture, (str, Path)):
        picture = Image.open(picture)
    picture = picture.convert("RGB")
    picture.thumbnail((1600, 1600))
    buffer = io.BytesIO()
    picture.save(buffer, "JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
