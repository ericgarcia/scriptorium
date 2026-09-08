#!/usr/bin/env python3
"""
md_to_marp.py — turn a talk piece's draft.md into a Marp deck with speaker notes.

THE DIALECT (kept deliberately small — see skills/talk/SKILL.md)

    <header above the first --- is scaffold and is discarded, as in every piece>
    ---
    ## I. The Setup                      -> a section title slide (the movement)
    <!-- slide: The promise -->          -> starts a slide titled "The promise"
    > A line that appears on the slide   -> blockquote  = on-slide text
    - a bullet                           -> list        = on-slide bullets
    ![alt](assets/fig1.png)              -> image       = on-slide figure
    Plain paragraphs are the SPOKEN SCRIPT and become the slide's presenter notes.
    <!-- slide -->                       -> a slide with no title (a figure alone, a beat)

So the script is prose and the slide is everything that is not prose. A talk is drafted the
way an essay is — the argument in paragraphs — and the deck falls out of it: nothing on a
slide that the speaker did not write, and no speaker line that the audience has to read.

MANIFEST  pieces/<slug>/talk.yaml (flat key: value; the same reader as publish.yaml)
    title, subtitle, speaker, duration_min, theme (default|gaia|uncover), size (16:9|4:3),
    paginate (true|false), footer, out (deck filename, default deck.md)

OUTPUT    pieces/<slug>/<out> — Marp markdown. Render with
    npx -y @marp-team/marp-cli <deck.md> -o deck.html      (or -o deck.pdf; PDF needs Chrome)
Images are referenced relative to the piece directory, so render from inside it or pass
--allow-local-files.

USAGE     python3 md_to_marp.py pieces/<slug> [--out deck.md] [--check]
    --check  exit 2 if a figure the draft references is missing on disk, or a slide has no
             notes at all (a slide the speaker has nothing to say over is usually a mistake).
EXIT      0 written · 1 usage · 2 --check found a fault
"""
import os, re, sys

FIG_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
SLIDE_RE = re.compile(r'<!--\s*slide(?:\s*:\s*(.*?))?\s*-->')
MOVEMENT_RE = re.compile(r'^##\s+(.*)$')


def read_manifest(path):
    man = {}
    if not os.path.exists(path):
        return man
    for ln in open(path, encoding='utf-8'):
        s = ln.split('#', 1)[0].rstrip()
        if not s or s.startswith(' ') or ':' not in s:
            continue
        k, v = s.split(':', 1)
        man[k.strip()] = v.strip().strip('"').strip("'")
    return man


def body_of(text):
    """Everything below the first `---` line; the header above it is scaffold."""
    lines = text.split('\n')
    for i, l in enumerate(lines):
        if l.strip() == '---':
            return '\n'.join(lines[i + 1:])
    return text


def parse(text):
    """-> [{'kind': 'section'|'slide', 'title': str, 'on': [lines], 'notes': [paragraphs]}]"""
    slides, cur = [], None
    para = []

    def flush_para():
        nonlocal para
        if para and cur is not None:
            cur['notes'].append(' '.join(s.strip() for s in para))
        para = []

    for raw in body_of(text).split('\n'):
        line = raw.rstrip()
        m = MOVEMENT_RE.match(line)
        if m:
            flush_para()
            cur = {'kind': 'section', 'title': m.group(1).strip(), 'on': [], 'notes': []}
            slides.append(cur)
            continue
        m = SLIDE_RE.search(line)
        if m:
            flush_para()
            cur = {'kind': 'slide', 'title': (m.group(1) or '').strip(), 'on': [], 'notes': []}
            slides.append(cur)
            continue
        if cur is None:
            continue                                    # prose before any movement: dropped
        if line.startswith('<!--'):
            continue                                    # other comments are scaffold
        if not line.strip():
            flush_para(); continue
        if line.startswith('>') or re.match(r'^\s*([-*]|\d+\.)\s+', line) or FIG_RE.match(line.strip()) \
                or line.startswith('#'):
            flush_para()
            cur['on'].append(line)
        else:
            para.append(line)
    flush_para()
    return slides


