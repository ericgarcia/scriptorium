#!/usr/bin/env python3
"""
md_to_linkedin.py — compose a piece as a LinkedIn Article, for a human to publish.

LinkedIn is a SURFACE, not a store (PUBLISHING.md): there is no write API for Articles,
so the copy is composed in the browser and a person clicks Publish. This tool produces
what gets composed and refuses when the piece is not ready to go there.

  usage: python3 tools/md_to_linkedin.py <piece-dir> --outlets publishing/outlets.yaml
                 [--canonical-outlet NAME] [--out DIR] [--check] [--no-fetch]

  OUT   <out>/article.html    the body, LinkedIn-safe, ready to paste
        <out>/article.json    title, canonical, and the images in upload order
        <out>/fig<N>.json     one per figure: {n, alt, name, dataUri}, for pane_carry.py

WHAT LINKEDIN CANNOT CARRY, AND WHAT THIS DOES INSTEAD

  Footnotes      LinkedIn has none. Refs become [1], [2]… in first-reference order and
                 the notes follow the body under "Notes" — the same order the Substack
                 composer inserts them, so the two copies number alike.
  rel=canonical  LinkedIn emits none. "Link to the canonical" is a visible line at the
                 top — *Originally published at <url>* — not a tag.
  Images         A marked slot in the body, and a fig<N>.json per figure. Measured
                 2026-09-10: a pasted data: image lands as a figure and LinkedIn uploads
                 it to its CDN ON SAVE — but the paste DROPS THE ALT TEXT, so each figure
                 is pasted over its own slot and its alt set afterwards from the payload.
                 One figure at a time keeps a 2 MB image off the body's paste.
  Subtitle       An Article has a title and nothing else, so the subtitle becomes an
                 italic lede under the canonical line.

THE GATES, AND THERE IS NO --force

  1. check_verified must pass. LinkedIn is a copy, but it is a public one under the
     author's name, and the verification rule does not get weaker for syndication.
  2. The body must be clean by the converter's own guards — no stray verify markers,
     no footnote that fails to pair, no clearance date left in reader text.
  3. The canonical must be RECORDED and LIVE. PUBLISHING.md: publish the canonical first
     and let it be indexed before the copy goes up. A LinkedIn Article that says
     "originally published at" a URL that 404s is a broken promise in the first line,
     and LinkedIn will be the copy search engines find first if it goes up first.
     (--no-fetch skips only the network half, for tests; it never waives the record.)

Never publishes, never posts, never touches LinkedIn. It writes two files.
"""

import argparse
import html
import json
import os
import re
import subprocess
import sys

try:
    import yaml
except ImportError:
    print("error: missing dependency (yaml); pip install pyyaml", file=sys.stderr)
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from md_to_substack import parse_blocks                        # noqa: E402


