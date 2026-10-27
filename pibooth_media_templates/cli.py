# -*- coding: utf-8 -*-
"""Command line tools to build and test templates away from the booth.

    pibooth-media-templates init [FOLDER]
    pibooth-media-templates check [FOLDER]
    pibooth-media-templates preview TEMPLATE PHOTO [PHOTO ...] [-o OUT_DIR] [--no-background]
"""

import sys
import argparse
import os.path as osp
import os
import logging

from PIL import Image, ImageOps

from .model import load_template, load_templates, TemplateError, MULTI_FRAME_TYPES
from .render import BackgroundReplacer, render
from .media import generate_media
from .examples import write_examples

DEFAULT_FOLDER = osp.join('~', '.config', 'pibooth', 'media_templates')


def _folder(value):
    return osp.abspath(osp.expanduser(value or DEFAULT_FOLDER))


def cmd_init(args):
    folder = _folder(args.folder)
    made = write_examples(folder, overwrite=args.force)
    for path in made:
        print("created", path)
    print("{} example template(s) in {}".format(len(made), folder))
    return 0


def cmd_check(args):
    folder = _folder(args.folder)
    templates, errors = load_templates(folder)
    for template in templates:
        print("ok    {:<20} {:<11} {} capture(s){}".format(
            template.name, template.type, template.captures,
            ", replaces background" if template.needs_matting else ""))
    for error in errors:
        print("ERROR", error)
    print("{} usable, {} with errors ({})".format(len(templates), len(errors), folder))
    return 1 if errors else 0


def cmd_preview(args):
    try:
        template = load_template(osp.abspath(osp.expanduser(args.template)))
    except TemplateError as ex:
        print("ERROR", ex)
        return 1

    photos = [ImageOps.exif_transpose(Image.open(p)).convert('RGB') for p in args.photos]
    images = [photos[i % len(photos)] for i in range(template.captures)]  # Reuse photos if too few

    replacer = None
    if template.needs_matting and not args.no_background:
        replacer = BackgroundReplacer()
        replacer.load()

    out_dir = osp.abspath(args.output)
    os.makedirs(out_dir, exist_ok=True)
    stem = osp.join(out_dir, osp.basename(osp.dirname(template.source)) if osp.basename(template.source) == 'template.yaml'
                    else osp.splitext(osp.basename(template.source))[0])
    footer = [(text, None, (0, 0, 0), 'center') for text in args.footer]
    final, processed = render(template, images, replacer, footer_texts=footer)
    final.save(stem + '.jpg', quality=92)
    print("saved", stem + '.jpg')
    if template.type in MULTI_FRAME_TYPES:
        print("saved", generate_media(template, processed, stem))
    return 0


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    parser = argparse.ArgumentParser(prog='pibooth-media-templates', description=__doc__.split('\n\n')[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command')

    init = sub.add_parser('init', help="write the example templates")
    init.add_argument('folder', nargs='?', help="default: " + DEFAULT_FOLDER)
    init.add_argument('--force', action='store_true', help="overwrite existing examples")
    init.set_defaults(func=cmd_init)

    check = sub.add_parser('check', help="validate every template of a folder")
    check.add_argument('folder', nargs='?', help="default: " + DEFAULT_FOLDER)
    check.set_defaults(func=cmd_check)

    preview = sub.add_parser('preview', help="render a template from sample photos")
    preview.add_argument('template', help="template folder or .yaml file")
    preview.add_argument('photos', nargs='+', help="one photo per capture (repeated if fewer)")
    preview.add_argument('-o', '--output', default='.', help="output folder (default: current)")
    preview.add_argument('--footer', action='append', default=[], metavar='TEXT',
                         help="footer text like pibooth's footer_text1/2 (give it up to twice)")
    preview.add_argument('--no-background', action='store_true', help="skip background replacement (fast)")
    preview.set_defaults(func=cmd_preview)

    args = parser.parse_args(argv)
    if not getattr(args, 'func', None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
