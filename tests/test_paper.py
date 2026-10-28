"""Paper size: pictures made for a printer such as the Canon SELPHY CP1300 (postcard, 100 x 148 mm, 300 dpi)."""

import pytest
from PIL import Image

from pibooth_media_templates.model import load_template, load_templates
from pibooth_media_templates.render import MediaTemplateFactory, Paper, parse_paper, render


def make(tmp_path, text, name='t.yaml'):
    path = tmp_path / name
    path.write_text(text, encoding='utf-8')
    return load_template(str(path))


def test_parse_paper():
    assert parse_paper('') is None and parse_paper('off') is None
    assert parse_paper('postcard') == Paper(100.0, 148.0, 300, 'auto')
    assert parse_paper('"Postcard"', 600, 'cover') == Paper(100.0, 148.0, 600, 'cover')
    assert parse_paper('148x100') == Paper(100.0, 148.0, 300, 'auto')       # orientation is ignored
    assert parse_paper('4x6').height_mm == 152.4
    assert parse_paper('4x6in').width_mm == 101.6
    with pytest.raises(ValueError):
        parse_paper('a4ish')
    with pytest.raises(ValueError):
        parse_paper('postcard', fit='stretch')


def test_landscape_single_becomes_exact_postcard_pixels(tmp_path, photos):
    tpl = make(tmp_path, "type: single\ncanvas: {color: '#00ff00'}")
    final, _ = render(tpl, photos[:1], paper=parse_paper('postcard'))
    assert final.size == (1748, 1181)                      # 148 x 100 mm at 300 dpi, landscape
    assert final.getpixel((900, 2)) != (0, 255, 0)         # a 3:2 photo is cropped to fill: no bars


def test_footer_band_and_overlay_still_make_an_exact_postcard(tmp_path, photos):
    footer = [("London Science Museum", None, (255, 0, 0), 'center')]
    for text in ("type: single\nfooter: {mode: band}", "type: single\nframe: null"):
        tpl = make(tmp_path, text)
        final, _ = render(tpl, photos[:1], footer_texts=footer, paper=parse_paper('postcard'))
        assert final.size == (1748, 1181)
        band = final.crop((0, 1181 - 1181 // 8, final.width, 1181))
        reds = [i % band.width for i, (r, g, b) in enumerate(band.getdata()) if r > 200 and g < 60 and b < 60]
        assert reds and min(reds) > 20 and max(reds) < final.width - 20   # text sits inside the picture


def test_portrait_collage_is_padded_not_squashed(tmp_path, photos):
    tpl = make(tmp_path, "type: collage\ncaptures: 3\nsize: [600, 1800]\ncanvas: {color: '#00ff00'}\n"
                         "layout: {preset: strip, margin: 30, gap: 20}")
    final, _ = render(tpl, photos[:3], paper=parse_paper('postcard'))
    assert final.size == (1181, 1748)
    assert final.getpixel((5, 5)) == (0, 255, 0)           # side bars in the canvas colour
    assert final.getpixel((590, 874)) != (0, 255, 0)       # the strip stays whole in the middle


def test_paper_fit_can_be_forced(tmp_path, photos):
    tpl = make(tmp_path, "type: single\ncanvas: {color: '#00ff00'}")
    padded, _ = render(tpl, photos[:1], paper=parse_paper('postcard', fit='contain'))
    assert padded.size == (1748, 1181) and padded.getpixel((900, 3)) == (0, 255, 0)


def test_no_paper_keeps_the_template_size(tmp_path, photos):
    final, _ = render(make(tmp_path, "type: single"), photos[:1])
    assert final.size == photos[0].size


def test_factory_saves_with_the_paper_dpi(tmp_path, photos):
    factory = MediaTemplateFactory(make(tmp_path, "type: single"), photos[:1], paper=parse_paper('postcard'))
    path = tmp_path / 'out.jpg'
    factory.save(str(path))
    with Image.open(path) as saved:
        assert saved.size == (1748, 1181)
        assert round(saved.info['dpi'][0]) == 300


def test_every_example_fits_the_postcard(examples, photos):
    found, _ = load_templates(str(examples))
    for tpl in found:
        if tpl.type in ('single', 'collage'):
            final, _ = render(tpl, photos[:tpl.captures], paper=parse_paper('postcard'))
            assert sorted(final.size) == [1181, 1748], tpl.name


# --- through the plugin ------------------------------------------------------

pytest.importorskip('pibooth')
import pibooth_media_templates as plugin  # noqa: E402
from test_plugin import booth, pick, build  # noqa: E402,F401


def test_print_size_in_the_config_fits_the_picture_to_the_paper(booth):
    booth.cfg.set('MEDIA_TEMPLATES', 'print_size', 'postcard')
    plugin.CTRL.__init__()
    booth.hook.pibooth_startup(cfg=booth.cfg, app=booth.app)
    assert plugin.CTRL.paper.width_mm == 100.0 and plugin.CTRL.paper.dpi == 300
    pick(booth, 'Four Up')
    assert build(booth, 4).build().size == (1748, 1181)


def test_a_bad_print_size_is_reported_and_ignored(booth):
    booth.cfg.set('MEDIA_TEMPLATES', 'print_size', 'huge')
    plugin.CTRL.__init__()
    booth.hook.pibooth_startup(cfg=booth.cfg, app=booth.app)
    assert plugin.CTRL.paper is None and plugin.CTRL.active
