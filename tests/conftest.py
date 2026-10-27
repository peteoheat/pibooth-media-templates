import os

import pytest
from PIL import Image, ImageDraw

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

from pibooth_media_templates.examples import write_examples  # noqa: E402


@pytest.fixture
def examples(tmp_path):
    folder = tmp_path / 'templates'
    write_examples(str(folder))
    return folder


def make_photo(size=(640, 360), shade=0):
    """A photo with a bright 'guest' blob so shifts and crops are visible."""
    image = Image.new('RGB', size, (40 + shade, 90, 160))
    draw = ImageDraw.Draw(image)
    cx, cy = size[0] // 2, size[1] // 2
    draw.ellipse((cx - 60, cy - 90, cx + 60, cy + 90), fill=(230, 200, 170))
    draw.rectangle((10, 10, 70, 50), fill=(255, 0, 0))
    return image


@pytest.fixture
def photos():
    return [make_photo(shade=i * 20) for i in range(4)]
