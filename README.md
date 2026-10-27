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

* Icons appear along the bottom of the wait screen. **Touch an icon** to pick it and start the sequence.
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
icon: icon.png               # optional, otherwise a pictogram over the background is drawn
background: background.jpg   # replaces what is behind the guests (needs pibooth-modnet)
overlay: frame.png           # transparent PNG, stretched over the picture
```

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

## Command line

```bash
pibooth-media-templates init [FOLDER]            # write the examples
pibooth-media-templates check [FOLDER]           # validate every template
pibooth-media-templates preview TEMPLATE a.jpg b.jpg -o out/ [--no-background]
```

`preview` renders on any computer, so you can design templates without the booth.

## Configuration (`[MEDIA_TEMPLATES]`)

`enabled`, `templates_path`, `disabled` (names, comma separated), `default`, `keep_selection`, `bar_position`,
`bar_height`, `show_labels`, plus `model_path`, `inference_size`, `threads`, `refine_edges` for backgrounds (the
model file is shared with pibooth-modnet).

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