def render(slides, man, piece_dir):
    theme = man.get('theme', 'default'); size = man.get('size', '16:9')
    head = ['---', 'marp: true', f'theme: {theme}', f'size: {size}',
            f"paginate: {man.get('paginate', 'true')}"]
    if man.get('footer'):
        head.append(f"footer: '{man['footer']}'")
    head.append('---')
    out = ['\n'.join(head), '']
    # title slide
    out.append('<!-- _paginate: false -->')
    out.append(f"# {man.get('title', 'Untitled')}")
    if man.get('subtitle'):
        out.append(f"\n## {man['subtitle']}")
    if man.get('speaker'):
        out.append(f"\n{man['speaker']}")
    out.append('')
    for s in slides:
        out.append('---\n')
        if s['kind'] == 'section':
            out.append('<!-- _class: lead -->')
            out.append(f"# {s['title']}")
        else:
            if s['title']:
                out.append(f"## {s['title']}")
        for l in s['on']:
            # a figure fills the slide's free height: Marp reads `h:` from the alt text
            m = FIG_RE.match(l.strip())
            if m and not re.search(r'\b(h|w|height|width):', m.group(1)):
                h = 520 if s['title'] else 600
                l = f"![{m.group(1)} h:{h}px]({m.group(2)})"
            out.append(l)
        if s['notes']:
            notes = '\n\n'.join(s['notes']).replace('-->', '--​>')
            out.append('')
            out.append(f'<!--\n{notes}\n-->')
        out.append('')
    return '\n'.join(out)


def check(slides, piece_dir):
    faults = []
    for i, s in enumerate(slides):
        for l in s['on']:
            m = FIG_RE.search(l)
            if m and not os.path.exists(os.path.join(piece_dir, m.group(2))):
                faults.append(f"slide {i+1} ({s['title'] or s['kind']}): missing figure {m.group(2)}")
        if s['kind'] == 'slide' and not s['notes']:
            faults.append(f"slide {i+1} ({s['title'] or 'untitled'}): no speaker notes")
    return faults


def per_movement(slides, outline_path):
    """(title, spoken words, outline minutes or None) per movement. Minutes come from the
    outline heading that shares the movement's leading numeral — `## II. The Geometry (12 min)`."""
    budgets = {}
    if os.path.exists(outline_path):
        for ln in open(outline_path, encoding='utf-8'):
            m = re.match(r'^##\s+([IVXLC]+|\d+)[.)]?\s.*?\((\d+)\s*min\)', ln)
            if m:
                budgets[m.group(1)] = int(m.group(2))
    out, cur, words = [], None, 0
    for s in slides:
        if s['kind'] == 'section':
            if cur is not None:
                out.append((cur, words, budgets.get(cur.split('.')[0].split()[0])))
            cur, words = s['title'], 0
        words += len(' '.join(s['notes']).split())
    if cur is not None:
        out.append((cur, words, budgets.get(cur.split('.')[0].split()[0])))
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print(__doc__); sys.exit(1)
    piece = args[0].rstrip('/')
    man = read_manifest(os.path.join(piece, 'talk.yaml'))
    out_name = man.get('out', 'deck.md')
    if '--out' in sys.argv:
        out_name = sys.argv[sys.argv.index('--out') + 1]
    text = open(os.path.join(piece, 'draft.md'), encoding='utf-8').read()
    slides = parse(text)
    faults = check(slides, piece)
    n_sec = sum(1 for s in slides if s['kind'] == 'section')
    n_sl = len(slides) - n_sec
    words = sum(len(' '.join(s['notes']).split()) for s in slides)
    deck = render(slides, man, piece)
    out_path = os.path.join(piece, out_name)
    open(out_path, 'w', encoding='utf-8').write(deck)
    wpm = float(man.get('pace_wpm', 130))
    print(f"wrote {out_path}: {n_sec} movements, {n_sl} slides (+ title), {words} spoken words "
          f"(~{words/wpm:.0f} min at {wpm:.0f} wpm; talk.yaml says {man.get('duration_min', '?')})")
    for title, w, budget in per_movement(slides, os.path.join(piece, 'outline.md')):
        flag = ''
        if budget:
            mins = w / wpm
            flag = f"  outline {budget} min" + ('  OVER' if mins > budget * 1.1 else '  under' if mins < budget * 0.8 else '')
        print(f"  {title[:40]:40s} {w:5d} words  ~{w/wpm:4.1f} min{flag}")
    for f in faults:
        print('  fault:', f)
    if faults and '--check' in sys.argv:
        sys.exit(2)


if __name__ == '__main__':
    main()
