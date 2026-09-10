#!/usr/bin/env python3
"""
bundle_pieces.py — turn a bundle's markdown into the JSON form the store serves.

A bundle on disk carries YAML front matter and a markdown body, because that is what a
human reads and a git diff shows. The store carries the same fields as JSON with the
body alongside, because a destination should not need a YAML parser to render a page.
BUNDLE.md states both; this converts the first into the second.

  usage: python3 tools/bundle_pieces.py <content-dir> <bundle-dir> --outlet NAME
                 [--images DIR] [--kind piece|talk]

  INPUT   <content-dir>/*.md          front matter + body, or writings/*.md
          <images-dir>/<slug>/…       the pictures, wherever the site kept them

  OUTPUT  <bundle-dir>/pieces/<slug>.json
          <bundle-dir>/images/<slug>/…
          <bundle-dir>/index.json     merged, never rewritten from scratch

TWO THINGS IT DOES NOT DO, both deliberate:

  It does not recompute the digest. The digest was computed by the exporter over the
  reader-text domain and is the piece's proof that what is published is what was
  written. Recomputing it here with a different stripper would silently re-bless
  whatever happens to be on disk, which is the one thing a verifier must never do.

  It does not rewrite prose. The only edit is to image references, and only to undo a
  destination's own rewrite: a vendored bundle turns `../images/…` into `/images/…` so
  Next can serve from /public, and the store needs the relative form back.
"""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone

try:
    import yaml
except ImportError:
    print("error: missing dependency (yaml); pip install pyyaml", file=sys.stderr)
    sys.exit(2)


def die(code, msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def split_front_matter(text, path):
    if not text.startswith('---'):
        die(1, f'{path}: no front matter')
    end = text.find('\n---', 3)
    if end == -1:
        die(1, f'{path}: unterminated front matter')
    head = text[3:end]
    body = text[end + 4:]
    return yaml.safe_load(head) or {}, body.lstrip('\n')


def reader_text(md):
    """The words a human actually reads. Used for `plain`, never for the digest."""
    t = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', md)
    t = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', t)
    t = re.sub(r'^\[\^[^\]]+\]:.*$', '', t, flags=re.M)
    t = re.sub(r'\[\^[^\]]+\]', '', t)
    t = re.sub(r'[*_`>]+', '', t)
    t = re.sub(r'^#{1,6}\s*', '', t, flags=re.M)
    t = re.sub(r'^\s*[-*+]\s+', '', t, flags=re.M)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def to_relative(src):
    """Undo a destination's image rewrite. `/images/x` and `images/x` both mean the same
    place inside a bundle; the spec's form is `../images/x`."""
    if not isinstance(src, str) or re.match(r'^(https?:)?//|^data:', src):
        return src
    s = src.lstrip('/')
    s = re.sub(r'^(\.\./)+', '', s)
    return f'../{s}' if s.startswith('images/') else src


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('content')
    ap.add_argument('bundle')
    ap.add_argument('--outlet', required=True,
                    help='the outlet these pieces are published to')
    ap.add_argument('--images', help='directory holding <slug>/ image folders')
    ap.add_argument('--kind', default='piece', choices=['piece', 'talk'])
    a = ap.parse_args()

    src_dir = a.content
    if os.path.isdir(os.path.join(src_dir, 'writings')):
        src_dir = os.path.join(src_dir, 'writings')
    if not os.path.isdir(src_dir):
        die(1, f'{a.content}: not a directory')
    files = sorted(f for f in os.listdir(src_dir) if f.endswith('.md'))
    if not files:
        die(1, f'{src_dir}: no .md files')

    os.makedirs(os.path.join(a.bundle, 'pieces'), exist_ok=True)

    index_path = os.path.join(a.bundle, 'index.json')
    index = {'spec': '2', 'generated_at': '', 'pieces': []}
    if os.path.exists(index_path):
        with open(index_path, encoding='utf-8') as fh:
            index = json.load(fh)
    by_slug = {p['slug']: p for p in index.get('pieces', [])}

    copied = set()
    for name in files:
        path = os.path.join(src_dir, name)
        with open(path, encoding='utf-8') as fh:
            meta, body = split_front_matter(fh.read(), path)

        slug = meta.get('slug') or os.path.splitext(name)[0]
        for field in ('title', 'published_at', 'digest'):
            if not meta.get(field):
                die(1, f'{path}: {field} is required')

        # Image references, back to the form the spec calls for.
        body = re.sub(r'(!\[[^\]]*\]\()(/images/)', r'\1../images/', body)
        piece = {
            'slug': slug,
            'title': meta['title'],
            'published_at': str(meta['published_at'])[:10],
            'digest': meta['digest'],
            'body': body,
            'plain': reader_text(body),
        }
        for k in ('subtitle', 'source_slug', 'canonical', 'footnotes'):
            if meta.get(k):
                piece[k] = meta[k]
        if meta.get('syndicated'):
            piece['syndicated'] = meta['syndicated']
        if meta.get('hero'):
            hero = dict(meta['hero'])
            hero['src'] = to_relative(hero.get('src'))
            piece['hero'] = hero
        if meta.get('images'):
            piece['images'] = [{**i, 'src': to_relative(i.get('src'))} for i in meta['images']]

        with open(os.path.join(a.bundle, 'pieces', f'{slug}.json'), 'w', encoding='utf-8') as fh:
            json.dump(piece, fh, indent=2, ensure_ascii=False)
            fh.write('\n')

        if a.images:
            frm = os.path.join(a.images, slug)
            if os.path.isdir(frm):
                to = os.path.join(a.bundle, 'images', slug)
                if os.path.isdir(to):
                    shutil.rmtree(to)
                shutil.copytree(frm, to)
                copied.add(slug)

        entry = {
            'slug': slug,
            'title': meta['title'],
            'published_at': piece['published_at'],
            'digest': meta['digest'],
            'outlets': sorted(set((by_slug.get(slug, {}).get('outlets') or []) + [a.outlet])),
            'kind': a.kind,
        }
        if meta.get('subtitle'):
            entry['subtitle'] = meta['subtitle']
        by_slug[slug] = entry

    index['spec'] = '2'
    index['pieces'] = sorted(by_slug.values(),
                             key=lambda p: p.get('published_at', ''), reverse=True)
    index['generated_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    with open(index_path, 'w', encoding='utf-8') as fh:
        json.dump(index, fh, indent=2, ensure_ascii=False)
        fh.write('\n')

    print(f"✓ {a.bundle} — {len(files)} piece(s) for {a.outlet}, "
          f"images for {len(copied)}, {len(index['pieces'])} in index")
    return 0


if __name__ == '__main__':
    sys.exit(main())
