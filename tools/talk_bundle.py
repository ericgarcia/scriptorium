#!/usr/bin/env python3
"""
talk_bundle.py — assemble a bundle for a talk from its metadata and its built deck.

A talk is a piece with slides (BUNDLE.md, "Talks"). This puts the two halves together:

  INPUT   <talk>/piece.yaml            title, date, venue, and the framing prose
          <deck>/                      output of dc_to_deck.py

  OUTPUT  <bundle>/pieces/<slug>.json  the piece, with its `talk` block
          <bundle>/talks/<slug>/…      deck.html, notes.json, deck-stage.js, assets
          <bundle>/index.json          created, or updated in place if it exists

  usage: python3 tools/talk_bundle.py <talk-dir> <deck-dir> <bundle-dir>

The body is the talk's framing prose, not its transcript. A transcript is derived from
notes.json by the renderer, which is the arrangement BUNDLE.md records and deliberately
leaves open: nothing yet turns speaker notes into markdown on the desk, and inventing a
second implementation of that before the direction is settled would be building on sand.
"""

import hashlib
import json
import os
import re
import shutil
import sys

try:
    import yaml
except ImportError:
    print("error: missing dependency (yaml); pip install pyyaml", file=sys.stderr)
    sys.exit(2)


def die(code, msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def reader_text(md):
    """The text a human actually reads, which is the domain the digest covers.

    Deliberately the same idea as render_reader() in md_to_substack.py: drop the markers
    and leave the words, so a digest changes when the writing changes and not when the
    formatting does.
    """
    t = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', md)          # images
    t = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', t)       # links keep their text
    t = re.sub(r'[*_`]+', '', t)                          # emphasis, code
    t = re.sub(r'^#{1,6}\s*', '', t, flags=re.M)          # headings
    t = re.sub(r'^\s*[-*+]\s+', '', t, flags=re.M)        # bullets
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if len(args) != 3:
        print(__doc__)
        return 1
    talk_dir, deck_dir, bundle_dir = args

    meta_path = os.path.join(talk_dir, 'piece.yaml')
    if not os.path.exists(meta_path):
        die(1, f'{talk_dir}: no piece.yaml')
    with open(meta_path, encoding='utf-8') as fh:
        meta = yaml.safe_load(fh) or {}

    notes_path = os.path.join(deck_dir, 'notes.json')
    if not os.path.exists(notes_path):
        die(1, f'{deck_dir}: no notes.json — run dc_to_deck.py first')
    with open(notes_path, encoding='utf-8') as fh:
        notes = json.load(fh)

    slug = meta.get('slug') or notes.get('slug')
    if not slug:
        die(1, f'{meta_path}: slug is required')
    for field in ('title', 'published_at'):
        if not meta.get(field):
            die(1, f'{meta_path}: {field} is required')
    outlets = meta.get('outlets') or []
    if not outlets:
        die(1, f'{meta_path}: outlets is required — nothing is published without being named')

    body = (meta.get('body') or '').strip()
    if not body:
        die(1, f'{meta_path}: body is required (the framing prose above the deck)')

    plain = reader_text(body)
    digest = 'sha256:' + hashlib.sha256(plain.encode('utf-8')).hexdigest()

    # Copy the deck in. The bundle carries the built artifact and never looks inside it.
    talk_out = os.path.join(bundle_dir, 'talks', slug)
    if os.path.isdir(talk_out):
        shutil.rmtree(talk_out)
    shutil.copytree(deck_dir, talk_out)

    piece = {
        'slug': slug,
        'title': meta['title'],
        'published_at': str(meta['published_at']),
        'digest': digest,
        'body': body,
        'plain': plain,
        'talk': {
            'deck': f'../talks/{slug}/deck.html',
            'notes': f'../talks/{slug}/notes.json',
            'slide_count': notes['slideCount'],
        },
    }
    for k in ('subtitle', 'canonical', 'footnotes'):
        if meta.get(k):
            piece[k] = meta[k]
    for k in ('venue', 'delivered_at', 'duration_minutes'):
        if meta.get(k):
            piece['talk'][k] = str(meta[k]) if k == 'delivered_at' else meta[k]
    if meta.get('syndicated'):
        piece['syndicated'] = meta['syndicated']

    os.makedirs(os.path.join(bundle_dir, 'pieces'), exist_ok=True)
    piece_path = os.path.join(bundle_dir, 'pieces', f'{slug}.json')
    with open(piece_path, 'w', encoding='utf-8') as fh:
        json.dump(piece, fh, indent=2, ensure_ascii=False)
        fh.write('\n')

    # The index is a merge, not a rewrite: a bundle holding one talk must not unpublish
    # everything else in the store.
    index_path = os.path.join(bundle_dir, 'index.json')
    index = {'spec': '2', 'generated_at': '', 'pieces': []}
    if os.path.exists(index_path):
        with open(index_path, encoding='utf-8') as fh:
            index = json.load(fh)
    entry = {
        'slug': slug,
        'title': meta['title'],
        'published_at': str(meta['published_at']),
        'digest': digest,
        'outlets': outlets,
        'kind': 'talk',
    }
    if meta.get('subtitle'):
        entry['subtitle'] = meta['subtitle']
    index['pieces'] = [p for p in index.get('pieces', []) if p.get('slug') != slug] + [entry]
    index['pieces'].sort(key=lambda p: p.get('published_at', ''), reverse=True)
    index['spec'] = '2'
    from datetime import datetime, timezone
    index['generated_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    with open(index_path, 'w', encoding='utf-8') as fh:
        json.dump(index, fh, indent=2, ensure_ascii=False)
        fh.write('\n')

    assets = os.path.join(talk_out, 'assets')
    n_assets = len(os.listdir(assets)) if os.path.isdir(assets) else 0
    print(f"✓ {bundle_dir} — {slug}: {notes['slideCount']} slides, {n_assets} assets, "
          f"{len(index['pieces'])} piece(s) in index — outlets: {', '.join(outlets)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
