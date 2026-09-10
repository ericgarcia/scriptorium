#!/usr/bin/env python3
"""
dc_to_deck.py — turn a Claude Design deck export into a standalone deck a site can serve.

A talk's deck is designed visually in Claude Design, which exports `.dc.html`: an
AUTHORING format, not a publishable one. It wraps the slides in <x-dc>/<x-import> and
expects `support.js`, a runtime that needs React and exists to serve the design canvas.
Serving that to a reader would ship an editor.

`deck-stage.js` has no such dependency. Its own documentation describes a plain-HTML
usage — a <deck-stage> element with <section> children and one <script src> — so this
lifts the slides out of the authoring wrapper and emits that instead. No React, no
design runtime, nothing that has to be built at request time.

  INPUT   <src>/deck.dc.html      the Claude Design export
          <src>/deck-stage.js     the deck runtime, vendored from the same project
          <src>/assets/…          images the slides reference

  OUTPUT  <out>/deck.html         standalone: <deck-stage> + <section>s + the runtime
          <out>/notes.json        per-slide speaker notes, for a phone remote
          <out>/deck-stage.js
          <out>/assets/…          only the assets the slides actually reference

  USAGE   python3 tools/dc_to_deck.py <src> <out>

Re-importing an edited deck is: pull the new .dc.html into <src>, run this again.
Nothing in the output is hand-maintained.

Ported from the JavaScript original (muffinlabs-web/scripts/build-decks.mjs, 2026-09-10)
so the desk stays one language. The original used no DOM parser — regex and a
hand-rolled section scanner — which is why this reads the same.
"""

import json
import os
import re
import shutil
import sys

# The entity subset the Claude Design exporter emits inside attributes.
NAMED = {
    'amp': '&', 'lt': '<', 'gt': '>', 'quot': '"', 'apos': "'", 'nbsp': ' ',
    'mdash': '—', 'ndash': '–', 'hellip': '…',
    'ldquo': '“', 'rdquo': '”', 'lsquo': '‘', 'rsquo': '’',
}

PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


def die(code, msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def decode_entities(s):
    s = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), s)
    s = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), s)
    return re.sub(
        r'&([a-zA-Z]+);',
        lambda m: NAMED.get(m.group(1).lower(), m.group(0)),
        s,
    )


def attr(tag, name):
    """Read one attribute off an opening tag string."""
    m = re.search(rf'\s{name}="([^"]*)"', tag, re.I)
    return m.group(1) if m else None


def extract_sections(html):
    """Split the top-level <section> elements out of a chunk of HTML.

    Sections never nest in this format, but the depth is counted anyway so a future deck
    that does nest one fails loudly instead of silently losing slides.
    """
    out = []
    open_re = re.compile(r'<section\b[^>]*>', re.I)
    scan_re = re.compile(r'<section\b[^>]*>|</section\s*>', re.I)
    pos = 0
    while True:
        m = open_re.search(html, pos)
        if not m:
            return out
        depth = 1
        idx = m.end()
        while depth > 0:
            s = scan_re.search(html, idx)
            if not s:
                die(1, 'unbalanced <section> in deck source')
            depth += -1 if s.group(0).startswith('</') else 1
            idx = s.end()
        out.append({'open_tag': m.group(0), 'html': html[m.start():idx]})
        pos = idx


def assert_complete_png(path):
    """A PNG that lost its IEND chunk is a truncated download, not a valid image.

    This is not hypothetical: a design asset larger than the export read limit came back
    truncated once, and without this check it would have shipped as a broken slide.
    """
    with open(path, 'rb') as fh:
        buf = fh.read()
    name = os.path.basename(path)
    if buf[:8] != PNG_MAGIC:
        die(1, f'{name}: not a PNG')
    if buf[-8:-4] != b'IEND':
        die(1, f'{name}: truncated (no IEND chunk) — re-download this asset')


def clear_output(out_dir):
    """Empty the output directory — but only if it is one this tool made.

    In the JavaScript original the output path was computed (public/talks/<slug>),
    so a recursive delete could only ever land there. Here it is an argument, and a
    recursive delete pointed at an argument is the single most dangerous line in the
    repo. So: an absent or empty directory is fine, a previous deck build is fine,
    and anything else stops the run rather than being cleared.
    """
    if not os.path.exists(out_dir):
        return
    if not os.path.isdir(out_dir):
        die(2, f'{out_dir}: not a directory')
    entries = os.listdir(out_dir)
    if entries and 'deck.html' not in entries:
        die(2, f'{out_dir}: not empty and not a deck build '
               f'(no deck.html) — refusing to delete it')
    shutil.rmtree(out_dir)


