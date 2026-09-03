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

Prints the same counts as `md_to_substack.py`, plus the SHA-256 of the HTML **read back off
the pasteboard** — evidence about the clipboard, not a hash of what this script hoped to put
there. `--verify` re-checks that the pasteboard still holds this piece and nothing else; run it
immediately before the ⌘V, because the pasteboard is global mutable state and the gap between
loading and pasting is wide enough for another process to win it. Runs the identical
preflight refusals (a stray "verify" note, nested footnote refs) — this is a different
transport, never a way around the gates.

Footnotes cannot travel by clipboard: a paste cannot create native Substack footnotes.
`--fn-out` writes the small footnote-insertion snippet (a few KB, keyed on the [[FNn]]
markers the paste leaves behind), which is small enough to run directly.

PLATFORM
--------
macOS only today, and `set_clipboard_html` below is the entire platform-specific surface --
everything else in this repo is platform-neutral. Windows and Linux support is wanted and is a
small, well-scoped contribution; see "Platform support" in the README for sketches and for the
one hard requirement: the payload must land under the HTML clipboard *flavor*. Plain text is the
trap -- it pastes, it looks like it worked, and every heading, blockquote, italic and link is
silently gone.
"""

import sys, os, json, hashlib, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from md_to_substack import read_manifest, convert, manifest_gate  # noqa: E402

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
        sys.exit(
            'md_to_clipboard: macOS only -- this is the one platform-specific piece of the\n'
            'framework, and it has only ever been run on macOS.\n\n'
            'Right now, use the JS-snippet fallback documented in skills/publish/SKILL.md.\n'
            'Know that it is a real downgrade: it requires the agent to reproduce the whole\n'
            'essay into a browser eval, which is the transcription risk this tool exists to\n'
            'remove. Verify the composed post against the draft either way.\n\n'
            'Porting is small and welcome -- set_clipboard_html() is the whole surface. The\n'
            'payload must land under the HTML clipboard FLAVOR, not as plain text; plain text\n'
            'pastes cleanly and silently drops every heading, blockquote, italic and link.\n'
            '  Linux/X11:     xclip -selection clipboard -t text/html\n'
            '  Linux/Wayland: wl-copy --type text/html\n'
            '  Windows:       CF_HTML, which needs its own header with byte offsets\n'
            '                 (StartHTML/EndHTML/StartFragment/EndFragment) -- Set-Clipboard\n'
            '                 alone will not do it.\n'
            'See "Platform support" in the framework README.')
    hexed = html.encode('utf-8').hex()
    # Passed via stdin, not argv: a 32KB essay overruns the command-line length limit.
    proc = subprocess.run(['osascript', '-'], input='set the clipboard to «data HTML%s»' % hexed,
                          text=True, capture_output=True)
    if proc.returncode != 0:
        sys.exit('md_to_clipboard: osascript failed: %s' % proc.stderr.strip())
    got = read_clipboard_html()
    if got is None:
        sys.exit('md_to_clipboard: the pasteboard has no HTML flavor after the write.\n'
                 'Nothing was placed. Do not paste — you would paste whatever was there before.')
    if got != html:
        sys.exit('md_to_clipboard: WROTE %d chars, PASTEBOARD HOLDS %d — the write did not take.\n'
                 '  intended sha256=%s\n  actual   sha256=%s\n'
                 'Another process almost certainly owns the pasteboard (a concurrent session, a\n'
                 'clipboard manager). Do NOT paste. Re-run once the pasteboard is yours.'
                 % (len(html), len(got),
                    hashlib.sha256(html.encode()).hexdigest()[:16],
                    hashlib.sha256(got.encode()).hexdigest()[:16]))


def read_clipboard_html():
    """Return the HTML flavor currently on the pasteboard, or None if there isn't one.

    This is the half that was missing until 2026-09-02. The old check asked whether the
    string "HTML" appeared in `clipboard info` and then reported the SHA-256 of the string
    it had *intended* to place. Neither is evidence about the pasteboard, and the gap is not
    theoretical: on 2026-09-02 the tool reported a clean write while the pasteboard actually
    held a footnote snippet from a DIFFERENT piece, left by a concurrent session. It pasted
    into a fresh Substack post and was caught only by a post-check. A hash of your own
    intent proves nothing; read the bytes back.
    """
    proc = subprocess.run(['osascript', '-e', 'the clipboard as «class HTML»'],
                          text=True, capture_output=True)
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    if not out.startswith('«data HTML') or not out.endswith('»'):
        return None
    try:
        return bytes.fromhex(out[len('«data HTML'):-1]).decode('utf-8')
    except (ValueError, UnicodeDecodeError):
        return None


def verify_only(piece_dir):
    """Re-check that the pasteboard still holds THIS piece's body, immediately before pasting.

    Loading the clipboard and pasting are separate steps with a human-scale gap between them,
    and the pasteboard is global mutable state that any other process can take. On 2026-09-02
    a concurrent session's `pbcopy` won that race. Run this immediately before the ⌘V.
    """
    _html, _fns, _st, residual, _unv, fn_issues = convert(piece_dir)
    if residual or fn_issues['nested'] or fn_issues['undefined'] or fn_issues['duplicated']:
        sys.exit('md_to_clipboard --verify: the piece no longer converts cleanly; re-run without '
                 '--verify to see the refusal.')
    got = read_clipboard_html()
    if got is None:
        sys.exit('STALE: the pasteboard has no HTML flavor. Do NOT paste — re-run to reload it.')
    if got != _html:
        sys.exit('STALE: the pasteboard does not hold this piece.\n'
                 '  expected %d chars sha256=%s\n  found    %d chars sha256=%s\n'
                 'Something took the pasteboard since it was loaded. Do NOT paste; re-run to reload.'
                 % (len(_html), hashlib.sha256(_html.encode()).hexdigest()[:16],
                    len(got), hashlib.sha256(got.encode()).hexdigest()[:16]))
    print('OK: pasteboard holds %s — %d chars sha256=%s. Safe to paste.'
          % (piece_dir, len(got), hashlib.sha256(got.encode()).hexdigest()[:16]))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        sys.exit(__doc__)
    piece_dir = args[0].rstrip('/')
    if '--verify' in sys.argv:
        return verify_only(piece_dir)
    fn_out = None
    if '--fn-out' in sys.argv:
        fn_out = sys.argv[sys.argv.index('--fn-out') + 1]

    man = read_manifest(os.path.join(piece_dir, 'publish.yaml'))
    # Same gates as a normal compose. A different transport is not a lower bar.
    gate_errors, gate_warnings = manifest_gate(piece_dir)
    for w in gate_warnings:
        print('WARNING: %s -- the author has not signed off on this line; make sure they '
              'read it in the editor before Publish.' % w)
    if gate_errors:
        sys.exit('REFUSING: %s. A post needs a title and a subtitle before it is composed; '
                 'add them to publish.yaml. There is no override.' % '; '.join(gate_errors))
    html, footnotes, stripped, residual, unverified, fn_issues = convert(piece_dir)

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
    on_board = read_clipboard_html()   # re-read; this is evidence, the variable above is intent
    print('clipboard: %d chars of text/html  sha256=%s  (read back off the pasteboard)'
          % (len(on_board), hashlib.sha256(on_board.encode()).hexdigest()[:16]))
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
    print('  2. re-check the pasteboard, then REAL click into the body and a REAL cmd+v:')
    print('       python3 framework/tools/md_to_clipboard.py %s --verify' % piece_dir)
    print('  3. run the --fn-out snippet to convert [[FNn]] markers to native footnotes')
    print('  4. verify: block count + per-block hashes against the draft')


if __name__ == '__main__':
    main()
