#!/usr/bin/env python3
"""Render a piece as the house REVIEW ARTIFACT — the surface an author reads.

WHY THIS EXISTS
  A rewrite or a critique asks the author to judge *prose*. A draft.md full of
  [^slug] markers, a scaffold header and raw markdown is not the thing they are
  being asked to judge, and chat is not where review facts belong — they scroll
  away.

  Two sessions built this page by hand on 2026-09-09 and 2026-09-10 and produced
  two different formats: different type pairs, different palettes, one with a
  contents list and per-movement word counts and a provenance stamp, the other
  with gate chips and a tighter measure. Both were defensible. That is the
  problem — a format argued fresh each time is a format that drifts, and the
  author has to re-learn the page every time they open one.

  So the format is a TOOL, not a paragraph of instruction. One generator, one
  house page. The prose is parsed out of draft.md and never retyped, for the same
  reason the composer never retypes into Substack: a transcription slip becomes an
  edit nobody can see.

USAGE
  python3 review_artifact.py <piece_dir> [--facts facts.json] [--out page.html]

  Everything the page shows about the PIECE is read from the piece: title and
  subtitle from publish.yaml, prose and notes from draft.md, the hero from
  assets/. Everything it shows about the REVIEW comes from --facts (see FACTS
  below); with no facts file the page still renders, and the review strip simply
  reports what can be counted.

FACTS (all keys optional)
  version   "v3"                       label in the masthead stamp
  state     ["composed, not published"] flags in the stamp — say the live truth
  date      "10 September 2026"
  voice     "Being Good · argued voice"
  prior     {"words":3072,"movements":8,"notes":11}   deltas are computed
  gates     [["check_links","8 live, 0 dead"], ...]
  calls     [["Short title","One or two sentences of body (HTML ok)."], ...]
  cover     {"caption":"...","provenance":"Generated, not a photograph."}

EXIT
  0 rendered            1 usage / no draft            2 draft failed to parse
"""
import sys, os, re, json, html, io, base64

SANS = "IBM Plex Sans"; SERIF = "Spectral"; MONO = "IBM Plex Mono"


def manifest(piece_dir):
    out, path = {}, os.path.join(piece_dir, 'publish.yaml')
    if os.path.exists(path):
        for line in open(path):
            m = re.match(r'\s*(title|subtitle|public_url|post_url)\s*:\s*(.+)', line)
            if m and m.group(1) not in out:
                # strip a trailing inline comment, however much space precedes it —
                # `title: X   # settled` and `title: X # settled` both leak otherwise,
                # and the title band is the first thing an author reads.
                out[m.group(1)] = re.sub(r'\s+#.*$', '', m.group(2)).strip()
    return out


def split_draft(text):
    """Publishable body only — the scaffold above the first `---` never reaches a reader."""
    parts = text.split('\n---\n', 1)
    body = (parts[1] if len(parts) > 1 else text).strip()
    m = re.search(r'^\[\^[\w-]+\]:', body, re.M)
    if not m:
        return body, {}
    prose, tail = body[:m.start()].strip(), body[m.start():]
    starts = [(mm.group(1), mm.start()) for mm in re.finditer(r'^\[\^([\w-]+)\]:', tail, re.M)]
    defs = {}
    for i, (k, st) in enumerate(starts):
        en = starts[i + 1][1] if i + 1 < len(starts) else len(tail)
        defs[k] = re.sub(r'^\[\^[\w-]+\]:\s*', '', tail[st:en].strip())
    return prose, defs


def inline(t, num, notes=True):
    t = html.escape(t, quote=False)
    t = re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+)\)',
               r'<a class="sib" href="\2" target="_blank" rel="noopener">\1</a>', t)
    t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t, flags=re.S)
    t = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<em>\1</em>', t, flags=re.S)
    if notes:
        t = re.sub(r'\[\^([\w-]+)\]', lambda m: (
            f'<sup class="fn" id="r{num[m.group(1)]}">'
            f'<a href="#n{num[m.group(1)]}">{num[m.group(1)]}</a></sup>') if m.group(1) in num else '', t)
    return t


def hero(piece_dir, width=1400):
    for name in ('hero.png', 'hero.jpg', 'hero.jpeg'):
        p = os.path.join(piece_dir, 'assets', name)
        if os.path.exists(p):
            try:
                from PIL import Image
            except ImportError:
                return None, 'PIL missing — hero not embedded'
            im = Image.open(p).convert('RGB')
            if im.width > width:
                im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
            buf = io.BytesIO(); im.save(buf, 'JPEG', quality=82, optimize=True, progressive=True)
            return base64.b64encode(buf.getvalue()).decode(), None
    return None, None


