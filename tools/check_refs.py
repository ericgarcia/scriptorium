#!/usr/bin/env python3
"""check_refs.py — do the desk's cross-references still name the right piece?

`check_links.py` proves a URL resolves.  This proves something different and, with several
sessions running, more fragile: that when one file CALLS a piece by name, the name is still the
piece's name.

WHY (2026-09-02).  A sibling was retitled twice in one afternoon by another session —
*Fear Not, Little Flock* to *The Kingdom That Isn't*, then a second piece from *Two Wills* to
*Already Inside the Fence* — while other files went on referring to the old titles.  Nothing was
broken in a way any tool could see: every link still resolved, every file still parsed.  The
references were simply about a piece that no longer had that name, and the only reason it was
caught was that somebody happened to re-read the file.

METHOD, and the choice here is the useful part.  There is no need for history.  A stale title
shows up as a DISAGREEMENT: the same slug labelled with two different titles in two places.  So
this compares the corpus against ITSELF, and uses each piece's README H1 only to say which side
of a disagreement is right.  That needs no record of past titles, which is good, because the
desk does not keep one and should not have to.

WHAT IS DELIBERATELY NOT CHECKED, because a checker that cries about correct files gets
switched off:

  * `log/` and `corrections.md`.  They are APPEND-ONLY records of what was true when written.
    A log entry naming the old title is not stale, it is accurate history, and "fixing" it would
    be editing the evidence.
  * Any line that marks its own supersession — *Retired:*, *superseded*, *(was …)*, *formerly*,
    *replaced*.  Naming an old title in order to retire it is the correct use of an old title.

Exit: 0 consistent | 1 disagreements found | 2 nothing could be checked.
"""
import os, re, sys

SCAN_NAMES = ('README.md', 'notes.md', 'outline.md', 'draft.md', 'DASHBOARD.md')
SKIP_DIR_PARTS = ('/log/', '/.git/', '/node_modules/', '/__pycache__/')
SKIP_FILES = ('corrections.md',)
SUPERSESSION = re.compile(
    r'retired|supersed|formerly|\bwas\b\s*[:"“]|\(was\b|replaced|previous title|old title|'
    r'working title\s*\*?\*?[:,]', re.I)

# `## slug *(title **X**)*` / `*(working title **X**)*` — the dashboard's own labelling
HEAD_LABEL = re.compile(r'^##\s+([A-Za-z0-9][A-Za-z0-9._-]*)\s*\*\((?:working\s+)?title\s+'
                        r'(?:\*\*(?P<b>[^*]+)\*\*|"(?P<q>[^"]+)")\s*\)\*', re.M)
# a markdown link whose target is a piece directory
PIECE_LINK = re.compile(r'\[([^\]]{2,120})\]\(([^)]*?pieces/|\.\./)([A-Za-z0-9][A-Za-z0-9._-]*)/'
                        r'(?:README\.md)?\)')


def unemphasize(text):
    """Strip markdown emphasis from a link's text.

    `[*The Highest Peak*](../the-optimal-timeline/README.md)` is a reference to a piece named
    *The Highest Peak*; the asterisks are formatting, not part of the name.  The first run of
    this checker reported nine disagreements that were nothing but emphasis markers — a checker
    whose output is mostly noise gets muted, which costs more than the bug it was built for.
    """
    t = text.strip()
    for _ in range(3):
        m = re.fullmatch(r'(\*\*\*|\*\*|\*|__|_)(.+?)\1', t, re.S)
        if not m:
            break
        t = m.group(2).strip()
    return t


def instance_root(start=None):
    cur = os.path.abspath(start or os.environ.get('DESK_INSTANCE') or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(cur, 'pieces')):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())
        cur = parent


