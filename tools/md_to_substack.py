#!/usr/bin/env python3
"""
md_to_substack.py — turn a piece's draft.md + publish.yaml into a self-contained
JS snippet that composes the whole post in an OPEN Substack composer:

  1. sets Title + Subtitle,
  2. pastes the whole formatted body in one synthetic ProseMirror paste
     (paragraphs, headings, blockquote, dividers, lists, bold/italic/links, and
     images inlined as data: URIs — Substack uploads them to its CDN), and
  3. defines window.__sbInsertFootnotes() which converts the body's [[FNn]]
     markers into NATIVE Substack footnotes via the editor's own Tiptap
     `insertFootnote` command, filling each note's (rich) content.

Usage:  python3 md_to_substack.py <piece-dir> [out.js]

The caller runs the emitted JS in two steps against a fresh, logged-in composer:
  A) run the whole snippet         -> title/subtitle set, body pasted
  B) run window.__sbInsertFootnotes()  -> markers become native footnotes
(The two-step split is required: ProseMirror applies the paste asynchronously,
so the markers aren't in the doc model until the next tick / next call.)

Never publishes. Leaves a DRAFT for a human to review and publish.

draft.md conventions:
  - Front-matter/scaffolding = everything up to & including the FIRST `---`; dropped.
  - HTML comments stripped anywhere.
  - Blank-line blocks -> <p>; `## ` -> <h2>, `### ` -> <h3>; lone `---` -> <hr>.
  - Inline: **bold**, *italic*, [t](u); ![alt](path) -> inlined <img>.
  - Footnotes: `text[^n]` ref -> [[FNn]] marker; a block starting `[^n]: ...`
    is a footnote definition (collected, removed from the body).

INTERNAL EDITORIAL NOTES (never publish):
  - Anything inside an HTML comment `<!-- ... -->` is stripped (anywhere).
  - Inside a footnote, anything after a dagger `†` is an internal note (verify:/
    todo:/attribute:) and is dropped. Put "Verify X before print" style notes
    after a `†` so they auto-strip at publish.
  - Safety net: a trailing `Verify ….` sentence in a footnote is also dropped.
  - GUARD: if a footnote still contains the word "verify" after cleaning, the
    tool prints a WARNING and exits non-zero unless --allow-verify is passed, so
    an unresolved editorial note can never silently ship. Run verification, then
    move the note behind a `†` (or delete it), then re-run.
"""
import sys, os, re, json, base64, mimetypes

def read_manifest(path):
    m = {}
    if os.path.exists(path):
        for line in open(path):
            line = line.split('#', 1)[0].rstrip()
            if ':' in line and not line.startswith((' ', '\t')):
                k, v = line.split(':', 1)
                m[k.strip()] = v.strip()
    return m

def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def data_uri(piece_dir, rel):
    fp = os.path.join(piece_dir, rel)
    mime = mimetypes.guess_type(fp)[0] or 'image/png'
    b64 = base64.b64encode(open(fp, 'rb').read()).decode()
    return f'data:{mime};base64,{b64}'