CSS = """
:root{
  --paper:#F7F8FA; --card:#FFFFFF; --ink:#171A21; --muted:#5D6472; --rule:#D6DAE2;
  --accent:#23458C; --accent-soft:#E6ECF8; --flag:#8A4F14; --flag-soft:#FBF0E2;
  --serif:"__SERIF__",Georgia,"Times New Roman",serif;
  --sans:"__SANS__",system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:"__MONO__",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#101319; --card:#161A22; --ink:#E4E7ED; --muted:#939BAA; --rule:#2B313D;
  --accent:#93B4F0; --accent-soft:#1B2537; --flag:#DFA260; --flag-soft:#2A2114;}}
:root[data-theme="dark"]{
  --paper:#101319; --card:#161A22; --ink:#E4E7ED; --muted:#939BAA; --rule:#2B313D;
  --accent:#93B4F0; --accent-soft:#1B2537; --flag:#DFA260; --flag-soft:#2A2114;}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font-family:var(--serif);margin:0;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:0 24px 96px}
.mast{padding:56px 0 28px;border-bottom:1px solid var(--rule)}
.stamp{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--accent);display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.stamp b{font-weight:500;color:var(--muted)}
h1{font-weight:600;font-size:clamp(32px,5.2vw,54px);line-height:1.08;margin:18px 0 10px;
  text-wrap:balance;letter-spacing:-.015em}
.sub{font-style:italic;font-size:clamp(17px,2.2vw,21px);color:var(--muted);margin:0;
  max-width:44ch;line-height:1.45}
.hero{margin:30px 0 0;display:flex;flex-direction:column;gap:10px}
.hero img{width:100%;height:auto;display:block;border:1px solid var(--rule)}
.hero figcaption{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;
  font-family:var(--sans);font-size:13px;color:var(--muted);line-height:1.5}
.hero figcaption span{font-family:var(--serif);font-style:italic;font-size:15px;color:var(--ink)}
.hero figcaption em{font-style:normal;font-family:var(--mono);font-size:10.5px;
  letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.slot{border:1px dashed var(--flag);background:var(--flag-soft);color:var(--flag);
  font-family:var(--mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase;
  padding:34px 18px;text-align:center;margin:30px 0 0}
.review{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:1px;
  background:var(--rule);border:1px solid var(--rule);margin:34px 0 0}
.review div{background:var(--card);padding:16px 18px}
.review dt{font-family:var(--mono);font-size:10px;letter-spacing:.13em;text-transform:uppercase;
  color:var(--muted);margin:0 0 6px}
.review dd{margin:0;font-family:var(--sans);font-size:15px;line-height:1.5}
.review dd b{font-family:var(--mono);font-weight:500}
.delta{color:var(--accent)}
.gates{margin:18px 0 0;display:flex;flex-wrap:wrap;gap:6px}
.gates span{font-family:var(--sans);font-size:12.5px;color:var(--muted);
  border:1px solid var(--rule);padding:3px 9px;white-space:nowrap}
.gates b{font-family:var(--mono);font-size:11px;font-weight:500;color:var(--ink)}
.calls{margin:34px 0 0;border-left:2px solid var(--flag);padding:2px 0 2px 20px;
  display:flex;flex-direction:column;gap:14px}
.calls h3{font-family:var(--sans);font-size:12px;letter-spacing:.13em;text-transform:uppercase;
  color:var(--flag);margin:0}
.calls p{margin:0;font-family:var(--sans);font-size:15px;line-height:1.6;max-width:70ch}
.calls p b{font-weight:600}
.toc{margin:40px 0 0;border-top:1px solid var(--rule)}
.toc a{display:grid;grid-template-columns:34px 1fr auto;gap:14px;align-items:baseline;
  padding:11px 2px;border-bottom:1px solid var(--rule);text-decoration:none;color:var(--ink);
  font-family:var(--sans);font-size:15px}
.toc a span{font-family:var(--mono);font-size:12px;color:var(--accent)}
.toc a em{font-family:var(--mono);font-size:12px;color:var(--muted);font-style:normal;
  font-variant-numeric:tabular-nums}
.toc a:hover{background:var(--accent-soft)}
.mv{display:grid;grid-template-columns:80px minmax(0,1fr);gap:32px;padding:52px 0 0;align-items:start}
.rail{position:sticky;top:24px;display:flex;flex-direction:column;gap:4px;text-align:right;padding-top:10px}
.rn{font-family:var(--mono);font-size:20px;color:var(--accent);line-height:1}
.wc{font-family:var(--mono);font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.col{max-width:66ch}
h2{font-weight:600;font-size:clamp(23px,3vw,30px);line-height:1.2;margin:0 0 22px;
  text-wrap:balance;letter-spacing:-.01em}
.col p{font-size:18.5px;line-height:1.68;margin:0 0 20px}
blockquote{margin:26px 0;padding:0 0 0 20px;border-left:2px solid var(--accent);
  font-size:19px;line-height:1.6;font-style:italic}
blockquote p{margin:0;font-size:19px}
sup.fn a{font-family:var(--mono);font-size:11px;text-decoration:none;color:var(--accent);
  padding:0 1px;vertical-align:super}
a.sib{color:var(--accent);text-decoration:none;border-bottom:1px solid var(--accent-soft)}
a.sib:hover{border-bottom-color:var(--accent)}
.notes{margin:72px 0 0;border-top:1px solid var(--rule);padding-top:26px}
.notes h2{font-family:var(--sans);font-size:12px;letter-spacing:.13em;text-transform:uppercase;
  color:var(--muted);margin:0 0 20px}
.notes ol{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:15px;max-width:80ch}
.notes li{display:grid;grid-template-columns:26px 1fr;gap:12px;font-family:var(--sans);
  font-size:14px;line-height:1.62;color:var(--muted)}
.fnn{font-family:var(--mono);font-size:12px;color:var(--accent);
  font-variant-numeric:tabular-nums;padding-top:2px}
.notes em{font-style:italic;color:var(--ink)}
.back{color:var(--accent);text-decoration:none;font-size:13px}
:target{background:var(--accent-soft)}
a:focus-visible,.toc a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media (max-width:720px){
  .mv{grid-template-columns:1fr;gap:10px;padding-top:40px}
  .rail{position:static;flex-direction:row;gap:10px;text-align:left;align-items:baseline}
  .col p{font-size:17.5px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
""".replace("__SERIF__", SERIF).replace("__SANS__", SANS).replace("__MONO__", MONO)


