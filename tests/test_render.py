from PIL import Image

from pibooth_media_templates.model import load_template, load_templates
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
    without, _ = render(tpl, photos[:3])
    path = examples / 'strip_dated.yaml'
    path.write_text("type: collage\ncaptures: 3\nsize: [600, 1800]\nlayout: {preset: strip}\n"
                    "texts:\n  - {text: '{date:%d %B %Y}', y: 0.02, h: 0.04, color: '#ff0000'}\n", encoding='utf-8')
    dated, _ = render(load_template(str(path)), photos[:3])
    assert dated.size == without.size and dated.tobytes() != without.tobytes()


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


def test_slot_overlay_covers_its_capture_and_the_template_overlay_covers_all(tmp_path, photos):
    Image.new('RGBA', (10, 10), (0, 255, 0, 255)).save(tmp_path / 'slot.png')
    Image.new('RGBA', (10, 10), (0, 0, 0, 0)).save(tmp_path / 'clear.png')
    text = ("type: collage\nsize: [800, 400]\ncanvas: {color: '#000000'}\n"
            "slots:\n  - {capture: 1, x: 0, y: 0, w: 0.5, h: 1.0, overlay: slot.png}\n"
            "  - {capture: 2, x: 0.5, y: 0, w: 0.5, h: 1.0}\n")
    final, _ = render(make(tmp_path, text), photos[:2])
    assert final.getpixel((200, 200)) == (0, 255, 0)   # the first capture only
    assert final.getpixel((600, 200)) != (0, 255, 0)

    Image.new('RGBA', (10, 10), (255, 0, 255, 255)).save(tmp_path / 'all.png')
    final, _ = render(make(tmp_path, text + "overlay: all.png\n", name='u.yaml'), photos[:2])
    assert final.getpixel((200, 200)) == (255, 0, 255)  # the whole-image overlay is on top


# --- pibooth's [PICTURE] footer texts, and the template's own texts ---------

FOOTER = [("London Science Museum", None, (255, 0, 0), 'center'),
          ("STEM Skills Fair 2026", None, (0, 0, 255), 'center')]


def make(tmp_path, text, name='t.yaml'):
    path = tmp_path / name
    path.write_text(text, encoding='utf-8')
    return load_template(str(path))


def red_pixels(image, box=None):
    region = image.crop(box) if box else image
    return sum(1 for r, g, b in region.getdata() if r > 200 and g < 60 and b < 60)


def test_footer_overlay_is_drawn_on_the_photo(tmp_path, photos):
    tpl = make(tmp_path, "type: single")
    plain, _ = render(tpl, photos[:1])
    final, _ = render(tpl, photos[:1], footer_texts=FOOTER)
    assert final.size == plain.size                       # drawn over the picture
    assert red_pixels(final, (0, 300, 640, 360)) > 50     # in the bottom band
    assert red_pixels(final, (0, 0, 640, 200)) == red_pixels(plain, (0, 0, 640, 200))


def test_footer_band_extends_a_single_photo(tmp_path, photos):
    tpl = make(tmp_path, "type: single\ncanvas: {color: '#ffffff'}\nfooter: {mode: band}")
    final, _ = render(tpl, photos[:1], footer_texts=FOOTER)
    assert final.width == 640 and final.height == 360 + 360 // 8   # landscape: an eighth
    assert final.getpixel((2, final.height - 2)) == (255, 255, 255)


def test_footer_band_keeps_a_frame_overlay_on_the_photo(examples, photos):
    tpl = templates(examples)['Classic']
    tpl.footer['mode'] = 'band'
    final, _ = render(tpl, photos[:1], footer_texts=FOOTER)
    assert final.height > photos[0].height
    assert final.getpixel((2, 2)) == (255, 255, 255)      # the frame is still on the photo


def test_preset_collage_makes_room_for_the_footer(examples, photos):
    tpl = templates(examples)['Photo Strip']
    without, _ = render(tpl, photos[:3])
    final, _ = render(tpl, photos[:3], footer_texts=FOOTER)
    assert final.size == without.size == (600, 1800)
    band = 1800 // 6                                      # portrait: a sixth
    assert red_pixels(final, (0, 1800 - band, 600, 1800)) > 50
    assert final.getpixel((300, 1800 - band - 5)) == tpl.canvas_color   # photos stop above the band


def test_footer_can_be_switched_off_per_template(tmp_path, photos):
    tpl = make(tmp_path, "type: single\nfooter: false")
    plain, _ = render(tpl, photos[:1])
    final, _ = render(tpl, photos[:1], footer_texts=FOOTER)
    assert final.tobytes() == plain.tobytes()


def test_empty_footer_texts_change_nothing(tmp_path, photos):
    tpl = make(tmp_path, "type: single\nfooter: {mode: band}")
    final, _ = render(tpl, photos[:1], footer_texts=[("", None, (0, 0, 0), 'center')] * 2)
    assert final.size == photos[0].size


def test_second_footer_text_keeps_its_place_when_the_first_is_empty(tmp_path, photos):
    tpl = make(tmp_path, "type: single")
    only_second = [("", None, (255, 0, 0), 'center'), ("Hello", None, (255, 0, 0), 'center')]
    both = [("Top", None, (255, 0, 0), 'center'), ("Hello", None, (255, 0, 0), 'center')]
    a, _ = render(tpl, photos[:1], footer_texts=only_second)
    b, _ = render(tpl, photos[:1], footer_texts=both)
    assert red_pixels(a) > 0 and red_pixels(b) > red_pixels(a)


def test_template_texts_position_against_the_real_photo(tmp_path, photos):
    tpl = make(tmp_path, "type: single\ntexts:\n"
                         "  - {text: Hello, x: 0.0, y: 0.0, w: 1.0, h: 0.2, color: '#ff0000'}")
    final, _ = render(tpl, photos[:1])
    assert red_pixels(final, (0, 0, 640, 72)) > 50
    assert red_pixels(final, (0, 200, 640, 360)) == 0


def test_font_size_text_and_date_time_placeholders(tmp_path, photos):
    from datetime import datetime
    from pibooth_media_templates.render import default_context
    tpl = make(tmp_path, "type: single\ntexts:\n"
                         "  - {text: '{date} {time} {name}', x: 10, y: 10, font_size: 30, align: left, color: '#ff0000'}")
    context = default_context(tpl, datetime(2026, 10, 27, 14, 3, 11))
    assert "{date:%d %B %Y}".format(**context) == "27 October 2026"
    assert str(context['date']) == datetime(2026, 10, 27).strftime('%x')
    assert str(context['time']) == datetime(2026, 10, 27, 14, 3, 11).strftime('%X')
    final, _ = render(tpl, photos[:1], context=context)
    assert red_pixels(final, (0, 0, 640, 80)) > 30


def test_factory_collects_pibooths_footer_texts(tmp_path, photos):
    tpl = make(tmp_path, "type: single")
    factory = MediaTemplateFactory(tpl, photos[:1])
    plain = factory.build()
    factory.add_text("London Science Museum", "Amatic-Bold", (255, 0, 0), 'center')
    assert factory._final is None                           # rebuilt with the text
    assert red_pixels(factory.build(), (0, 300, 640, 360)) > 20
    assert red_pixels(plain, (0, 300, 640, 360)) == 0