def build_deck(src_dir, out_dir):
    if os.path.realpath(src_dir) == os.path.realpath(out_dir):
        die(2, 'source and output are the same directory')
    slug = os.path.basename(os.path.normpath(src_dir))
    dc_path = os.path.join(src_dir, 'deck.dc.html')
    if not os.path.exists(dc_path):
        die(1, f'{slug}: no deck.dc.html')
    raw = open(dc_path, encoding='utf-8').read()

    import_open = re.search(r'<x-import\b[^>]*>', raw, re.I)
    if not import_open:
        die(1, f'{slug}: no <x-import> in deck.dc.html')
    import_close = raw.rfind('</x-import>')
    body = raw[import_open.end():import_close]

    width = attr(import_open.group(0), 'width') or '1920'
    height = attr(import_open.group(0), 'height') or '1080'

    helmet = re.search(r'<helmet>(.*?)</helmet>', raw, re.I | re.S)
    head = helmet.group(1).strip() if helmet else ''

    sections = extract_sections(body)
    if not sections:
        die(1, f'{slug}: no slides found')

    # Speaker notes travel as a per-slide attribute; pull them into a sidecar so a phone
    # remote can load notes without loading the whole deck.
    slides = [
        {
            'index': i,
            'label': decode_entities(attr(s['open_tag'], 'data-label') or f'Slide {i + 1}'),
            'notes': decode_entities(attr(s['open_tag'], 'data-speaker-notes') or ''),
        }
        for i, s in enumerate(sections)
    ]

    title_m = re.search(r'<h1[^>]*>(.*?)</h1>', sections[0]['html'], re.I | re.S)
    title = (
        decode_entities(re.sub(r'<[^>]+>', '', title_m.group(1)).strip())
        if title_m else slug
    )

    # Verify every input before touching the output directory. The original
    # emptied the output first; a bad asset then left a half-erased deck behind,
    # which for a directory a site serves is worse than not rebuilding at all.
    runtime = os.path.join(src_dir, 'deck-stage.js')
    if not os.path.exists(runtime):
        die(1, f'{slug}: no deck-stage.js')

    # Copy only the assets the slides actually reference, and verify each one.
    referenced = list(dict.fromkeys(re.findall(r'src="assets/([^"]+)"', body)))
    for name in referenced:
        frm = os.path.join(src_dir, 'assets', name)
        if not os.path.exists(frm):
            die(1, f'{slug}: slide references missing asset assets/{name}')
        if name.lower().endswith('.png'):
            assert_complete_png(frm)

    clear_output(out_dir)
    os.makedirs(os.path.join(out_dir, 'assets'), exist_ok=True)
    for name in referenced:
        shutil.copy2(os.path.join(src_dir, 'assets', name),
                     os.path.join(out_dir, 'assets', name))
    shutil.copy2(runtime, os.path.join(out_dir, 'deck-stage.js'))

    slide_html = '\n'.join(s['html'] for s in sections)
    deck_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="robots" content="noindex">
{head}
<style>
  html, body {{ height: 100%; }}
  deck-stage:not(:defined) {{ visibility: hidden; }}
</style>
</head>
<body>
<deck-stage width="{width}" height="{height}">
{slide_html}
</deck-stage>
<script src="deck-stage.js"></script>
<script>
/* Bridge between deck-stage and whatever page embeds this deck.
   deck-stage announces slide changes with window.postMessage on its OWN
   window, which an embedder never sees, so relay those up; and accept
   navigation commands coming back down. */
(function () {{
  var stage = document.querySelector('deck-stage');
  var embedded = window.parent !== window;

  window.addEventListener('message', function (e) {{
    var d = e.data;
    if (!d || typeof d !== 'object') return;

    // deck-stage talking to itself -> relay outward
    if (e.source === window && typeof d.slideIndexChanged === 'number') {{
      if (embedded) {{
        parent.postMessage({{
          type: 'deck:slide',
          index: d.slideIndexChanged,
          total: d.deckTotal,
        }}, '*');
      }}
      return;
    }}

    // embedder talking to us -> drive the deck
    if (e.source !== window && d.type === 'deck:cmd' && stage) {{
      if (d.action === 'next') stage.next();
      else if (d.action === 'prev') stage.prev();
      else if (d.action === 'goto' && typeof d.index === 'number') stage.goTo(d.index);
    }}
  }});

  // Tell the embedder the deck is live and how many slides it has, so it can
  // render a position indicator before the first navigation.
  function announce() {{
    if (!embedded || !stage) return;
    parent.postMessage({{
      type: 'deck:ready',
      total: stage.querySelectorAll(':scope > section').length,
    }}, '*');
  }}
  if (document.readyState === 'complete') announce();
  else window.addEventListener('load', announce);
}})();
</script>
</body>
</html>
"""

    with open(os.path.join(out_dir, 'deck.html'), 'w', encoding='utf-8') as fh:
        fh.write(deck_html)
    with open(os.path.join(out_dir, 'notes.json'), 'w', encoding='utf-8') as fh:
        json.dump(
            {'slug': slug, 'title': title,
             'slideCount': len(slides), 'slides': slides},
            fh, indent=2, ensure_ascii=False,
        )

    return {'title': title, 'slides': len(slides), 'assets': len(referenced)}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if len(args) != 2:
        print(__doc__)
        sys.exit(1)
    src, out = args
    r = build_deck(src, out)
    print(f"✓ {out} — {r['slides']} slides, {r['assets']} assets — \"{r['title']}\"")


if __name__ == '__main__':
    main()
