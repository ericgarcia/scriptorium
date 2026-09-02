#!/usr/bin/env python3
"""dashboard.py — stop DASHBOARD.md being a shared singleton that the last writer wins.

THE PROBLEM (measured 2026-09-02).  `DASHBOARD.md` is one file holding ~27 independent blocks,
each owned by exactly one piece.  Six sessions were running against the desk at once; every one
of them read the whole file, edited its own block, and wrote the whole file back.  The last
write won and the others vanished without an error, a conflict, or a trace.  It happened three
times to one block in a single afternoon, and it was noticed only because somebody re-grepped.

THE FIX is not locking and not merging.  It is REMOVING THE SHARED FILE FROM THE WRITE PATH.
Each block becomes its own file under `DASHBOARD.d/`, owned by one piece.  `DASHBOARD.md` is
then GENERATED — it stays committed, because it is what a human reads and what the instructions
point at, but nothing edits it directly any more.  Two sessions writing two different pieces now
touch two different files and cannot collide at all.  This is the desk's own principle applied
one level down: the README is truth and the dashboard is a summary, so the summary should be
derived rather than authored.

THE PART THAT IS EASY TO GET WRONG, and the reason `ingest` exists.  During the changeover —
and any time a session that has not learned the new layout edits `DASHBOARD.md` by hand — a
blind `render` would overwrite that hand edit and reintroduce exactly the silent data loss this
tool exists to end.  So the default is not `render`, it is `sync`: INGEST FIRST (pull any
hand-edit in `DASHBOARD.md` back down into its fragment), THEN render.  A generator that can
destroy hand-written work is not an improvement on the problem it replaces.

AND THE INVERSE, WHICH INTEGRATION TESTING CAUGHT AFTER THE UNIT TESTS PASSED.  A first version
of `ingest` assumed `DASHBOARD.md` was always the newer side, so running the DOCUMENTED workflow
— edit your fragment, then `sync` — silently reverted the fragment from the older generated
file.  The tool destroyed exactly the work it had just told you to do.  So ingest is decided
PER BLOCK BY MTIME: `DASHBOARD.md` newer than the fragment means a hand edit worth pulling down;
a fragment newer than `DASHBOARD.md` means the normal workflow, and it is left alone.  Whichever
side was written last is the side that wins, which is the only rule that is right in both
directions.

    dashboard.py split    one-time: explode DASHBOARD.md into DASHBOARD.d/
    dashboard.py ingest   pull hand-edits in DASHBOARD.md back into fragments
    dashboard.py render   fragments -> DASHBOARD.md   (atomic)
    dashboard.py sync     ingest, then render   [default]
    dashboard.py check    exit 1 if DASHBOARD.md differs from the fragments

ORDERING carries no shared state on purpose.  It lives in the filename (`NNN-slug.md`, gaps of
ten), so adding a piece creates one new file and edits nothing.  An explicit order file would
just be the singleton again, one indirection away.
"""
import os, re, sys

FRAGDIR = 'DASHBOARD.d'
DASHBOARD = 'DASHBOARD.md'
BLOCK_RE = re.compile(r'^## ', re.M)


def instance_root(start=None):
    cur = os.path.abspath(start or os.environ.get('DESK_INSTANCE') or os.getcwd())
    while True:
        if os.path.isfile(os.path.join(cur, DASHBOARD)) or os.path.isdir(os.path.join(cur, FRAGDIR)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())
        cur = parent


def slug_of(heading):
    """`## hearing-firsthand *(title **Secondhand**)*` -> `hearing-firsthand`.

    The slug is the stable identity and the title is not — a piece was retitled twice in one
    afternoon while another session held stale references to it.  Fragments are named by slug
    for that reason, so a retitle rewrites a file's CONTENT and never its name.
    """
    text = heading[3:].strip()
    m = re.match(r'([a-z0-9][a-z0-9._-]*)', text)
    # A real slug is lowercase-and-hyphens; a prose heading ("Books") is not, and must be
    # slugified rather than passed through — otherwise the fragment for `## Books` is named
    # `Books` and sorts and compares differently from every other fragment on the shelf.
    if m and (len(text) == len(m.group(1)) or text[len(m.group(1))] in ' *('):
        return m.group(1)
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or 'section'


