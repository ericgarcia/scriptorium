#!/usr/bin/env python3
"""check_commonmark.py — does a draft's markup survive a strict markdown parser?

WHY THIS EXISTS (2026-09-11)
  The desk composes Substack through its own converter, which is lenient. Every
  other outlet renders the same draft through a CommonMark parser, which is not.
  So markup can be right on one outlet and broken on another, and every check the
  desk had compared the draft against the outlet that tolerated it.

  Found live on alignmentfellowship, both reader-visible:
    not-yet         `autobiography,* Confessions*, know…*` — in CommonMark a `*` after
                    a letter and before a comma cannot open emphasis; readers saw two
                    literal asterisks. Substack rendered it correctly.
    son-of-joseph   ʿayin written as a backtick (*`almah*) — a backtick opens inline
                    code, which swallowed the italics; readers saw stray asterisks, and
                    Substack readers saw a literal backtick where ʿ belongs.

WHAT IT FLAGS
  stray-asterisk        emphasis markup that renders as a literal `*` under CommonMark.
                        Escaped asterisks (\\*) are intentional — the house censoring
                        convention — and are not counted; nor is anything in code.
  backtick-letter-mark  a lone backtick glued to the front of a word, used as a letter
                        (ʿayin, ʾaleph). Write the letter itself: ʿ (U+02BF), ʾ (U+02BE).

USAGE
  python3 check_commonmark.py pieces/<slug> [...]
  python3 check_commonmark.py --all

EXIT
  0 clean · 3 findings · 1 usage · 2 could not check (markdown-it-py missing).
  "Could not check" is never reported as a pass.
"""
import sys, os, re, html


def _md():
    try:
        from markdown_it import MarkdownIt
    except ImportError:
        return None
    return MarkdownIt('commonmark')


def blocks_of(src):
    """Reader-facing blocks: below the first `---`, comments and fenced code removed,
    and a footnote definition reduced to its body so it renders as prose."""
    parts = src.split('\n---\n', 1)
    body = parts[1] if len(parts) > 1 else src
    body = re.sub(r'<!--.*?-->', ' ', body, flags=re.S)
    body = re.sub(r'```.*?```', ' ', body, flags=re.S)
    for block in re.split(r'\n\s*\n', body):
        if block.strip():
            yield re.sub(r'^\[\^[\w-]+\]:\s*', '', block)


LETTER_MARK = re.compile(r'(?<![`\w])`([^\W\d_][\ẁ-ͯ]*)(?![`\w])')


def check_text(src, md):
    found = []
    for block in blocks_of(src):
        flat = ' '.join(block.split())
        for m in LETTER_MARK.finditer(block):
            same_line_rest = block[m.end():].split('\n', 1)[0]
            if '`' in same_line_rest:          # a paired `code span`, not a letter mark
                continue
            i = flat.find('`' + m.group(1))
            found.append(('backtick-letter-mark', flat[max(0, i - 40):i + 50]))
        if '*' not in block:
            continue
        h = md.render(block)
        h = re.sub(r'<code>.*?</code>', ' ', h, flags=re.S)   # code may hold asterisks
        rendered = ' '.join(html.unescape(re.sub(r'<[^>]+>', '', h)).split())
        stray = rendered.count('*') - block.count('\\*')
        if stray > 0:
            i = rendered.find('*')
            found.append(('stray-asterisk', rendered[max(0, i - 50):i + 50]))
    return found


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if '--all' in sys.argv:
        args = sorted(os.path.join('pieces', d) for d in os.listdir('pieces')
                      if os.path.exists(os.path.join('pieces', d, 'draft.md')))
    if not args:
        print(__doc__.strip()); sys.exit(1)
    md = _md()
    if md is None:
        print("could not check: markdown-it-py is not installed (pip install markdown-it-py). "
              "This is NOT a pass.")
        sys.exit(2)
    total = checked = 0
    for pd in args:
        p = os.path.join(pd, 'draft.md')
        if not os.path.exists(p):
            continue
        checked += 1
        for kind, ctx in check_text(open(p, encoding='utf-8').read(), md):
            print(f"  {os.path.basename(pd.rstrip('/')):34s} {kind:22s} …{ctx}…")
            total += 1
    print(f"{checked} draft(s) checked under CommonMark, {total} finding(s)")
    sys.exit(3 if total else 0)


if __name__ == '__main__':
    main()