def h1_title(path):
    """The piece's own name: its H1, minus a trailing italic parenthetical.

    `# Secondhand *(slug \\`hearing-firsthand\\`)*`            -> Secondhand
    `# In the Name (The Ambassador) *(was "The Name")*`        -> In the Name (The Ambassador)
    """
    try:
        with open(path) as fh:
            for line in fh:
                if line.startswith('# '):
                    t = line[2:].strip()
                    t = re.sub(r'\s*\*\(.*$', '', t).strip()
                    return t or None
                if line.strip() and not line.startswith(('*', '<', '>')):
                    continue
    except OSError:
        pass
    return None


def truth(root):
    """slug -> title, from each piece's README H1."""
    out = {}
    pdir = os.path.join(root, 'pieces')
    if not os.path.isdir(pdir):
        return out
    for slug in sorted(os.listdir(pdir)):
        rd = os.path.join(pdir, slug, 'README.md')
        if os.path.isfile(rd):
            out[slug] = h1_title(rd)
    return out


def scan_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ('.git', '__pycache__', 'node_modules')]
        p = dirpath.replace(os.sep, '/') + '/'
        if any(s in p for s in SKIP_DIR_PARTS):
            continue
        for fn in filenames:
            if fn in SKIP_FILES:
                continue
            if fn in SCAN_NAMES or (fn.endswith('.md') and '/DASHBOARD.d/' in p):
                yield os.path.join(dirpath, fn)


def collect(root):
    """-> claims[slug] = set of (title, relpath, lineno), and unknown-slug references."""
    claims, unknown = {}, []
    known = set(os.listdir(os.path.join(root, 'pieces'))) if os.path.isdir(os.path.join(root, 'pieces')) else set()
    for path in scan_files(root):
        rel = os.path.relpath(path, root)
        try:
            with open(path) as fh:
                lines = fh.read().split('\n')
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if SUPERSESSION.search(line):
                continue
            for m in HEAD_LABEL.finditer(line):
                slug, title = m.group(1), (m.group('b') or m.group('q')).strip()
                claims.setdefault(slug, set()).add((title, rel, i))
            for m in PIECE_LINK.finditer(line):
                text, slug = m.group(1).strip(), m.group(3)
                if slug not in known:
                    # `../<name>/` is only a PIECE reference from inside pieces/. From
                    # books/all-my-stories it means the sibling book, and calling that a
                    # missing piece is the checker inventing a problem.
                    if (rel.startswith('pieces' + os.sep)
                            and slug not in ('..', '.') and not slug.endswith('.md')):
                        unknown.append((slug, rel, i))
                    continue
                text = unemphasize(text)
                if re.fullmatch(r'[\w./-]+', text) or text.lower() in ('readme', 'piece', 'here'):
                    continue          # a path or a generic word, not a title claim
                if text[:1].islower():
                    continue          # 'the companion essay' — a descriptor, not a name
                claims.setdefault(slug, set()).add((text, rel, i))
    return claims, unknown


def main(argv):
    root = instance_root(argv[1] if len(argv) > 1 else None)
    real = truth(root)
    if not real:
        sys.stderr.write('check_refs: no pieces/ found under %s\n' % root)
        return 2
    claims, unknown = collect(root)

    problems = 0
    for slug in sorted(claims):
        titles = {t for t, _f, _l in claims[slug]}
        current = real.get(slug)
        wrong = sorted(t for t in titles if current and t != current)
        if not wrong:
            continue
        problems += 1
        print('%s — README says %r' % (slug, current))
        for t in wrong:
            for title, f, ln in sorted(claims[slug]):
                if title == t:
                    print('    %-14r %s:%d' % (t, f, ln))
    for slug, f, ln in unknown:
        problems += 1
        print('%s — referenced but no such piece   %s:%d' % (slug, f, ln))

    checked = sum(len(v) for v in claims.values())
    if problems:
        print('\nchecked %d title claim(s) across %d piece(s): %d disagreement(s)'
              % (checked, len(claims), problems))
        print('The README H1 is truth. Fix the reference, not the README — and if the README is '
              'the stale one, fix it there and re-run.')
        return 1
    print('checked %d title claim(s) across %d piece(s): all consistent' % (checked, len(claims)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
