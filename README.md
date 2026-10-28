# pibooth-media-templates

photobooth-app style **media templates** for [pibooth](https://github.com/pibooth/pibooth) 2.1.x.

pibooth's own layouts only let a guest pick 1, 2, 3 or 4 captures, and pibooth-picture-template needs hand-drawn
XML. Here each template is a small YAML file, and every enabled template appears as an **icon on the wait screen**.
A template can be a single photo, a collage, an animation, a video or a wigglegram, each with its own background,
overlay and texts. So you can offer, say, two single-photo options with different replaced backgrounds.

## Install

```bash
pip install pibooth-media-templates
pip install pibooth-modnet          # optional: lets templates replace the camera background
sudo apt install ffmpeg             # optional: H.264 video templates
sudo apt install python3-opencv     # optional: wigglegram alignment (or: pip install opencv-python-headless)
```

On first start nine example templates are written to `~/.config/pibooth/media_templates/`. Run
`pibooth-media-templates init` to (re)create them, or copy one and edit it.

## Using it

* Frosted-glass icon tiles float over the bottom of the wait screen (like photobooth-app's home screen), each with
  a white icon and the template name. **Touch a tile** to pick it and start the sequence.
* **Left / right arrow keys** change the selection; your normal capture button starts with the selected template.
* The choice is kept for the next guest (`keep_selection = False` returns to the default each time).
* Set `[WINDOW] arrows = top` in pibooth if the bottom arrows clash with the bar, or set `bar_position = top`.
* If `pibooth-modnet` is also installed its own theme picker is switched off; templates handle backgrounds.

## Template format

A template is `name.yaml`, or a folder containing `template.yaml` and its images. Relative paths resolve against
that folder.

```yaml
name: Sunset                 # label under the icon
enabled: true                # false hides it
type: single                 # single | collage | animation | video | wigglegram
captures: 1                  # 1-4 (single is always 1)
icon: photo_camera           # a Material icon name (see below), or an image file such as icon.png
color: "#c0392b"             # optional tile colour (default: frosted blue)
background: background.jpg   # replaces what is behind the guests (needs pibooth-modnet)
overlay: frame.png           # transparent PNG, stretched over the picture
```

**Icons.** As in photobooth-app, `icon` is the name of a Google Material icon: pick one at
[fonts.google.com/icons](https://fonts.google.com/icons) and use its lower-case name (`celebration`,
`wb_twilight`, `family_restroom`, ...). If you leave it out, the type decides: `photo_camera` (single),
`auto_awesome_mosaic` (collage), `gif` (animation), `movie` (video), `3d_rotation` (wigglegram). A value containing
a dot or slash (`icon.png`, `icons/party.png`) is an image file instead; it is cropped to a square and drawn as is, so
use a white line icon on a transparent background to match. Unknown names are rejected with suggestions
(`unknown icon 'photo_camra', did you mean photo_camera?`).

The icons come from the classic Material Icons fonts bundled with the plugin (about 2,200 icons, outlined or filled
via `icon_style`, Apache-2.0). A few newer additions that appear on fonts.google.com, such as `animated_images` and
`3d`, are not in them; use the older equivalent (`gif`, `3d_rotation`) or an image file.

**Layouts (collage, or any type that needs a canvas).** Use a preset or list slots explicitly:

```yaml
type: collage
size: [600, 1800]                       # canvas pixels
canvas: {color: "#101018"}              # or image: paper.jpg
layout: {preset: strip, margin: 30, gap: 20, footer: 0.07}   # single | strip | strip_h | grid
# or:
slots:
  - {capture: 1, x: 0.05, y: 0.03, w: 0.9, h: 0.46, fit: cover, rotation: 0, background: sunset.jpg}
  - {capture: 2, x: 0.05, y: 0.51, w: 0.9, h: 0.46, background: night.jpg}
texts:
  - {text: "{date:%d %B %Y}", y: 0.93, h: 0.05, color: "#ffffff", align: center, font: null}
```

Numbers written as floats from 0 to 1 are a fraction of the canvas; whole numbers are pixels. A slot's
`background` overrides the template's; `background: false` keeps the camera background for that slot. Text may use
`{date}` (strftime formats allowed) and `{name}`. Without `slots` or `layout`, a template is "native": the capture
itself is the picture (with overlay).

**Multi-frame types** write an extra file next to the picture, with the same name
(`2026-10-27-14-03-11_pibooth.gif`):

| type | options | output |
|---|---|---|
| `animation` | `format: gif\|webp`, `frame_ms`, `boomerang`, `size` | looping GIF/WebP |
| `wigglegram` | `frame_ms`, `align`, `size`, `format` | aligned ping-pong GIF/WebP |
| `video` | `fps`, `frame_s`, `fade_s`, `size` | MP4 slideshow with cross-fades |

The still picture pibooth shows and prints for these types is the template's layout (or the first capture).
On the print, finish and wait screens the frames are played as a loop (the saved `.jpg` is still what is
printed).

## Text

There are two kinds of text, and they can be used together.

**1. pibooth's footer: `[PICTURE]` in `pibooth.cfg`, unchanged.** `footer_text1`, `footer_text2`, `text_colors`,
`text_fonts` and `text_alignments` work as before, including `{date}` and `{count}`
(`footer_text2 = "{date:%d %B %Y}"`). The text is auto-sized to fit, and laid out as in pibooth: two lines stacked
in a portrait picture, side by side in a landscape one, in a band a sixth (portrait) or an eighth (landscape) of the
picture's height. Where the band goes depends on the template:

| template | default | what happens |
|---|---|---|
| `single`, `animation`... (the capture is the picture) | `overlay` | drawn over the bottom of the photo |
| collage from a `layout: {preset: ...}` | `band` | the photos make room, so nothing is covered |
| collage from explicit `slots` | `overlay` | drawn over the bottom of the canvas; leave the bottom sixth (portrait) or eighth (landscape) free |

Change it per template with `footer`:

```yaml
footer: false                       # ignore pibooth's footer text in this template
footer: {mode: band}                # add a strip under a single photo, in the canvas colour (white by default)
footer: {mode: overlay, height: 0.15, margin: 40}   # band height / margin: fraction of the picture, or pixels
```

Footer text gets a thin outline in a contrasting colour so it stays readable over photos and white margins alike.

The footer is a still-picture feature: animations, wigglegrams and videos stay clean, as in photobooth-app. The
default text colour in `[PICTURE]` is black; set `text_colors = (255, 255, 255)` for white text over photos.
`margin_thick` and `captures_cropping` no longer apply: a template sets its own `layout.margin` and each slot's `fit`.

**2. A template's own `texts`, as in photobooth-app.** Any number of texts, anywhere on the picture, on any still
template (a single photo needs no `size`):

```yaml
texts:
  - {text: "{date:%d %B %Y}", x: 0.0, y: 0.02, w: 1.0, h: 0.06, align: center, color: "#ffffff"}
  - {text: "{name} {time}", x: 40, y: 40, font_size: 48, align: left, font: Amatic-Bold, rotation: -5}
```

`x`, `y`, `w`, `h` are fractions of the picture (floats from 0 to 1) or pixels. Without `font_size` the text is
fitted to its box; with it, the text is that many pixels tall and `w`/`h` only position it. `font` is a pibooth font
name or a font file path. Placeholders: `{date}` and `{time}` (as photobooth-app, locale format, or
`{date:%d %B %Y}`), `{name}` (the template) and pibooth's `{count}`.

## Command line

```bash
pibooth-media-templates init [FOLDER]            # write the examples
pibooth-media-templates check [FOLDER]           # validate every template
pibooth-media-templates preview TEMPLATE a.jpg b.jpg -o out/ [--no-background]
```

`preview` renders on any computer, so you can design templates without the booth.

## Configuration (`[MEDIA_TEMPLATES]`)

`enabled`, `templates_path`, `disabled` (names, comma separated), `default`, `keep_selection`, `bar_position`,
`bar_height` (default 0.2 of the window), `show_labels`, `icon_style` (`outlined` or `filled`), plus `model_path`, `inference_size`, `threads`, `refine_edges` for backgrounds (the
model file is shared with pibooth-modnet), and `print_size`, `print_dpi`, `print_fit` (see below).

## Printing: paper size

pibooth sends the saved picture to CUPS as it is, so a picture of the wrong shape is scaled or cropped by the
printer driver. Set `print_size` and every still picture is made at the paper's exact pixel size, with the dpi
stored in the file:

```ini
[MEDIA_TEMPLATES]
print_size = postcard     # Canon SELPHY CP1300/CP1500 postcard, 100 x 148 mm borderless
print_dpi = 300           # what the SELPHY prints at: 1181 x 1748 px (1748 x 1181 in landscape)
print_fit = auto
```

`print_size` is `postcard` (100 x 148 mm), `l` (89 x 119), `card` (54 x 86), `4x6`, `5x7`, `6x8` (inches), or
`WIDTHxHEIGHT` in mm (`100x148`). Orientation follows the picture, so a landscape photo makes a landscape file.

* A **single photo** fills the paper: it is cropped to the paper's shape first, and the frame overlay and footer text
  are laid out on that shape, so nothing is cut off afterwards.
* A **collage** keeps the shape its template gives it. Within about 6% of the paper's shape (for example the 6 x 4 in
  Four Up) it is cropped slightly; a very different one (the 2 x 6 in Photo Strip) is centred on the canvas colour
  with margins at the sides, never stretched. Make a collage `size` match the paper to use all of it.
* `print_fit = cover` always crops, `contain` always pads (a photo then keeps its whole frame, with bars).

Leave the CUPS queue on the matching borderless page size (for the SELPHY, "Postcard 100x148mm" borderless) so
the driver prints the file 1:1. Animations, wigglegrams and videos are unaffected. Try it without the booth:
`pibooth-media-templates preview TEMPLATE photo.jpg --paper postcard`.

## Limits to know about

* **Up to 4 captures per template.** pibooth builds its default picture factory before plugins can step in, and
  that accepts 1-4 images.
* **Video and wigglegram are made from stills.** pibooth has no video capture, so a "video" is a slideshow of the
  captures, and a wigglegram comes from one camera taking successive photos (aligned on the subject), not two lenses.
* Background replacement runs when the pictures are built, so each capture adds roughly the MODNet time (about
  a second on a Pi 5) to the processing screen. pibooth-modnet's overlap-with-countdown trick is not used yet.
* pibooth's wait-screen `animate` option shows un-templated frames for multi-capture templates; turn it off.
* Templates load at start-up; restart pibooth after editing them.

## Development

```bash
pip install -e .[test] pibooth pytest && pytest
```

## Third-party

The bundled icon fonts are Google's [Material Icons](https://github.com/google/material-design-icons), licensed under
the Apache License 2.0 (`pibooth_media_templates/data/LICENSE-material-icons.txt`).
