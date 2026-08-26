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
    text = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    return text

def convert(piece_dir):
    src = open(os.path.join(piece_dir, 'draft.md')).read()
    src = re.sub(r'<!--.*?-->', '', src, flags=re.S)                 # strip HTML comments
    lines = src.split('\n')
    for i, ln in enumerate(lines):                                  # drop front-matter
        if ln.strip() == '---':
            lines = lines[i + 1:]
            break
    body = '\n'.join(lines).strip()

    footnotes = {}                                                   # n -> content HTML
    out = []
    for block in re.split(r'\n\s*\n', body):
        b = block.strip()
        if not b:
            continue
        m = re.match(r'^\[\^(\w+)\]:\s?(.*)$', b, re.S)              # footnote definition
        if m:
            footnotes[m.group(1)] = inline(' '.join(m.group(2).split('\n')), piece_dir)
            continue
        if b == '---':
            out.append('<hr>')
        elif b.startswith('### '):
            out.append('<h3>' + inline(b[4:], piece_dir) + '</h3>')
        elif b.startswith('## '):
            out.append('<h2>' + inline(b[3:], piece_dir) + '</h2>')
        elif b.startswith('!['):
            out.append(inline(b, piece_dir))
        else:
            out.append('<p>' + inline(' '.join(b.split('\n')), piece_dir) + '</p>')

    # footnotes in numeric order where possible (Substack renumbers by position anyway)
    def key(n):
        return (0, int(n)) if n.isdigit() else (1, n)
    ordered = [[n, footnotes[n]] for n in sorted(footnotes, key=key)]
    return '\n'.join(out), ordered

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

def main():
    piece_dir = sys.argv[1].rstrip('/')
    out_js = sys.argv[2] if len(sys.argv) > 2 else 'paste.js'
    man = read_manifest(os.path.join(piece_dir, 'publish.yaml'))
    html, footnotes = convert(piece_dir)
    js = (JS_TEMPLATE
          .replace('%TITLE%', json.dumps(man.get('title', '')))
          .replace('%SUBTITLE%', json.dumps(man.get('subtitle', '')))
          .replace('%BODY%', json.dumps(html))
          .replace('%FOOTNOTES%', json.dumps(footnotes)))
    open(out_js, 'w').write(js)
    print(f"paragraphs~{html.count('<p>')}  headings~{html.count('<h2>')+html.count('<h3>')}  "
          f"dividers~{html.count('<hr>')}  images~{html.count('<img')}  footnotes~{len(footnotes)}")
    print(f"wrote {out_js} ({len(js)} bytes)")

if __name__ == '__main__':
    main()
