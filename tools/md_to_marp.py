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
    <!-- design: put the spike on the right -->   -> a note for the slide's designer; never rendered

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

USAGE     python3 md_to_marp.py pieces/<slug> [--out deck.md] [--check] [--briefs]
    --check  exit 2 if a figure the draft references is missing on disk, or a slide has no
             notes at all (a slide the speaker has nothing to say over is usually a mistake).
    --briefs also write pieces/<slug>/slides/ — one brief per slide (NN-<title>.md: what is on
             it verbatim, the figure, what is said over it, the design note) and an index
             README.md — the folder handed to a designer (Claude Design) slide by slide. The
             general visual style doc, slides/00-style.md, is the author's and is never
             overwritten; the template scaffolds one.
EXIT      0 written · 1 usage · 2 --check found a fault
"""
import os, re, sys

FIG_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
SLIDE_RE = re.compile(r'<!--\s*slide(?:\s*:\s*(.*?))?\s*-->')
DESIGN_RE = re.compile(r'<!--\s*design\s*:\s*(.*?)\s*-->', re.S)
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
            cur = {'kind': 'section', 'title': m.group(1).strip(), 'on': [], 'notes': [], 'design': []}
            slides.append(cur)
            continue
        m = SLIDE_RE.search(line)
        if m:
            flush_para()
            cur = {'kind': 'slide', 'title': (m.group(1) or '').strip(), 'on': [], 'notes': [], 'design': []}
            slides.append(cur)
            continue
        if cur is None:
            continue                                    # prose before any movement: dropped
        if line.startswith('<!--'):
            dm = DESIGN_RE.search(line)
            if dm:
                flush_para(); cur['design'].append(dm.group(1).strip())
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
    head.append('style: "img { display: block; margin: 0 auto; }"')   # a figure sits centered, not flush left
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
            # a figure fills the slide's free box: Marp reads `h:`/`w:` from the alt text. Size by
            # whichever side binds, or a wide figure (an attribution card at 2.4:1) gets a fixed
            # height, is clamped to the slide width by CSS, and renders squeezed.
            m = FIG_RE.match(l.strip())
            if m and not re.search(r'\b(h|w|height|width):', m.group(1)):
                box_h = 520 if s['title'] else 600
                box_w = 1150
                dims = png_size(os.path.join(piece_dir, m.group(2)))
                if dims and dims[0] / dims[1] > box_w / box_h:
                    l = f"![{m.group(1)} w:{box_w}px]({m.group(2)})"
                else:
                    l = f"![{m.group(1)} h:{box_h}px]({m.group(2)})"
            out.append(l)
        if s['notes']:
            notes = '\n\n'.join(s['notes']).replace('-->', '--​>')
            out.append('')
            out.append(f'<!--\n{notes}\n-->')
        out.append('')
    return '\n'.join(out)


def png_size(path):
    """(width, height) from a PNG's IHDR, or None. No imaging library needed."""
    try:
        with open(path, 'rb') as f:
            head = f.read(24)
        if head[:8] != b'\x89PNG\r\n\x1a\n' or head[12:16] != b'IHDR':
            return None
        import struct
        return struct.unpack('>II', head[16:24])
    except OSError:
        return None


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
            m = re.match(r'^##\s+([IVXLC]+|\d+)[.)]?\s.*?\((\d+(?:\.\d+)?)\s*min\)', ln)
            if m:
                budgets[m.group(1)] = float(m.group(2))
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


def slug_of(title, fallback):
    t = re.sub(r"[^a-z0-9]+", "-", (title or fallback).lower()).strip("-")
    return t[:48] or fallback


def kind_of(s):
    if s['kind'] == 'section':
        return 'section'
    has_fig = any(FIG_RE.search(l) for l in s['on'])
    has_list = any(re.match(r'^\s*([-*]|\d+\.)\s+', l) for l in s['on'])
    if has_fig:
        return 'figure'
    if has_list:
        return 'bullets'
    return 'claim' if s['on'] else 'beat'


