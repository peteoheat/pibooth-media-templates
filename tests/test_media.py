import shutil

import pytest
from PIL import Image, ImageSequence

from pibooth_media_templates.model import load_templates
from pibooth_media_templates import media
from conftest import make_photo


def get(examples, name):
    found, _ = load_templates(str(examples))
    return next(t for t in found if t.name == name)


def test_animation_gif_boomerang(examples, photos, tmp_path):
    tpl = get(examples, 'Bounce')
    path = media.generate_media(tpl, photos, str(tmp_path / 'anim'))
    assert path.endswith('.gif')
    with Image.open(path) as gif:
        frames = list(ImageSequence.Iterator(gif))
        assert len(frames) == 6                       # 4 + 2 coming back
        assert gif.info['loop'] == 0 and gif.info['duration'] == 350
        assert max(gif.size) == 640 or max(gif.size) == 800


def test_animation_webp(examples, photos, tmp_path):
    tpl = get(examples, 'Bounce')
    tpl.media['format'] = 'webp'
    path = media.generate_media(tpl, photos, str(tmp_path / 'anim'))
    assert path.endswith('.webp')
    with Image.open(path) as image:
        assert image.n_frames == 6


def test_ping_pong():
    assert media.ping_pong([1, 2, 3]) == [1, 2, 3, 2]
    assert media.ping_pong([1, 2]) == [1, 2]
    assert media.ping_pong([1, 2, 3, 4]) == [1, 2, 3, 4, 3, 2]


@pytest.mark.skipif(media.cv2 is None, reason="needs OpenCV")
def test_wigglegram_aligns_the_subject(examples, tmp_path):
    # Same scene shot from slightly different positions: the guest moves 12 px each frame
    from PIL import ImageChops
    base = make_photo((640, 360))
    frames = [ImageChops.offset(base, 12 * i, 0) for i in range(3)]
    aligned = media.align_frames(frames)

    def guest_x(image):
        row = image.convert('RGB').crop((0, 180, image.width, 181))
        xs = [x for x in range(row.width) if row.getpixel((x, 0)) == (230, 200, 170)]
        return (xs[0] + xs[-1]) / 2

    before = [guest_x(f) for f in frames]
    after = [guest_x(f) for f in aligned]
    assert max(before) - min(before) >= 20
    assert max(after) - min(after) <= 2          # the subject stays still
    assert aligned[0].width < frames[0].width    # borders cropped


def test_wigglegram_output(examples, tmp_path):
    tpl = get(examples, 'Wiggle')
    path = media.generate_media(tpl, [make_photo(shade=i) for i in range(3)], str(tmp_path / 'wig'))
    with Image.open(path) as gif:
        assert gif.n_frames == 4                    # 1 2 3 2
        assert gif.info['duration'] == 140


@pytest.mark.skipif(media.cv2 is None and not shutil.which('ffmpeg'), reason="needs ffmpeg or OpenCV")
def test_video_is_written(examples, photos, tmp_path):
    tpl = get(examples, 'Reel')
    tpl.media.update(size=320, fps=10, frame_s=0.3, fade_s=0.2)
    path = media.generate_media(tpl, photos, str(tmp_path / 'reel'))
    assert path.endswith('.mp4')
    assert (tmp_path / 'reel.mp4').stat().st_size > 1000
    if media.cv2 is not None:
        capture = media.cv2.VideoCapture(path)
        assert capture.isOpened() and capture.get(media.cv2.CAP_PROP_FRAME_COUNT) >= 12
        capture.release()


def test_still_templates_make_no_extra_file(examples, photos, tmp_path):
    assert media.generate_media(get(examples, 'Four Up'), photos, str(tmp_path / 'x')) is None