def parse(text):
    """-> (preamble, [(slug, block_text), ...]).  Block text keeps its heading and trailing \n."""
    starts = [m.start() for m in BLOCK_RE.finditer(text)]
    if not starts:
        return text, []
    preamble = text[:starts[0]]
    blocks = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(text)
        chunk = text[s:e]
        blocks.append((slug_of(chunk.split('\n', 1)[0]), chunk))
    return preamble, blocks


def frag_path(root, num, slug):
    return os.path.join(root, FRAGDIR, '%03d-%s.md' % (num, slug))


def fragments(root):
    """-> [(num, slug, path)] in render order."""
    d = os.path.join(root, FRAGDIR)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in os.listdir(d):
        m = re.match(r'^(\d{3})-(.+)\.md$', fn)
        if m:
            out.append((int(m.group(1)), m.group(2), os.path.join(d, fn)))
    return sorted(out, key=lambda t: (t[0], t[1]))


def _atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = '%s.tmp%d' % (path, os.getpid())
    with open(tmp, 'w') as fh:
        fh.write(text)
    os.replace(tmp, path)


def _norm(s):
    """Fragments are stored VERBATIM — this only guarantees a trailing newline.

    An earlier version normalized to exactly one trailing newline and re-joined blocks with a
    blank line.  On the fixture that round-tripped perfectly; on the real dashboard it did not,
    because the live file separates some blocks by a blank line and others by none, and the
    normalizer flattened all of them.  The result would have been a first render that reflowed
    the entire document — not data loss, but a diff nobody asked for, in the one file this
    change exists to stop churning.  So: keep the bytes, and only ensure a block cannot run
    into the next one's heading.
    """
    return s if s.endswith('\n') else s + '\n'


def do_split(root, force=False):
    path = os.path.join(root, DASHBOARD)
    with open(path) as fh:
        text = fh.read()
    preamble, blocks = parse(text)
    existing = fragments(root)
    if existing and not force:
        sys.stderr.write('dashboard: %s already has %d fragments; --force to re-split\n'
                         % (FRAGDIR, len(existing)))
        return 1
    _atomic_write(frag_path(root, 0, 'preamble'), _norm(preamble))
    n = 0
    for slug, chunk in blocks:
        n += 10
        _atomic_write(frag_path(root, n, slug), _norm(chunk))
    print('split %s -> %d fragments in %s/' % (DASHBOARD, len(blocks) + 1, FRAGDIR))
    return 0


def render_text(root):
    parts = []
    for _num, _slug, path in fragments(root):
        with open(path) as fh:
            parts.append(_norm(fh.read()))
    return ''.join(parts)      # exact concatenation: the separators live IN the fragments


def do_render(root, quiet=False):
    frags = fragments(root)
    if not frags:
        sys.stderr.write('dashboard: no fragments in %s/ — run `dashboard.py split` first\n' % FRAGDIR)
        return 2
    out = render_text(root)
    path = os.path.join(root, DASHBOARD)
    old = open(path).read() if os.path.isfile(path) else None
    if old == out:
        if not quiet:
            print('render: %s already current (%d fragments)' % (DASHBOARD, len(frags)))
        return 0
    _atomic_write(path, out)
    if not quiet:
        print('render: wrote %s from %d fragments' % (DASHBOARD, len(frags)))
    return 0