def build(piece_dir, facts):
    raw = open(os.path.join(piece_dir, 'draft.md')).read()
    prose, defs = split_draft(raw)
    man = manifest(piece_dir)

    order = list(dict.fromkeys(re.findall(r'\[\^([\w-]+)\]', prose)))
    missing = [k for k in order if k not in defs]
    if missing:
        print(f"footnote marker with no definition: {missing}", file=sys.stderr); sys.exit(2)
    unused = [k for k in defs if k not in order]
    if unused:
        print(f"footnote defined but never referenced: {unused}", file=sys.stderr); sys.exit(2)
    num = {k: i + 1 for i, k in enumerate(order)}

    # --- movements ----------------------------------------------------------
    chunks = re.split(r'^## +', prose, flags=re.M)
    lead, movements = chunks[0], []
    for ch in chunks[1:]:
        head, _, rest = ch.partition('\n')
        movements.append((head.strip(), rest.strip()))
    if not movements:                      # a piece with no headings is still reviewable
        movements = [('', prose)]

    def blocks(md):
        out = []
        for blk in re.split(r'\n\s*\n', md):
            blk = blk.strip()
            if not blk or blk.startswith('!['):
                continue
            if blk.startswith('>'):
                q = ' '.join(l.lstrip('> ').strip() for l in blk.split('\n'))
                out.append(f'<blockquote><p>{inline(q, num)}</p></blockquote>')
            else:
                out.append(f'<p>{inline(" ".join(blk.split()), num)}</p>')
        return '\n'.join(out)

    def words(md):
        # Count WORDS, not whitespace-separated tokens.  A bare em-dash, a blockquote
        # marker and a footnote reference are all separated by spaces and none of them is
        # a word: `.split()` made this piece read 4,179 against the 4,164 recorded in its
        # README, log, dashboard and three commit messages, and the artifact is the one
        # surface an author checks the number on.  This regex is the one the rest of the
        # desk counts with, so the artifact and the scaffold now agree by construction.
        md = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', md)   # images
        md = re.sub(r'\[\^[^\]]+\]', '', md)             # footnote references
        md = re.sub(r'^\s*>\s?', '', md, flags=re.M)      # blockquote markers
        return len(re.findall(r"[A-Za-z0-9’'\-]+", md))

    body_words = words(lead) + sum(words(b) for _, b in movements)

    toc, essay = [], []
    for i, (head, md) in enumerate(movements, 1):
        n = re.match(r'([IVXLC]+|\d+)\.', head)
        label = n.group(1) if n else str(i)
        title = re.sub(r'^([IVXLC]+|\d+)\.\s*', '', head)
        w = words(md)
        toc.append(f'<a href="#m{i}"><span>{label}</span>{html.escape(title)}<em>{w:,} w</em></a>')
        essay.append(
            f'<section class="mv" id="m{i}"><div class="rail"><div class="rn">{label}</div>'
            f'<div class="wc">{w:,} w</div></div><div class="col">'
            f'<h2>{html.escape(title)}</h2>{blocks(md)}</div></section>')

    # --- review strip -------------------------------------------------------
    prior = facts.get('prior') or {}
    def cell(label, now, was, unit=''):
        d = ''
        if isinstance(was, int):
            diff = now - was
            d = (f' <span class="delta">{"+" if diff>0 else ""}{diff:,} on {was:,}</span>'
                 if diff else ' <span class="delta">unchanged</span>')
        return f'<div><dt>{label}</dt><dd><b>{now:,}</b>{unit}{d}</dd></div>'
    strip = (cell('Body words', body_words, prior.get('words'))
             + cell('Movements', len(movements), prior.get('movements'))
             + cell('Footnotes', len(order), prior.get('notes')))

    gates = ''.join(f'<span><b>{html.escape(k)}</b> {html.escape(v)}</span>'
                    for k, v in facts.get('gates', []))
    gates = f'<div class="gates">{gates}</div>' if gates else ''

    calls = facts.get('calls', [])
    callsblk = ''
    if calls:
        items = ''.join(f'<p><b>{t}</b> {b}</p>' for t, b in calls)
        callsblk = (f'<section class="calls"><h3>Open &mdash; {len(calls)} '
                    f'call{"s" if len(calls)!=1 else ""} for you</h3>{items}</section>')

    b64, warn = hero(piece_dir, )
    cover = facts.get('cover') or {}
    if b64:
        alt = re.search(r'!\[([^\]]*)\]', prose)
        figure = (f'<figure class="hero"><img src="data:image/jpeg;base64,{b64}" '
                  f'alt="{html.escape(alt.group(1)) if alt else ""}"><figcaption>'
                  f'<span>{cover.get("caption","")}</span>'
                  f'<em>{cover.get("provenance","provenance not recorded")}</em>'
                  f'</figcaption></figure>')
    else:
        figure = f'<div class="slot">Hero image slot &mdash; {warn or "none supplied yet"}</div>'

    notes = ''.join(
        f'<li id="n{num[k]}"><div class="fnn">{num[k]}</div><div>{inline(" ".join(defs[k].split()), num, notes=False)} '
        f'<a class="back" href="#r{num[k]}" aria-label="back to text">&#8617;</a></div></li>'
        for k in order)

    stamp = ' '.join([f'<span>{html.escape(facts.get("version","draft"))}</span>']
                     + [f'<b>{html.escape(s)}</b>' for s in facts.get('state', [])]
                     + ([f'<b>{html.escape(facts["date"])}</b>'] if facts.get('date') else []))

    return f"""<title>{html.escape(man.get('title','Review'))}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family={SERIF}:ital,wght@0,400;0,600;1,400&family={SANS.replace(' ','+')}:wght@400;500;600&family={MONO.replace(' ','+')}:wght@400;500&display=swap">
<style>{CSS}</style>
<div class="wrap">
<header class="mast">
  <div class="stamp">{stamp}</div>
  <h1>{html.escape(man.get('title','(untitled)'))}</h1>
  <p class="sub">{html.escape(man.get('subtitle',''))}</p>
  {figure}
  <dl class="review">{strip}</dl>
  {gates}
  {callsblk}
  <nav class="toc">{''.join(toc)}</nav>
</header>
{''.join(essay)}
<section class="notes"><h2>Notes</h2><ol>{notes}</ol></section>
</div>
"""


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print(__doc__.strip()); sys.exit(1)
    piece_dir = args[0].rstrip('/')
    if not os.path.exists(os.path.join(piece_dir, 'draft.md')):
        print(f"no draft.md in {piece_dir}"); sys.exit(1)

    def opt(name, default=None):
        if name in sys.argv:
            return sys.argv[sys.argv.index(name) + 1]
        return default

    facts = {}
    fp = opt('--facts') or os.path.join(piece_dir, 'review.json')
    if os.path.exists(fp):
        facts = json.load(open(fp))
    out = opt('--out', os.path.join(piece_dir, 'review.html'))
    page = build(piece_dir, facts)
    open(out, 'w').write(page)
    print(f"wrote {out} ({len(page)//1024} KB) — publish it with the Artifact tool")


if __name__ == '__main__':
    main()