def inline(text, piece_dir):
    text = esc(text)
    text = re.sub(r'\[\^(\w+)\]', r'[[FN\1]]', text)                 # footnote refs -> markers
    def img(m):
        return f'<figure><img src="{data_uri(piece_dir, m.group(2))}" alt="{esc(m.group(1))}"></figure>'
    text = re.sub(r'!\[(.*?)\]\((.*?)\)', img, text)
    # link text may not contain brackets, so a nearby footnote marker ([[FNx]]) can't be
    # swallowed into the link when a link and a marker share a paragraph
    text = re.sub(r'\[([^\[\]]+?)\]\(([^)]+?)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    return text

def clean_footnote(raw):
    """Drop internal editorial notes from a footnote's text.
    Returns (cleaned_text, was_stripped)."""
    cleaned = re.sub(r'\s*[†‡].*$', '', raw, flags=re.S)             # dagger-delimited tail
    cleaned = re.sub(r'\s*\bVerify\b[^.]*\.\s*$', '', cleaned, flags=re.S)  # trailing "Verify …."
    return cleaned.strip(), (cleaned.strip() != raw.strip())

def parse_blocks(piece_dir):
    """Parse draft.md into (blocks, footnotes_ordered, stripped, residual).
    `blocks` is the ordered list of body-block HTML strings (<p>/<h2>/<h3>/<hr>/
    <blockquote>/<figure>), each carrying [[FNn]] markers where a ref appeared.
    `footnotes_ordered` is [[n, contentHTML], ...] with internal notes stripped.
    This is the shared parser behind both convert() (fresh publish) and
    render_reader() (surgical republish)."""
    src = open(os.path.join(piece_dir, 'draft.md')).read()
    src = re.sub(r'<!--.*?-->', '', src, flags=re.S)                 # strip HTML comments
    lines = src.split('\n')
    for i, ln in enumerate(lines):                                  # drop front-matter
        if ln.strip() == '---':
            lines = lines[i + 1:]
            break
    body = '\n'.join(lines).strip()

    footnotes = {}                                                   # n -> content HTML
    stripped = 0                                                     # editorial notes removed
    out = []
    for block in re.split(r'\n\s*\n', body):
        b = block.strip()
        if not b:
            continue
        m = re.match(r'^\[\^(\w+)\]:\s?(.*)$', b, re.S)              # footnote definition
        if m:
            raw = ' '.join(m.group(2).split('\n'))
            text, was_stripped = clean_footnote(raw)
            stripped += 1 if was_stripped else 0
            footnotes[m.group(1)] = inline(text, piece_dir)
            continue
        if b == '---':
            out.append('<hr>')
        elif b.startswith('### '):
            out.append('<h3>' + inline(b[4:], piece_dir) + '</h3>')
        elif b.startswith('## '):
            out.append('<h2>' + inline(b[3:], piece_dir) + '</h2>')
        elif b.startswith('!['):
            out.append(inline(b, piece_dir))
        elif b.startswith('> '):
            # blockquote: strip the '> ' from every line, join, emit one <blockquote>.
            # Without this the marker survives into the paragraph and is escaped to '&gt;'.
            quoted = ' '.join(re.sub(r'^>\s?', '', ln) for ln in b.split('\n'))
            out.append('<blockquote><p>' + inline(quoted, piece_dir) + '</p></blockquote>')
        else:
            out.append('<p>' + inline(' '.join(b.split('\n')), piece_dir) + '</p>')

    # footnotes in numeric order where possible (Substack renumbers by position anyway)
    def key(n):
        return (0, int(n)) if n.isdigit() else (1, n)
    ordered = [[n, footnotes[n]] for n in sorted(footnotes, key=key)]
    residual = [n for n, c in ordered if re.search(r'verify', c, re.I)]
    return out, ordered, stripped, residual

def convert(piece_dir):
    blocks, ordered, stripped, residual = parse_blocks(piece_dir)
    return '\n'.join(blocks), ordered, stripped, residual

def strip_to_reader(html_fragment):
    """Reduce a block/footnote HTML fragment to the plain reader-text that the
    live Substack editor actually holds: drop [[FNn]] markers (they became native
    footnotes), drop tags, unescape the three entities esc() introduces, collapse
    whitespace. This is the domain the surgical diff and the live doc share."""
    s = re.sub(r'\[\[FN\w+\]\]', '', html_fragment)
    s = re.sub(r'<[^>]+>', '', s)
    s = s.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return re.sub(r'\s+', ' ', s).strip()

def render_reader(piece_dir):
    """(title-independent) reader-text view of the piece, for surgical republish:
    (body_texts, footnote_texts, residual). body_texts drops <hr>/empty blocks so
    it aligns 1:1 with the live doc's non-empty, non-footnote top nodes; footnote_texts
    is in the same numeric order the composer inserts them (= live doc order)."""
    blocks, ordered, stripped, residual = parse_blocks(piece_dir)
    body = []
    for b in blocks:
        if b.strip() == '<hr>':
            continue
        txt = strip_to_reader(b)
        if txt:
            body.append(txt)
    fns = [strip_to_reader(c) for _n, c in ordered]
    return body, fns, residual

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    allow_verify = '--allow-verify' in sys.argv
    piece_dir = args[0].rstrip('/')
    out_js = args[1] if len(args) > 1 else 'paste.js'
    man = read_manifest(os.path.join(piece_dir, 'publish.yaml'))
    html, footnotes, stripped, residual = convert(piece_dir)
    js = (JS_TEMPLATE
          .replace('%TITLE%', json.dumps(man.get('title', '')))
          .replace('%SUBTITLE%', json.dumps(man.get('subtitle', '')))
          .replace('%BODY%', json.dumps(html))
          .replace('%FOOTNOTES%', json.dumps(footnotes)))
    print(f"paragraphs~{html.count('<p>')}  headings~{html.count('<h2>')+html.count('<h3>')}  "
          f"dividers~{html.count('<hr>')}  images~{html.count('<img')}  footnotes~{len(footnotes)}  "
          f"editorial-notes-stripped~{stripped}")
    if residual:
        print(f"WARNING: {len(residual)} footnote(s) still contain 'verify' after cleaning: "
              f"{residual}. Verify the claim, then move the note behind a † (or delete it).")
        if not allow_verify:
            print("Refusing to write output. Re-run with --allow-verify to override.")
            sys.exit(2)
    open(out_js, 'w').write(js)
    print(f"wrote {out_js} ({len(js)} bytes)")

JS_TEMPLATE = """(() => {
  const setField = (el, v) => { if (!el) return; const d = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value'); d.set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); };
  setField(document.querySelector('textarea[placeholder="Title"]'), %TITLE%);
  setField(document.querySelector('textarea[placeholder="Add a subtitle\\u2026"]'), %SUBTITLE%);
  const pm = document.querySelector('.ProseMirror'); pm.focus();
  const dt = new DataTransfer(); dt.setData('text/html', %BODY%);
  pm.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
  window.__sbFN = %FOOTNOTES%;
  window.__sbInsertFootnotes = () => {
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
  };
  return 'body pasted (' + document.querySelectorAll('.ProseMirror > *').length + ' blocks pre-async); next: window.__sbInsertFootnotes()';
})()
"""

if __name__ == '__main__':
    main()
