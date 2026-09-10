#!/usr/bin/env python3
"""rename_piece.py — move a piece to the slug its title now implies, atomically.

WHY (Eric, 2026-09-10, reversing the older keep-the-slug practice).  A piece's directory is
its address, and an address that describes the piece it used to be is how a corpus starts
lying about itself.  The desk had drifted to 25 of 40 pieces answering to the wrong name.

The `rewrite` skill describes the move as six steps.  Six steps done twenty-five times by
hand is where a silent miss lives, so this does them and then PROVES it.

    python3 framework/tools/rename_piece.py <old-slug> [new-slug]        # dry run
    python3 framework/tools/rename_piece.py <old-slug> [new-slug] --apply

`new-slug` defaults to the slug derived from `publish.yaml`'s title.

WHAT IT WILL NOT DO
  - rewrite anything inside an http(s) URL.  A published address is not a repo path: some
    pieces have a Substack or site slug that contains the directory name, and blind
    substitution would silently break a live link.
  - touch `log/` or `corrections.md`.  They are append-only records of what was true when
    written; an old slug there is history, not rot (the exemption `check_refs.py` makes too).
  - drop the old address.  It is appended to `former_slugs:` in publish.yaml, which is what
    keeps the site's redirect alive after the directory stops differing from the title-slug.
    See `md_to_site.renames_for`: without it, a rename DELETES the redirect for a URL that is
    already published and in a submitted sitemap, and no audit can see it.
"""
import argparse, os, re, subprocess, sys, glob

HERE = os.path.dirname(os.path.abspath(__file__))


def _desk_root():
    """The INSTANCE repo, not the framework submodule this file lives in.

    `git rev-parse --show-toplevel` run from HERE returns the submodule, and every path
    below would then miss — the same trap `substack_sync.cmd_seed` documents. Walk up from
    the working directory looking for the thing that actually identifies a desk: `pieces/`.
    """
    d = os.path.abspath(os.getcwd())
    while True:
        if os.path.isdir(os.path.join(d, 'pieces')):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            sys.stderr.write('rename_piece: no pieces/ directory above the working '
                             'directory — run this from inside the desk.\n')
            sys.exit(2)
        d = parent


ROOT = _desk_root()
URL = re.compile(r'https?://[^\s)\]"\'>]+')
EXEMPT_BASENAMES = {'corrections.md'}


def die(msg, code=2):
    sys.stderr.write('rename_piece: ' + msg + '\n')
    sys.exit(code)


def derive(title):
    s = str(title).lower().replace('’', "'").replace("'", '')
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def title_of(piece_dir):
    for line in open(os.path.join(piece_dir, 'publish.yaml'), encoding='utf-8'):
        m = re.match(r'^title:\s*(.+?)\s*(?:#.*)?$', line)
        if m:
            return m.group(1).strip().strip('"\'')
    return None


def exempt(path):
    rel = os.path.relpath(path, ROOT)
    parts = rel.split(os.sep)
    return 'log' in parts or os.path.basename(rel) in EXEMPT_BASENAMES


def sub_outside_urls(text, old, new):
    """Replace whole-token `old` with `new`, but never inside a URL."""
    pat = re.compile(r'(?<![A-Za-z0-9_-])' + re.escape(old) + r'(?![A-Za-z0-9_-])')
    out, last, n = [], 0, 0
    for m in URL.finditer(text):
        seg, cnt = pat.subn(new, text[last:m.start()])
        out.append(seg); n += cnt
        out.append(m.group(0))            # URL passes through untouched
        last = m.end()
    seg, cnt = pat.subn(new, text[last:])
    out.append(seg); n += cnt
    return ''.join(out), n


