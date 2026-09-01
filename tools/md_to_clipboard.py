#!/usr/bin/env python3
"""Put a piece's composed body HTML on the system clipboard, for a real ⌘V paste.

WHY THIS EXISTS
---------------
`md_to_substack.py` emits a self-contained JS snippet that carries the entire essay
baked into a string literal. Driving it means an agent reproducing every byte of that
snippet into a browser `javascript_exec` call — for a 5,700-word essay that is ~37KB of
the author's own prose, retyped. That makes the transcription the weakest link in the
chain: one wrong character diffs as a real edit and can publish a typo in the author's
voice. The guards downstream cannot see it, because to them a typo is just another edit.

The clipboard removes the agent from the transport entirely. The bytes go
disk -> macOS pasteboard -> Chrome -> ProseMirror, and are never retyped.

WHAT WORKS, AND WHAT DOES NOT (measured 2026-09-01)
---------------------------------------------------
  in-app browser pane + navigator.clipboard.read()  -> NotAllowedError: document not focused
  in-app browser pane + synthetic cmd+v             -> no-op, editor stays empty
  REAL Chrome + real click + real cmd+v             -> WORKS; h2/em/strong all survive

So this is used with the `claude-in-chrome` surface, not the in-app pane. Programmatic
`focus()` does not satisfy the Clipboard API; the click has to be a real one.

USAGE
-----
    python3 framework/tools/md_to_clipboard.py <piece-dir> [--fn-out notes.js]

Prints the same counts as `md_to_substack.py`, plus the SHA-256 of the HTML actually
placed on the pasteboard so the paste can be verified afterward. Runs the identical
preflight refusals (a stray "verify" note, nested footnote refs) — this is a different
transport, never a way around the gates.

Footnotes cannot travel by clipboard: a paste cannot create native Substack footnotes.
`--fn-out` writes the small footnote-insertion snippet (a few KB, keyed on the [[FNn]]
markers the paste leaves behind), which is small enough to run directly.
"""

import sys, os, json, hashlib, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from md_to_substack import read_manifest, convert  # noqa: E402

FN_TEMPLATE = """(() => {
  window.__sbFN = %FOOTNOTES%;
  const ed = document.querySelector('.ProseMirror').editor;
  const findToken = (doc, t) => { let f = null; doc.descendants((node, pos) => { if (f) return false; if (node.isText) { const i = node.text.indexOf(t); if (i >= 0) { f = { from: pos + i, to: pos + i + t.length }; return false; } } return true; }); return f; };
  let done = 0; const missing = [];
  for (const [n, c] of window.__sbFN) {
    const loc = findToken(ed.state.doc, '[[FN' + n + ']]');
    if (!loc) { missing.push(n); continue; }
    ed.chain().focus().setTextSelection(loc).deleteSelection().insertFootnote().run();
    ed.chain().insertContent(c).run();
    done++;
  }
  return JSON.stringify({ inserted: done, missing });
})()"""


def set_clipboard_html(html: str) -> None:
    """Put `html` on the macOS pasteboard under the HTML flavor.

    pbcopy only sets public.utf8-plain-text, which ProseMirror pastes as flat text --
    every heading, blockquote, link and italic would be lost. AppleScript's
    «data HTML<hex>» sets the real HTML flavor, which is what the paste handler reads.
    """
    if sys.platform != 'darwin':
        sys.exit('md_to_clipboard: macOS only (uses the AppleScript pasteboard).')
    hexed = html.encode('utf-8').hex()
    # Passed via stdin, not argv: a 32KB essay overruns the command-line length limit.
    proc = subprocess.run(['osascript', '-'], input='set the clipboard to «data HTML%s»' % hexed,
                          text=True, capture_output=True)
    if proc.returncode != 0:
        sys.exit('md_to_clipboard: osascript failed: %s' % proc.stderr.strip())
    info = subprocess.run(['osascript', '-e', 'clipboard info'], text=True, capture_output=True).stdout
    if 'HTML' not in info:
        sys.exit('md_to_clipboard: clipboard did not take the HTML flavor (got: %s)' % info.strip())


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        sys.exit(__doc__)
    piece_dir = args[0].rstrip('/')
    fn_out = None
    if '--fn-out' in sys.argv:
        fn_out = sys.argv[sys.argv.index('--fn-out') + 1]

    man = read_manifest(os.path.join(piece_dir, 'publish.yaml'))
    html, footnotes, stripped, residual, unverified, fn_issues = convert(piece_dir)

    # Same gates as a normal compose. A different transport is not a lower bar.
    if residual:
        sys.exit('REFUSING: %d footnote(s) still contain "verify" after cleaning: %s'
                 % (len(residual), residual))
    if fn_issues['nested']:
        sys.exit('REFUSING: footnote reference(s) inside a footnote: %s. These publish as a '
                 'literal marker. Reword the note.' % fn_issues['nested'])
    if fn_issues['undefined'] or fn_issues['duplicated']:
        sys.exit('REFUSING: undefined=%s duplicated=%s — either desynchronizes footnote '
                 'indices for a later surgical re-sync.'
                 % (fn_issues['undefined'], fn_issues['duplicated']))

    set_clipboard_html(html)

    print('paragraphs~%d  headings~%d  dividers~%d  images~%d  footnotes~%d  '
          'editorial-notes-stripped~%d'
          % (html.count('<p>'), html.count('<h2>') + html.count('<h3>'),
             html.count('<hr>'), html.count('<img'), len(footnotes), stripped))
    print('clipboard: %d chars of text/html  sha256=%s'
          % (len(html), hashlib.sha256(html.encode()).hexdigest()[:16]))
    print('title:    %s' % json.dumps(man.get('title', '')))
    print('subtitle: %s' % json.dumps(man.get('subtitle', '')))
    if unverified:
        print('note: %d anchor(s) still carry a † marker' % len(unverified))

    if fn_out:
        with open(fn_out, 'w') as f:
            f.write(FN_TEMPLATE.replace('%FOOTNOTES%', json.dumps(footnotes)))
        print('footnote snippet: %s (%d notes)' % (fn_out, len(footnotes)))

    print()
    print('Next, in REAL Chrome (not the in-app pane — it cannot reach the pasteboard):')
    print('  1. open the composer and set title/subtitle')
    print('  2. REAL click into the body, then a REAL cmd+v')
    print('  3. run the --fn-out snippet to convert [[FNn]] markers to native footnotes')
    print('  4. verify: block count + per-block hashes against the draft')


if __name__ == '__main__':
    main()
