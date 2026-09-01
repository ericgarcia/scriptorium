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
  - GUARD 1 (malformed note): if a footnote still contains "verify" AFTER
    cleaning, exit non-zero unless --allow-verify. Catches a note someone forgot
    to put behind a dagger.
  - GUARD 2 (the real one): a `†` note whose text looks like an unverified-claim
    marker (verify/todo/tk/check/confirm/pin/source/cite) exits non-zero unless
    --allow-unverified. This is checked against the text that was REMOVED.
    Guard 1 alone was structurally inert: the documented convention is to put
    verify notes behind a `†`, which strips them before Guard 1 ever looks — so a
    well-formed note always passed. A draft carrying 17 of them converted clean
    (2026-08-29). A `†` marker means the claim is UNVERIFIED; publishing it
    silently is exactly the failure these guards exist to prevent.
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

# An editorial note that matches this is an UNVERIFIED-CLAIM marker, not a
# harmless aside. Stripping one silently is the failure this guard exists to
# stop, so it is checked against the text that was REMOVED, not what survived.
UNVERIFIED_RE = re.compile(r'\b(verify|todo|tk|check|confirm|pin|source|cite)\b', re.I)

def clean_footnote(raw):
    """Drop internal editorial notes from a footnote's text.
    Returns (cleaned_text, removed_note_text)."""
    cleaned = re.sub(r'\s*[†‡].*$', '', raw, flags=re.S)             # dagger-delimited tail
    cleaned = re.sub(r'\s*\bVerify\b[^.]*\.\s*$', '', cleaned, flags=re.S)  # trailing "Verify …."
    cleaned = cleaned.strip()
    removed = ''
    if cleaned != raw.strip():
        m = re.search(r'[†‡](.*)$', raw, flags=re.S)
        removed = (m.group(1) if m else raw.strip()[len(cleaned):]).strip()
    return cleaned, removed

def render_block(b, piece_dir):
    """Render ONE stripped markdown block to its body HTML. Factored out of parse_blocks
    so a caller that has edited a block's source can re-render just that block and check
    what it actually produces — which is how substack_sync verifies a pulled edit landed
    as the text it meant, instead of trusting an offset map."""
    if b == '---':
        return '<hr>'
    if b.startswith('### '):
        return '<h3>' + inline(b[4:], piece_dir) + '</h3>'
    if b.startswith('## '):
        return '<h2>' + inline(b[3:], piece_dir) + '</h2>'
    if b.startswith('!['):
        return inline(b, piece_dir)
    if b.startswith('> '):
        # blockquote: strip the '> ' from every line, join, emit one <blockquote>.
        # Without this the marker survives into the paragraph and is escaped to '&gt;'.
        quoted = ' '.join(re.sub(r'^>\s?', '', ln) for ln in b.split('\n'))
        return '<blockquote><p>' + inline(quoted, piece_dir) + '</p></blockquote>'
    return '<p>' + inline(' '.join(b.split('\n')), piece_dir) + '</p>'

