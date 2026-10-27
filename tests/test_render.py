from PIL import Image

from pibooth_media_templates.model import load_templates
from pibooth_media_templates.render import MediaTemplateFactory, render


class FakeReplacer(object):

    """Stands in for MODNet: paints the whole capture with a colour derived
    from the background file so we can tell which background was used."""

    def __init__(self):
        self.calls = []

    def replace(self, image, background):
        self.calls.append(background)
        colour = (255, 0, 0) if 'sunset' in background or background.endswith('background.jpg') and 'sunset_single' in background else (0, 0, 255)
        return Image.new('RGB', image.size, colour)


def templates(examples):
    found, _ = load_templates(str(examples))
    return {t.name: t for t in found}


def test_single_keeps_capture_size_and_applies_overlay(examples, photos):
    tpl = templates(examples)['Classic']
    final, _ = render(tpl, photos[:1])
    assert final.size == photos[0].size
    assert final.getpixel((2, 2)) == (255, 255, 255)   # frame border painted over the photo
    assert final.getpixel((320, 180)) != (255, 255, 255)


def test_collage_has_the_template_size_and_fills_slots(examples, photos):
    tpl = templates(examples)['Photo Strip']
    final, processed = render(tpl, photos[:3])
    assert final.size == (600, 1800)
    assert len(processed) == 3
    for slot in tpl.slots:
        assert final.getpixel((slot.x + slot.width // 2, slot.y + slot.height // 2)) != tpl.canvas_color


def test_texts_are_drawn_with_the_date(examples, photos):
    tpl = templates(examples)['Photo Strip']
    plain, _ = render(tpl, photos[:3])
    tpl.texts = []
    without, _ = render(tpl, photos[:3])
    assert plain.tobytes() != without.tobytes()


def test_each_single_template_asks_for_its_own_background(examples, photos):
    found = templates(examples)
    replacer = FakeReplacer()
    render(found['Sunset'], photos[:1], replacer)
    render(found['Night Sky'], photos[:1], replacer)
    assert replacer.calls[0] != replacer.calls[1]
    assert 'sunset_single' in replacer.calls[0] and 'night_single' in replacer.calls[1]


def test_slots_use_their_own_background(examples, photos):
    replacer = FakeReplacer()
    render(templates(examples)['Two Worlds'], photos[:2], replacer)
    assert [c.rsplit('\\', 1)[-1].rsplit('/', 1)[-1] for c in replacer.calls] == ['sunset.jpg', 'night.jpg']


def test_no_replacer_leaves_captures_untouched(examples, photos):
    tpl = templates(examples)['Sunset']
    final, processed = render(tpl, photos[:1], None)
    assert processed[0].tobytes() == photos[0].tobytes()
    assert final.size == photos[0].size


def test_factory_matches_what_pibooth_calls(examples, photos, tmp_path):
    tpl = templates(examples)['Four Up']
    factory = MediaTemplateFactory(tpl, photos)
    factory.set_margin(100)
    factory.set_background('#fff')
    factory.set_overlay('x.png')
    factory.add_text('a', 'f', (0, 0, 0), 'center')
    factory.set_cropping()
    factory.set_outlines()
    path = tmp_path / 'out.jpg'
    image = factory.save(str(path))
    assert path.exists() and image.size == (1800, 1200)
    assert factory.build() is image  # cached
    assert factory._images == tuple(photos)


def test_rotated_slot(tmp_path, photos):
    (tmp_path / 't.yaml').write_text("type: collage\nsize: [800, 800]\ncanvas: {color: '#000000'}\n"
                                     "slots:\n  - {x: 0.25, y: 0.25, w: 0.5, h: 0.5, rotation: 20}\n")
    found, errors = load_templates(str(tmp_path))
    assert not errors
    final, _ = render(found[0], photos[:1])
    assert final.size == (800, 800)
    assert final.getpixel((5, 5)) == (0, 0, 0)  # corners stay canvas colour