def write_briefs(slides, man, piece_dir):
    """slides/NN-<title>.md per slide + README.md index. 00-style.md is the author's; kept."""
    out_dir = os.path.join(piece_dir, 'slides')
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):                        # regenerate cleanly; keep the style doc
        if re.match(r'^\d{2}-', f) and f != '00-style.md':
            os.remove(os.path.join(out_dir, f))
    title = man.get('title', 'Untitled')
    entries = [{'kind': 'title', 'title': title, 'on': [f"# {title}"] + ([f"## {man['subtitle']}"] if man.get('subtitle') else []) + ([man['speaker']] if man.get('speaker') else []), 'notes': [], 'design': []}] + slides
    def label_of(s):
        """A slide's name for humans: its title, else its figure's alt, else its first line."""
        if s['title']:
            return s['title']
        fm = next((FIG_RE.search(l) for l in s['on'] if FIG_RE.search(l)), None)
        if fm:
            return re.sub(r'\s+(h|w|height|width):\S+', '', fm.group(1)) or os.path.splitext(os.path.basename(fm.group(2)))[0]
        if s['on']:
            return ' '.join(re.sub(r'^[>\-*\d.\s]+', '', s['on'][0]).split()[:8])
        return ''
    movement = ''
    rows = []
    n = len(entries)
    for i, s in enumerate(entries, 1):
        if s['kind'] == 'section':
            movement = s['title']
        k = 'title' if s['kind'] == 'title' else kind_of(s)
        label = label_of(s)
        fm = next((FIG_RE.search(l) for l in s['on'] if FIG_RE.search(l)), None)
        file_label = s['title'] or (os.path.splitext(os.path.basename(fm.group(2)))[0] if fm else label)
        name = f"{i:02d}-{slug_of(file_label, k)}.md"
        prev_t = label_of(entries[i-2]) if i > 1 else '—'
        next_t = label_of(entries[i]) if i < n else '—'
        figs = [FIG_RE.search(l) for l in s['on']]
        figs = [m for m in figs if m]
        lines = [f"# Slide {i:02d} — {label or k}", '',
                 f"**Kind:** {k} · **Movement:** {movement or '—'} · **Position:** {i} of {n} · "
                 f"**Previous:** {prev_t or '(untitled)'} · **Next:** {next_t or '(untitled)'}", '',
                 '## On the slide — verbatim, and nothing else', '']
        lines += [l for l in s['on'] if not FIG_RE.search(l)] or ['*(no text — the figure, or the section title, is the slide)*']
        if figs:
            lines += ['', '## Figure', '']
            for m in figs:
                alt = re.sub(r'\s+(h|w|height|width):\S+', '', m.group(1))
                lines.append(f"- `{m.group(2)}` — {alt}. Generated by `assets/figures.py`; place it, do not redraw it. "
                             f"The speaker walks the room through it (below), so it must be legible from the back row.")
        lines += ['', '## What the speaker says over it (context for the designer; never rendered)', '']
        lines += ['\n\n'.join(s['notes']) if s['notes'] else '*(nothing — a beat)*']
        lines += ['', '## Design notes', '']
        lines += [f"- {d}" for d in s['design']] or ['- none beyond `00-style.md`: one claim, the house palette, the type scale for this kind of slide.']
        open(os.path.join(out_dir, name), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
        words = len(' '.join(s['notes']).split())
        rows.append((i, name, k, movement, label or '(untitled)', figs[0].group(2) if figs else '', words))
    idx = [f"# Slides — {title}", '',
           f"One brief per slide, generated from `draft.md` by `md_to_marp.py --briefs` — **regenerate, never edit these by hand** "
           f"(a per-slide design note goes in the draft as `<!-- design: … -->`). `00-style.md` is the general visual style doc and is "
           f"the author's. Hand this folder to the designer (Claude Design) with `00-style.md` first, then the slides in order.", '',
           f"{n} slides · {man.get('size', '16:9')} · {man.get('duration_min', '?')} min · footer: {man.get('footer', '—')}", '',
           '| # | brief | kind | movement | title | figure | spoken words |', '|---|---|---|---|---|---|---|']
    for i, name, k, mv, t, fig, w in rows:
        idx.append(f"| {i:02d} | [{name}]({name}) | {k} | {mv} | {t} | {('`'+fig+'`') if fig else ''} | {w} |")
    open(os.path.join(out_dir, 'README.md'), 'w', encoding='utf-8').write('\n'.join(idx) + '\n')
    style = os.path.join(out_dir, '00-style.md')
    return out_dir, n, os.path.exists(style)


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
            flag = f"  outline {budget:g} min" + ('  OVER' if mins > budget * 1.1 else '  under' if mins < budget * 0.8 else '')
        print(f"  {title[:40]:40s} {w:5d} words  ~{w/wpm:4.1f} min{flag}")
    for f in faults:
        print('  fault:', f)
    if '--briefs' in sys.argv:
        out_dir, n, has_style = write_briefs(slides, man, piece)
        print(f"wrote {out_dir}/: {n} slide briefs + README.md" + ('' if has_style else "  (no 00-style.md yet — copy templates/talk/slides/00-style.md and fill it in)"))
    if faults and '--check' in sys.argv:
        sys.exit(2)


if __name__ == '__main__':
    main()