def parse_blocks(piece_dir):
    """Parse draft.md into (blocks, footnotes_ordered, stripped, residual).
    `blocks` is the ordered list of body-block HTML strings (<p>/<h2>/<h3>/<hr>/
    <blockquote>/<figure>), each carrying [[FNn]] markers where a ref appeared.
    `footnotes_ordered` is [[n, contentHTML], ...] in FIRST-REFERENCE order, with
    internal notes stripped; `fn_issues` reports refs/definitions that don't pair up.
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
    fn_src = {}                                                      # n -> raw markdown source
    stripped = 0                                                     # editorial notes removed
    unverified = []                                                  # (id, note) for verify-markers
    out, out_src = [], []                                            # HTML block + its raw source
    for block in re.split(r'\n\s*\n', body):
        b = block.strip()
        if not b:
            continue
        m = re.match(r'^\[\^(\w+)\]:\s?(.*)$', b, re.S)              # footnote definition
        if m:
            raw = ' '.join(m.group(2).split('\n'))
            text, removed = clean_footnote(raw)
            if removed:
                stripped += 1
                if UNVERIFIED_RE.search(removed):
                    unverified.append((m.group(1), ' '.join(removed.split())[:90]))
            footnotes[m.group(1)] = inline(text, piece_dir)
            fn_src[m.group(1)] = b
            continue
        out_src.append(b)
        out.append(render_block(b, piece_dir))

    # Footnotes in FIRST-REFERENCE order — the order the composer actually inserts them
    # (it walks the body's markers in document order), and therefore the order the live
    # doc holds them in.
    #
    # This was previously sorted by LABEL — numerics first, then alphabetically — on the
    # reasoning that "Substack renumbers by position anyway." That is true for composing
    # and false for the surgical re-sync, which aligns footnote nodes 1:1 BY INDEX. Any
    # draft whose labels are named (`[^kjv]`) or no longer in citation order then paired
    # every footnote against the wrong live node — and the count-only structural guard
    # could not see it, because a permutation preserves the count. Real case: `In the
    # Name` (2026-09-01) rendered footnote #0 as `John 10:3` against a live #0 that was
    # the shelucho-shel-adam maxim; 30 == 30, zero aligned, and a re-sync would have
    # overwritten all thirty notes of a live essay with mismatched text.
    seen, ref_order, duplicated = set(), [], []
    for blk in out:
        for ref in re.finditer(r'\[\[FN(\w+)\]\]', blk):
            n = ref.group(1)
            if n in seen:
                duplicated.append(n)                                 # 2nd ref => 2nd live node
                continue
            seen.add(n)
            ref_order.append(n)
    fn_issues = {
        'undefined':    [n for n in ref_order if n not in footnotes],   # ref with no definition
        'unreferenced': [n for n in footnotes if n not in seen],        # definition never cited
        'duplicated':   sorted(set(duplicated)),                        # cited more than once
    }
    ordered = [[n, footnotes[n]] for n in ref_order if n in footnotes]
    residual = [n for n, c in ordered if re.search(r'verify', c, re.I)]
    sources = {'body': out_src, 'fns': [fn_src[n] for n, _c in ordered]}
    return out, ordered, stripped, residual, unverified, fn_issues, sources

def convert(piece_dir):
    blocks, ordered, stripped, residual, unverified, fn_issues, _src = parse_blocks(piece_dir)
    return '\n'.join(blocks), ordered, stripped, residual, unverified, fn_issues

# --- typography -------------------------------------------------------------
# Substack's editor (ProseMirror smart-quote input rules) converts straight quotes
# to curly ones as the body is pasted. draft.md is written with straight quotes, so
# the composed live post and the draft's reader-text disagree on every apostrophe
# and quotation mark forever after. Nothing normalized them, so a surgical re-sync
# saw a diff in every quote-bearing block and would have rewritten each one — mass
# typographic damage disguised as a one-word touch-up (found 2026-09-01).
#
# The diff domain therefore compares FLATTENED text (curly -> straight), while any
# run actually inserted into the live doc is SMARTENED (straight -> curly) so it
# matches the typography of the document it lands in.

def flatten_quotes(s):
    """Curly quotes -> straight. The comparison domain; never inserted."""
    return (s.replace('\u2018', "'").replace('\u2019', "'")
             .replace('\u201c', '"').replace('\u201d', '"'))

def smarten_quotes(s):
    """Straight quotes -> curly, by the usual boundary rule: a quote that follows
    whitespace, an opening bracket or a dash opens; anything else closes."""
    out, opening = [], set(' \t\n(【[{\u2014\u2013-\u201c\u2018')
    for i, ch in enumerate(s):
        if ch in '"\'':
            prev = s[i - 1] if i else ' '
            opens = prev in opening
            if ch == '"':
                out.append('\u201c' if opens else '\u201d')
            else:
                out.append('\u2018' if opens else '\u2019')
        else:
            out.append(ch)
    return ''.join(out)

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
    is in first-reference order — the order the composer inserts them, which is the
    order the live doc holds. `fn_issues` surfaces refs/definitions that don't pair
    up, any of which would shift that alignment."""
    blocks, ordered, stripped, residual, _unverified, fn_issues, sources = parse_blocks(piece_dir)
    body, body_src = [], []
    for b, bsrc in zip(blocks, sources['body']):
        if b.strip() == '<hr>':
            continue
        txt = strip_to_reader(b)
        if txt:
            body.append(txt)
            body_src.append(bsrc)                                    # stays 1:1 with `body`
    fns = [strip_to_reader(c) for _n, c in ordered]
    render_reader.sources = {'body': body_src, 'fns': sources['fns']}
    return body, fns, residual, fn_issues

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    allow_verify = '--allow-verify' in sys.argv
    allow_unverified = '--allow-unverified' in sys.argv
    piece_dir = args[0].rstrip('/')
    out_js = args[1] if len(args) > 1 else 'paste.js'
    man = read_manifest(os.path.join(piece_dir, 'publish.yaml'))
    html, footnotes, stripped, residual, unverified, fn_issues = convert(piece_dir)
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
    if fn_issues['undefined'] or fn_issues['duplicated']:
        # Either one changes how many footnote nodes the composer creates, which
        # desynchronizes every later index for a subsequent surgical re-sync.
        if fn_issues['undefined']:
            print(f"WARNING: footnote ref(s) with no definition, which publish as raw "
                  f"markers: {fn_issues['undefined']}")
        if fn_issues['duplicated']:
            print(f"WARNING: footnote(s) cited more than once: {fn_issues['duplicated']}. "
                  f"Each extra citation becomes its own live footnote node.")
        sys.exit(4)
    if fn_issues['unreferenced']:
        print(f"NOTE: {len(fn_issues['unreferenced'])} footnote definition(s) are never cited "
              f"and will not appear in the post: {fn_issues['unreferenced']}")
    if unverified:
        print(f"WARNING: {len(unverified)} footnote(s) carry an UNVERIFIED-CLAIM marker that "
              f"would be stripped and published as fact:")
        for n, note in unverified:
            print(f"  [^{n}]  † {note}")
        if not allow_unverified:
            print("Refusing to write output. Verify the claims and clear the notes, or re-run "
                  "with --allow-unverified if these are genuinely not verify-markers.")
            sys.exit(3)
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