def die(code, msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


FN_MARK = re.compile(r'\[\[FN(\w+)\]\]')


def resolve_canonical(manifest, outlets_cfg, canonical_outlet):
    """The piece's home address. The manifest's own `canonical:` wins; otherwise the URL
    the canonical outlet's manifest key records. Never derived from a slug: a guessed
    canonical is exactly the one that turns out to 404."""
    if manifest.get('canonical'):
        return str(manifest['canonical']), 'manifest canonical:'
    declared = manifest.get('outlets') or []
    name = canonical_outlet or next((o for o in declared if o != 'linkedin'), None)
    if not name:
        return None, 'no outlet to be canonical'
    oc = (outlets_cfg.get('outlets') or {}).get(name)
    if not oc:
        return None, f'outlet {name!r} is not defined in the outlets config'
    key = oc.get('manifest_url_key')
    if not key:
        return None, f'outlet {name!r} has no manifest_url_key'
    url = manifest.get(key)
    return (str(url) if url else None), f'{name} ({key})'


def canonical_is_live(url):
    """(ok, why). Live means a 200 at that address — a redirect to somewhere else is not
    the canonical, it is whatever the site decided to show instead."""
    from outlet_audit import fetch
    status, _body, final = fetch(url)
    if status is None:
        return False, 'unreachable'
    if status != 200:
        return False, f'HTTP {status}'
    if final.rstrip('/') != url.split('?')[0].rstrip('/'):
        return False, f'redirects to {final}'
    return True, 'HTTP 200'


def build(piece_dir):
    """Body HTML, the notes, and the image slots. Pure: no network, no gates.

    Figures are taken from each block's markdown SOURCE, never recovered from the rendered
    HTML: the shared renderer's esc() leaves double quotes unescaped, so an alt text that
    quotes a label ("labeled \"featurize.\"") ends the alt attribute early and cannot be
    parsed back out of it. The first cut of this tool did exactly that and rendered zero
    slots for five figures."""
    blocks, ordered, _stripped, residual, unverified, fn_issues, sources = parse_blocks(piece_dir)
    number = {n: i + 1 for i, (n, _c) in enumerate(ordered)}

    images, body = [], []
    for b, src in zip(blocks, sources['body']):
        whole = re.fullmatch(r'!\[(.*?)\]\(([^)\s]+)\)', src.strip(), re.S)
        if whole:
            alt, path = whole.group(1), whole.group(2)
            images.append({'n': len(images) + 1, 'path': path, 'alt': alt})
            body.append(f'<p><strong>[Figure {len(images)} — upload here]</strong> '
                        f'<em>{html.escape(alt)}</em></p>')
            continue
        body.append(FN_MARK.sub(lambda m: f'[{number.get(m.group(1), "?")}]', b))

    notes = [f'<p>[{number[n]}] {FN_MARK.sub("", c)}</p>' for n, c in ordered]
    return body, notes, images, {'residual': residual, 'unverified': unverified,
                                 'fn_issues': fn_issues}


def image_files(piece_dir):
    """The local image paths in body order — what the author uploads, one per slot."""
    src = open(os.path.join(piece_dir, 'draft.md'), encoding='utf-8').read()
    src = re.sub(r'<!--.*?-->', '', src, flags=re.S)
    body = src.split('\n---\n', 1)[1] if '\n---\n' in src else src
    return re.findall(r'!\[[^\]]*\]\(([^)\s]+)\)', body)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('piece')
    ap.add_argument('--outlets', required=True,
                    help="the instance's outlets.yaml; the framework holds no URLs")
    ap.add_argument('--canonical-outlet', help='default: first declared outlet')
    ap.add_argument('--out', help='default: <piece>/linkedin/')
    ap.add_argument('--check', action='store_true', help='run the gates, write nothing')
    ap.add_argument('--no-fetch', action='store_true',
                    help='skip the network check of the canonical (tests only)')
    a = ap.parse_args()

    piece = a.piece.rstrip('/')
    if not os.path.exists(os.path.join(piece, 'draft.md')):
        die(1, f'{piece}: no draft.md')
    if not os.path.exists(a.outlets):
        die(1, f'{a.outlets}: no outlets config')
    # yaml, not md_to_substack.read_manifest: that reader is key: value only and returns
    # nothing for a list, so `outlets:` read as empty and every gate below misfired.
    with open(os.path.join(piece, 'publish.yaml'), encoding='utf-8') as fh:
        manifest = yaml.safe_load(fh) or {}
    with open(a.outlets, encoding='utf-8') as fh:
        outlets_cfg = yaml.safe_load(fh) or {}

    refusals = []

    if 'linkedin' not in (manifest.get('outlets') or []):
        refusals.append("publish.yaml does not name `linkedin` among its outlets — "
                        "nothing goes somewhere it was not sent")

    v = subprocess.run([sys.executable, os.path.join(HERE, 'check_verified.py'),
                        os.path.abspath(piece)],
                       capture_output=True, text=True)
    if v.returncode != 0:
        first = (v.stdout + v.stderr).strip().splitlines()
        refusals.append('check_verified refuses: ' + (first[0] if first else f'exit {v.returncode}'))

    body, notes, images, guards = build(piece)
    if guards['residual']:
        refusals.append(f"clearance or verify language left in reader text: {guards['residual']}")
    if guards['unverified']:
        refusals.append(f"unverified markers stripped from footnotes: {guards['unverified']}")
    for k in ('undefined', 'unreferenced', 'duplicated', 'nested'):
        if guards['fn_issues'].get(k):
            refusals.append(f"footnotes {k}: {guards['fn_issues'][k]}")

    canonical, where = resolve_canonical(manifest, outlets_cfg, a.canonical_outlet)
    if not canonical:
        refusals.append(f'no canonical URL recorded ({where}) — publish the canonical first')
    elif not a.no_fetch:
        ok, why = canonical_is_live(canonical)
        if not ok:
            refusals.append(f'canonical {canonical} is not live ({why}) — '
                            'publish it first and let it be indexed')

    files = image_files(piece)
    if len(files) != len(images):
        refusals.append(f'{len(files)} image(s) in the draft but {len(images)} figure slot(s) '
                        'rendered — a figure would go missing')

    title = manifest.get('title') or os.path.basename(piece)
    print(f"piece      {piece}")
    print(f"title      {title}")
    print(f"canonical  {canonical or '—'}   [{where}]")
    print(f"body       {len(body)} block(s), {len(notes)} note(s), {len(images)} figure(s)")

    if refusals:
        print(f"\nREFUSED — {len(refusals)} reason(s):", file=sys.stderr)
        for r in refusals:
            print(f'  {r}', file=sys.stderr)
        return 1
    if a.check:
        print('\nready — every gate passes; nothing written (--check)')
        return 0

    parts = [f'<p><em>Originally published at <a href="{html.escape(canonical)}">'
             f'{html.escape(canonical)}</a>.</em></p>']
    if manifest.get('subtitle'):
        parts.append(f"<p><em>{html.escape(str(manifest['subtitle']))}</em></p>")
    parts += body
    if notes:
        parts.append('<h2>Notes</h2>')
        parts += notes

    out = a.out or os.path.join(piece, 'linkedin')
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'article.html'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(parts) + '\n')
    for img in images:
        img['file'] = os.path.join(piece, img.pop('path'))
    with open(os.path.join(out, 'article.json'), 'w', encoding='utf-8') as fh:
        json.dump({'title': title, 'canonical': canonical, 'images': images},
                  fh, indent=2, ensure_ascii=False)
        fh.write('\n')
    # One carry payload per figure. The bytes and the alt text travel together, so the
    # page that pastes the image is also the page that restores its alt — which the paste
    # drops — and neither is ever retyped.
    import base64, mimetypes
    for img in images:
        mime = mimetypes.guess_type(img['file'])[0] or 'image/png'
        with open(img['file'], 'rb') as fh:
            data = base64.b64encode(fh.read()).decode()
        with open(os.path.join(out, f"fig{img['n']}.json"), 'w', encoding='utf-8') as fh:
            json.dump({'n': img['n'], 'alt': img['alt'], 'name': os.path.basename(img['file']),
                       'dataUri': f'data:{mime};base64,{data}'}, fh, ensure_ascii=False)
    print(f"\nwrote      {out}/article.html, article.json, fig1..{len(images)}.json")
    print("next       compose in LinkedIn's Article editor; a human clicks Publish")
    return 0


if __name__ == '__main__':
    sys.exit(main())