def do_ingest(root, quiet=False):
    """Pull hand-edits made directly in DASHBOARD.md back down into the fragments.

    This is what makes the changeover safe, and it stays useful afterwards: any session or
    editor that has not learned the new layout will keep editing the generated file, and their
    work has to survive that.  A block with no fragment is a NEW piece and gets one.  A fragment
    with no block is reported and NEVER deleted — the absence may just mean the other side is
    stale, and deleting somebody's block on that guess is the original bug wearing a new hat.
    """
    path = os.path.join(root, DASHBOARD)
    if not os.path.isfile(path):
        return 0
    dash_mtime = os.path.getmtime(path)

    def newer_on_disk(frag):
        """Is DASHBOARD.md the newer side for this block?  If not, leave the fragment alone."""
        try:
            return dash_mtime > os.path.getmtime(frag) + 1e-6
        except OSError:
            return True          # no fragment yet: the dashboard is all there is

    with open(path) as fh:
        preamble, blocks = parse(fh.read())
    frags = fragments(root)
    by_slug = {slug: (num, p) for num, slug, p in frags}
    changed, added, kept = [], [], []

    pre_num, pre_path = by_slug.get('preamble', (0, frag_path(root, 0, 'preamble')))
    if newer_on_disk(pre_path) and (not os.path.isfile(pre_path)
                                    or _norm(open(pre_path).read()) != _norm(preamble)):
        _atomic_write(pre_path, _norm(preamble))
        changed.append('preamble')

    nxt = (max([n for n, _, _ in frags], default=0) // 10 + 1) * 10
    for slug, chunk in blocks:
        if slug in by_slug:
            _num, p = by_slug[slug]
            if _norm(open(p).read()) != _norm(chunk):
                if newer_on_disk(p):
                    _atomic_write(p, _norm(chunk))
                    changed.append(slug)
                else:
                    kept.append(slug)      # the fragment is the newer side: the normal workflow
        else:
            _atomic_write(frag_path(root, nxt, slug), _norm(chunk))
            added.append(slug)
            nxt += 10

    seen = {s for s, _ in blocks} | {'preamble'}
    orphans = [s for _n, s, _p in frags if s not in seen]
    if not quiet:
        if changed or added:
            print('ingest: updated %d, added %d  (%s)' %
                  (len(changed), len(added), ', '.join(changed + ['+' + a for a in added])))
        else:
            print('ingest: nothing to pull down from %s' % DASHBOARD)
        if kept:
            print('ingest: %d fragment(s) newer than %s, kept: %s'
                  % (len(kept), DASHBOARD, ', '.join(kept)))
        if orphans:
            print('ingest: %d fragment(s) absent from %s and KEPT: %s'
                  % (len(orphans), DASHBOARD, ', '.join(orphans)))
    return 0


def do_check(root):
    frags = fragments(root)
    if not frags:
        sys.stderr.write('dashboard: no fragments to check\n')
        return 2
    path = os.path.join(root, DASHBOARD)
    live = open(path).read() if os.path.isfile(path) else ''
    if live == render_text(root):
        print('check: %s matches its %d fragments' % (DASHBOARD, len(frags)))
        return 0
    _, live_blocks = parse(live)
    live_by = dict(live_blocks)
    drift = []
    for _n, slug, p in frags:
        if slug == 'preamble':
            continue
        want = _norm(open(p).read())
        got = _norm(live_by.get(slug, ''))
        if slug not in live_by:
            drift.append('%s: MISSING from %s' % (slug, DASHBOARD))
        elif want != got:
            drift.append('%s: differs' % slug)
    for slug in live_by:
        if slug not in {s for _n, s, _p in frags}:
            drift.append('%s: in %s with no fragment' % (slug, DASHBOARD))
    print('check: %s DIFFERS from its fragments' % DASHBOARD)
    for d in drift or ['(whitespace/ordering only)']:
        print('  ' + d)
    print('run `dashboard.py sync` — it ingests hand-edits before rendering, so nothing is lost')
    return 1


def main(argv):
    if len(argv) > 1 and argv[1] in ('-h', '--help'):
        print(__doc__)
        return 0
    cmd = argv[1] if len(argv) > 1 else 'sync'
    root = instance_root()
    if cmd == 'split':
        return do_split(root, force='--force' in argv)
    if cmd == 'render':
        return do_render(root)
    if cmd == 'ingest':
        return do_ingest(root)
    if cmd == 'check':
        return do_check(root)
    if cmd == 'sync':
        rc = do_ingest(root)
        return rc or do_render(root)
    sys.stderr.write('dashboard: unknown command %r (split|ingest|render|sync|check)\n' % cmd)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