def git(*args, check=True):
    r = subprocess.run(['git'] + list(args), capture_output=True, text=True, cwd=ROOT)
    if check and r.returncode:
        die(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('old'); ap.add_argument('new', nargs='?')
    ap.add_argument('--apply', action='store_true')
    o = ap.parse_args()

    old_dir = os.path.join(ROOT, 'pieces', o.old)
    if not os.path.isdir(old_dir):
        die(f"no such piece: pieces/{o.old}")
    title = title_of(old_dir)
    new = o.new or (derive(title) if title else None)
    if not new:
        die(f"pieces/{o.old} has no title in publish.yaml; pass the new slug explicitly")
    if new == o.old:
        print(f"{o.old}: already matches its title — nothing to do"); return 0
    if os.path.exists(os.path.join(ROOT, 'pieces', new)):
        die(f"pieces/{new} already exists")

    plan = {'dir': (f'pieces/{o.old}', f'pieces/{new}'), 'dashboard': None, 'edits': [], 'skipped_urls': 0}

    frags = glob.glob(os.path.join(ROOT, 'DASHBOARD.d', f'*-{o.old}.md'))
    if len(frags) > 1:
        die(f"{len(frags)} dashboard fragments match {o.old}; resolve the duplicate first")
    if frags:
        b = os.path.basename(frags[0])
        plan['dashboard'] = (f'DASHBOARD.d/{b}', 'DASHBOARD.d/' + b[:-(len(o.old) + 3)] + new + '.md')

    for path in glob.glob(os.path.join(ROOT, '**', '*.md'), recursive=True) + \
                glob.glob(os.path.join(ROOT, '**', '*.yaml'), recursive=True):
        if '/framework/' in path or '/.git/' in path or exempt(path):
            continue
        try: text = open(path, encoding='utf-8').read()
        except Exception: continue
        if o.old not in text:
            continue
        newtext, n = sub_outside_urls(text, o.old, new)
        in_urls = len(re.findall(re.escape(o.old), text)) - n
        plan['skipped_urls'] += max(0, in_urls)
        if n:
            plan['edits'].append((os.path.relpath(path, ROOT), n, newtext))

    print(f"\n{o.old}  ->  {new}     (title: {title!r})")
    print(f"  mv  {plan['dir'][0]}  ->  {plan['dir'][1]}")
    if plan['dashboard']:
        print(f"  mv  {plan['dashboard'][0]}  ->  {plan['dashboard'][1]}")
    print(f"  {len(plan['edits'])} file(s) with cross-references, "
          f"{sum(n for _p, n, _t in plan['edits'])} occurrence(s)")
    for rel, n, _t in plan['edits']:
        print(f"      {n:>3}  {rel}")
    if plan['skipped_urls']:
        print(f"  {plan['skipped_urls']} occurrence(s) left alone inside URLs (published addresses)")
    if not o.apply:
        print("\n  dry run — pass --apply to perform it"); return 0

    git('mv', plan['dir'][0], plan['dir'][1])
    if plan['dashboard']:
        git('mv', plan['dashboard'][0], plan['dashboard'][1])
    # THE PLAN WAS COMPUTED BEFORE THE MOVES, so every path in it may be stale. Remap ALL of
    # them, not just the ones under pieces/. Writing to a stale path does not fail — `open(...,
    # 'w')` RECREATES the file that was just moved away, leaving two fragments for one piece
    # (the new name holding the pre-sweep original, the old name holding the swept text).
    # Measured on the 2026-09-10 sweep: 24 stale dashboard fragments, one per rename.
    moved = [plan['dir']] + ([plan['dashboard']] if plan['dashboard'] else [])
    for rel, _n, text in plan['edits']:
        for src, dst in moved:
            if rel == src:
                rel = dst
            elif rel.startswith(src + '/'):
                rel = dst + rel[len(src):]
        target = os.path.join(ROOT, rel)
        if not os.path.exists(target):
            die(f"refusing to create {rel} — it is not where the plan said it would be, "
                f"which means a path was not remapped after the move")
        with open(target, 'w', encoding='utf-8') as fh:
            fh.write(text)

    # former_slugs: the trace that outlives the rename and keeps the redirect alive
    man = os.path.join(ROOT, 'pieces', new, 'publish.yaml')
    src = open(man, encoding='utf-8').read()
    if re.search(r'^former_slugs:', src, re.M):
        src = re.sub(r'^former_slugs:\n', f'former_slugs:\n  - {o.old}\n', src, count=1, flags=re.M)
    else:
        src = src.rstrip('\n') + (
            "\n\n# Every address this piece has answered to. NEVER remove one: it is the only\n"
            "# record that a URL was handed to a reader, and md_to_site keeps its redirect alive.\n"
            f"former_slugs:\n  - {o.old}\n")
    open(man, 'w', encoding='utf-8').write(src)

    print(f"\n  renamed. former_slugs += {o.old}")
    stale = [l for l in git('grep', '-rn', '--', o.old, check=False).splitlines()
             if not re.search(r'/log/|corrections\.md', l) and 'former_slugs' not in l
             and not URL.search(l.split(':', 2)[-1])]
    print(f"  remaining non-URL, non-log mentions of {o.old!r}: {len(stale)}")
    for l in stale[:12]:
        print('      ' + l[:150])
    return 0


if __name__ == '__main__':
    sys.exit(main())
