#!/usr/bin/env python3
"""piece_header.py — make a published piece's draft.md say that it is published.

Every piece keeps its text in `draft.md` for its whole life, which is right: the file is
one thing with one name, and every tool identifies a piece by it. But the scaffold note
at the top went on saying

    *Draft — being-good-essay voice. Full arc §I–§VII...*

on pieces that had been live for weeks. That line is the first thing a human reads when
opening the file, and it says the file is disposable at exactly the moment it has become
the source of record for something people are reading.

So the FILENAME does not change -- renaming would give nine tools a second name to know
about, and any call site that missed it would not error, it would silently drop the piece
from the corpus checks. The HEADER changes instead. It costs nothing: everything above
the first `---` is front matter that the converter discards, so this text can never reach
a reader.

    piece_header.py --check          what is stale (exit 1 if any)
    piece_header.py --apply [slug]   rewrite; idempotent; published pieces only
"""
import sys, os, re, argparse, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from md_to_substack import read_manifest                          # noqa: E402

BANNER_RE = re.compile(r'^\*Published \d{4}-\d{2}-\d{2}', re.M)
# "(working title)" on a piece that shipped under that exact title is the same staleness
# as "Draft —". Only removed when the manifest title matches, never guessed at.
WORKING_TITLE = re.compile(r'\s*\*\(working title\)\*\s*$')
DRAFT_PREFIX = re.compile(r'^\*Draft\s*[—-]\s*', re.M)


def split_front_matter(src):
    """(front_matter, rest). Everything before the first `---` line is front matter --
    the same rule parse_blocks uses to decide what the reader never sees."""
    lines = src.split('\n')
    for i, ln in enumerate(lines):
        if ln.strip() == '---':
            return '\n'.join(lines[:i]), '\n'.join(lines[i:])
    return None, src                                              # no separator: leave alone


def banner(man):
    """Line breaks are placed by hand, not by textwrap.

    Wrapping this text mechanically split a [markdown link](across two lines) and broke a
    `code span` in half. Markdown tolerates both, but the entire point of this header is
    that a human reads it, so the breaks go where a sentence ends.
    """
    url, title = man.get('public_url', ''), man.get('title', '')
    date = man.get('published_at', '')
    return '\n'.join([
        f"*Published {date} · [{title}]({url}) —",
        "this file is the source of record for the live post.",
        "Edits here are not live until pushed (`substack_sync push`),",
        "and `substack_verify --fresh` confirms they landed.*",
    ])


def rewrite(src, man):
    """-> (new_src, note) ; new_src is None when nothing needs doing."""
    fm, rest = split_front_matter(src)
    if fm is None:
        return None, 'no `---` separator — left alone'

    paras = [p for p in re.split(r'\n[ \t]*\n', fm) if p.strip()]
    head = [p for p in paras if p.lstrip().startswith('#')]
    body = [p for p in paras if not p.lstrip().startswith('#')]
    if not head:
        return None, 'no H1 in the front matter — left alone'

    # Drop any banner we wrote before, so running twice is a no-op rather than a stack.
    body = [p for p in body if not BANNER_RE.match(p.strip())]
    # The note keeps everything it said; it just stops calling itself a draft.
    body = [DRAFT_PREFIX.sub('*', p, count=1) for p in body]

    h1 = head[0]
    if WORKING_TITLE.search(h1) and man.get('title'):
        stem = WORKING_TITLE.sub('', h1).lstrip('# ').strip()
        if stem == man['title'].strip():                          # shipped under this name
            h1 = WORKING_TITLE.sub('', h1)

    # Normalize the seam. Without this the blank lines between the last front-matter
    # paragraph and `---` drift by one on every run, so the tool never converges and
    # --check can never report a clean tree.
    new_fm = '\n\n'.join([h1, banner(man)] + body + head[1:])
    new_src = new_fm.rstrip() + '\n\n' + rest.lstrip('\n')
    if new_src == src:
        return None, 'already current'
    return new_src, 'updated'


def live_pieces(repo, only):
    out = []
    pdir = os.path.join(repo, 'pieces')
    for name in sorted(os.listdir(pdir)):
        if only and name not in only:
            continue
        d = os.path.join(pdir, name)
        if not os.path.isfile(os.path.join(d, 'draft.md')):
            continue
        man = read_manifest(os.path.join(d, 'publish.yaml'))
        if not man.get('public_url'):
            continue                                              # not live: still a draft
        if not man.get('published_at'):
            print(f"  {name}: live but no published_at in publish.yaml — skipped")
            continue
        out.append((name, d, man))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('slugs', nargs='*')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--repo', default=os.path.dirname(os.path.dirname(HERE)))
    a = ap.parse_args()
    if not (a.apply or a.check):
        ap.error('pass --check or --apply')

    stale = 0
    for name, d, man in live_pieces(a.repo, set(a.slugs)):
        p = os.path.join(d, 'draft.md')
        src = open(p).read()
        new, note = rewrite(src, man)
        if new is None:
            if note != 'already current':
                print(f"  {name:<30} {note}")
            continue
        stale += 1
        if a.apply:
            open(p, 'w').write(new)
            print(f"  {name:<30} updated")
        else:
            print(f"  {name:<30} stale header")
    if a.check:
        print(f"\n{stale} piece(s) need the header updated")
        return 1 if stale else 0
    print(f"\n{stale} piece(s) updated")
    return 0


if __name__ == '__main__':
    sys.exit(main())
