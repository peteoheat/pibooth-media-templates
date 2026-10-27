import pytest

from pibooth_media_templates.model import (load_template, load_templates, preset_slots, TemplateError)


def write(tmp_path, text, name='t.yaml'):
    path = tmp_path / name
    path.write_text(text, encoding='utf-8')
    return str(path)


def test_all_examples_load(examples):
    templates, errors = load_templates(str(examples))
    assert errors == []
    names = {t.name for t in templates}
    assert {'Classic', 'Sunset', 'Night Sky', 'Photo Strip', 'Four Up', 'Two Worlds',
            'Bounce', 'Wiggle', 'Reel'} == names


def test_two_single_options_have_different_backgrounds(examples):
    templates, _ = load_templates(str(examples))
    by_name = {t.name: t for t in templates}
    sunset, night = by_name['Sunset'], by_name['Night Sky']
    assert sunset.type == night.type == 'single'
    assert sunset.captures == night.captures == 1
    assert sunset.background_for(0) != night.background_for(0)
    assert sunset.needs_matting and night.needs_matting
    assert not by_name['Classic'].needs_matting


def test_slot_background_overrides_template_background(examples):
    templates, _ = load_templates(str(examples))
    two = next(t for t in templates if t.name == 'Two Worlds')
    assert two.background_for(0).endswith('sunset.jpg')
    assert two.background_for(1).endswith('night.jpg')


def test_fractions_and_pixels(tmp_path):
    template = load_template(write(tmp_path, """
type: collage
size: [1000, 2000]
slots:
  - {x: 0.1, y: 100, w: 0.5, h: 1.0}
"""))
    slot = template.slots[0]
    assert (slot.x, slot.y, slot.width, slot.height) == (100, 100, 500, 2000)


def test_disabled_by_flag_and_by_name(tmp_path):
    write(tmp_path, "name: A\nenabled: false\n", 'a.yaml')
    write(tmp_path, "name: B\n", 'b.yaml')
    write(tmp_path, "name: C\n", 'c.yaml')
    templates, _ = load_templates(str(tmp_path), disabled=['c'])
    assert [t.name for t in templates] == ['B']


@pytest.mark.parametrize('text, message', [
    ("type: hologram", "type must be"),
    ("type: collage", "slots"),
    ("type: animation\ncaptures: 5", "1 to 4"),
    ("type: animation\ncaptures: 1", "at least 2"),
    ("overlay: nope.png", "not found"),
    ("type: collage\nlayout: {preset: spiral}", "preset"),
    ("type: collage\nslots:\n  - {capture: 3}\ncaptures: 2", "uses capture 3"),
    ("type: single\ntexts:\n  - {text: hi}", "size"),
    ("::: not yaml :::\n  - [", "invalid YAML"),
])
def test_invalid_templates_are_rejected(tmp_path, text, message):
    with pytest.raises(TemplateError, match=message):
        load_template(write(tmp_path, text))


def test_a_broken_template_does_not_stop_the_others(tmp_path):
    write(tmp_path, "type: hologram\n", 'bad.yaml')
    write(tmp_path, "name: Fine\n", 'good.yaml')
    templates, errors = load_templates(str(tmp_path))
    assert [t.name for t in templates] == ['Fine']
    assert len(errors) == 1


@pytest.mark.parametrize('preset, count', [('single', 1), ('strip', 3), ('strip_h', 3), ('grid', 4), ('grid', 3)])
def test_preset_slots_stay_inside_the_canvas(preset, count):
    for x, y, w, h in preset_slots(preset, count, (1200, 1800), 60, 30, 0.05):
        assert x >= 60 and y >= 60 and w > 0 and h > 0
        assert x + w <= 1200 - 60 and y + h <= 1800 - 60


def test_folder_template_resolves_relative_paths(examples):
    template = load_template(str(examples / 'night_single'))
    assert template.background.startswith(str(examples / 'night_single'))


def test_icon_defaults_follow_the_type(tmp_path):
    from pibooth_media_templates.icons import DEFAULT_ICONS
    for kind, icon in DEFAULT_ICONS.items():
        extra = "\ncaptures: 2" if kind in ('animation', 'video', 'wigglegram') else ""
        extra += "\nlayout: {preset: grid}" if kind == 'collage' else ""
        template = load_template(write(tmp_path, "type: {}{}".format(kind, extra), kind + '.yaml'))
        assert template.icon_name == icon and template.icon is None


def test_icon_can_be_a_material_name_or_an_image_file(tmp_path):
    from PIL import Image
    Image.new('RGBA', (64, 64), (255, 255, 255, 255)).save(tmp_path / 'mine.png')
    named = load_template(write(tmp_path, "icon: celebration", 'a.yaml'))
    assert (named.icon, named.icon_name) == (None, 'celebration')
    pic = load_template(write(tmp_path, "icon: mine.png", 'b.yaml'))
    assert pic.icon.endswith('mine.png') and pic.icon_name is None


def test_unknown_icon_suggests_the_closest_names(tmp_path):
    with pytest.raises(TemplateError, match="did you mean photo_camera"):
        load_template(write(tmp_path, "icon: photo_camra"))


def test_missing_icon_file_is_an_error(tmp_path):
    with pytest.raises(TemplateError, match="not found"):
        load_template(write(tmp_path, "icon: nope.png"))


def test_tile_colour(tmp_path):
    assert load_template(write(tmp_path, "color: '#c0392b'")).color == (192, 57, 43)
    assert load_template(write(tmp_path, "name: x")).color is None
    with pytest.raises(TemplateError, match="colour"):
        load_template(write(tmp_path, "color: notacolour"))
