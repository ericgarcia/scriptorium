#!/usr/bin/env python3
"""substack_captions.py -- write a piece's captions into its Substack post, by position.

WHY THIS EXISTS (2026-09-11).  Captions live in publish.yaml (`captions:`, and `cover_caption:`
for the hero), and md_to_substack now emits them on compose as <figcaption>, which Substack's
paste turns into each captionedImage's caption node (measured 2026-09-11 on a TEST draft; the
`captioned-image-container` wrapper shape, by contrast, loses the caption). So a FRESH compose
carries them. A post composed before that has captionedImages with no caption, and a live post
is not recomposed to fix one line. This sets them surgically: no body text is touched, only each
image's caption node.

    usage: python3 substack_captions.py pieces/<slug> [--out captions.js]

Run the snippet IN THE POST'S EDITOR -- it edits the document, not the drafts API -- then ship
it as any re-sync is shipped (Update -> Update now, reading the dialog for a delivery control
first), then `substack_verify --fresh`, which compares captions and reports DRIFT-CAPTION.

WHAT IT REFUSES
    A post whose image count differs from the draft's. Captions are matched by position, and
    one extra or missing image would put every caption after it on the wrong picture.
    A piece with no captions at all (exit 2) -- there is nothing to write.

WHAT IT LEAVES ALONE
    A live caption on an image the desk gives none. It is reported (`kept`), never deleted:
    removing a caption someone set is not this tool's call. substack_verify reports it as drift
    until publish.yaml says what it should be.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from md_to_substack import render_captions   # noqa: E402

SNIPPET = r"""(() => {
  const WANT = %CAPS%;
  const flat = s => (s || '').replace(/[\u2018\u2019]/g, "'").replace(/[\u201c\u201d]/g, '"').replace(/\s+/g, ' ').trim();
  const pm = document.querySelector('.ProseMirror');
  const ed = pm && pm.editor;
  if (!ed) return JSON.stringify({refused: 'no editor on this page: open the post in its editor'});
  const figs = [];
  ed.state.doc.descendants((n, pos) => { if (n.type.name === 'captionedImage') { figs.push({n, pos}); return false; } });
  if (figs.length !== WANT.length)
    return JSON.stringify({refused: 'post has ' + figs.length + ' image(s), the draft has ' + WANT.length +
                                    '; captions are matched by position, so nothing was changed'});
  const schema = ed.state.schema;
  let tr = ed.state.tr;
  const done = [];
  for (let i = figs.length - 1; i >= 0; i--) {                    // last first: positions stay valid
    const {n, pos} = figs[i];
    const want = WANT[i];
    let capPos = null, cap = null;
    n.forEach((c, off) => { if (c.type.name === 'caption') { capPos = pos + 1 + off; cap = c; } });
    const have = cap ? cap.textContent : '';
    if (flat(have) === flat(want)) { done.unshift({i: i + 1, state: 'unchanged'}); continue; }
    if (!want) { done.unshift({i: i + 1, state: 'kept', live: have}); continue; }
    const node = schema.nodes.caption.create(null, schema.text(want));
    tr = cap ? tr.replaceWith(capPos, capPos + cap.nodeSize, node) : tr.insert(pos + n.nodeSize - 1, node);
    done.unshift({i: i + 1, state: cap ? 'replaced' : 'added'});
  }
  if (tr.docChanged) ed.view.dispatch(tr);
  const back = [];
  ed.state.doc.descendants(n => {
    if (n.type.name === 'captionedImage') { let t = ''; n.forEach(c => { if (c.type.name === 'caption') t = c.textContent; }); back.push(t); return false; }
  });
  return JSON.stringify({done, readBack: back,
                         matches: back.every((t, i) => !WANT[i] || flat(t) === flat(WANT[i]))});
})()"""


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__); return 1
    out = argv[argv.index('--out') + 1] if '--out' in argv else 'captions.js'
    piece = [a for a in argv if not a.startswith('--') and a != out][0].rstrip('/')
    caps = render_captions(piece)
    if not any(caps):
        print(f"{piece}: no captions in publish.yaml (captions:, cover_caption:) -- nothing to set.")
        return 2
    js = SNIPPET.replace('%CAPS%', json.dumps(caps))
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(js)
    for i, c in enumerate(caps, 1):
        print(f"  #{i}  {c if c else '(none -- a live caption here is kept)'}")
    print(f"wrote {out} ({len(js):,} bytes) for {len(caps)} image(s)")
    print("\nRun it IN THE POST'S EDITOR (it edits the document), carried with pane_carry.py and "
          "hash-checked in the page; then Update -> Update now, reading the dialog for any delivery "
          "control first; then substack_verify --fresh.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
