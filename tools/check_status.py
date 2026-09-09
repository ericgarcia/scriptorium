#!/usr/bin/env python3
"""check_status.py — does the desk's PROSE still agree with its manifests?

Three tools already guard three other things, and a sentence can be wrong while all
three pass:

  check_links.py   a URL resolves.
  check_refs.py    a cross-reference names the right piece (titles move).
  outlet_audit.py  a piece exists on every outlet it declares (half-published).

None of them reads what the prose CLAIMS. This does.

WHY (2026-09-09, four times in one week)

  * *In Vain* — the founding-writings index and the charter both called it "composed as
    a private draft; unpublished". It had gone live that morning.
  * *The Mask Comes Off Last* — "unpublished", and carrying no link, five days after it
    published. The index was breaking its own stated rule, that live pieces link to
    their reader URL.
  * *Rising After Falls* — published by another session mid-afternoon; the index still
    called it unpublished an hour later. Found by the first run of this tool.
  * The charter still called the Fellowship's domain "open, and Eric's call" after the
    site had shipped. See the limits below: this one is not mechanically visible.

Every case has the same shape. `publish.yaml` is written by the sync tools against the
live post; the prose is written by hand. **The manifest is the witness**, and prose that
contradicts it is what this reports.

WHAT IT CHECKS

  unpublished  prose calls a piece unpublished; its manifest carries a reader URL.
  phantom      prose links a piece as live; its manifest carries no reader URL at all.
  unlinked     a live piece is named with no link, against the house rule — reported
               only in files that STATE that rule, so it never fires on a document that
               never made the promise.
  address      with --prefer OUTLET, a piece linked at another outlet's URL when the
               preferred outlet has one. Use it after moving a publication's home.

WHAT IS DELIBERATELY NOT CHECKED, on check_refs.py's principle that a checker which
cries about correct files gets switched off:

  * `DASHBOARD.md`. It is generated from `DASHBOARD.d`; the fragments are checked instead,
    so a finding names the file you would actually edit.
  * `log/`, `corrections.md`, and everything under a dated heading. They are append-only
    records of what was true when written. An entry saying "unpublished" is accurate
    history, and "fixing" it would be editing the evidence.
  * Any line that marks its own supersession — retired, superseded, (was …), formerly,
    replaced. Naming an old state in order to retire it is the correct use of one.
  * Whether a DECISION has gone stale. The charter case above is real drift and this
    cannot see it: no file records that a decision was made, so there is nothing to
    disagree with. Only a person re-reading catches that, and it is worth saying plainly
    rather than implying the sweep is complete.

CONFIG (instance-side; the framework holds no URLs)

  --outlets publishing/outlets.yaml — the same registry outlet_audit.py reads. A piece
  is PUBLISHED if any outlet's `manifest_url_key` is set in its manifest, or if it still
  opts in the pre-outlets way with `site: true` and the registry names a legacy_outlet.

  A LIMIT OF `address`, worth knowing before trusting a clean run: it can only compare
  what the manifest records. A piece opting in the legacy way carries no outlet URL, so
  there is no preferred address to compare a link against and the check stays silent on
  it — silence there means "not checked", not "correct". At the time of writing 30 of 40
  pieces are in that state. `unpublished`, `phantom` and `unlinked` are unaffected: they
  only need to know whether an address exists, not what it is.

USAGE
  python3 check_status.py [path ...] [--pieces DIR] [--outlets FILE] [--prefer OUTLET]

EXIT
  0  the prose agrees with the manifests
  1  usage / nothing could be checked
  4  at least one disagreement — each named with file, line, and what the manifest says
"""
import argparse
import os
import re
import sys

try:
    import yaml
except ImportError:
    yaml = None

SKIP_DIR_PARTS = ('/log/', '/.git/', '/node_modules/', '/__pycache__/', '/.next/', '/out/')
# DASHBOARD.md is GENERATED from DASHBOARD.d by dashboard.py, so a claim in it is a copy
# of a claim in a fragment. Checking both reports every finding twice and points the
# second one at a file that will be overwritten. The fragments are checked; the build
# output is not, for the same reason nothing lints a build output.
SKIP_FILES = ('corrections.md', 'DASHBOARD.md')

SUPERSESSION = re.compile(
    r'retired|supersed|formerly|\bwas\b\s*[:"“]|\(was\b|replaced|previously|no longer|'
    r'what this replaced|until \d{4}-\d{2}-\d{2}', re.I)

LOG_HEADING = re.compile(r'^#{1,6}\s+\d{4}-\d{2}-\d{2}\b')

UNPUBLISHED = re.compile(
    r'\bunpublished\b|\bnot yet published\b|\bprivate draft\b|\bnot published\b|'
    r'\bunreleased\b|\bdraft only\b', re.I)

SLUG_REF = re.compile(r'`([a-z0-9][a-z0-9-]{2,})`')
MD_LINK = re.compile(r'\[([^\]]+)\]\((https?://[^)\s]+)\)')
RULE_STATED = re.compile(r'live pieces link to their reader url', re.I)


def load_outlets(path):
    if not path or not os.path.exists(path):
        return {}, None
    cfg = yaml.safe_load(open(path).read()) or {}
    return cfg.get('outlets') or {}, cfg.get('legacy_outlet')


def reader_urls(man, outlets, legacy):
    """{outlet: url} for every outlet this piece actually has an address on."""
    out = {}
    for name, spec in outlets.items():
        key = (spec or {}).get('manifest_url_key')
        val = man.get(key) if key else None
        if val:
            out[name] = str(val).rstrip('/')
    if not out and man.get('site') is True and legacy:
        # Pre-outlets opt-in: it says the piece goes to the legacy outlet, but records no
        # URL, so there is no address to compare a link against — only the fact of it.
        out[legacy] = None
    return out


def load_manifests(pieces_dir, outlets, legacy):
    got = {}
    if not os.path.isdir(pieces_dir):
        return got
    for name in sorted(os.listdir(pieces_dir)):
        p = os.path.join(pieces_dir, name, 'publish.yaml')
        if not os.path.exists(p):
            continue
        try:
            man = yaml.safe_load(open(p).read()) or {}
        except Exception:
            continue
        got[name] = {'urls': reader_urls(man, outlets, legacy), 'title': man.get('title')}
    return got


def markdown_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules']
            for f in files:
                if not f.endswith('.md') or f in SKIP_FILES:
                    continue
                full = os.path.join(root, f)
                if any(s in full.replace(os.sep, '/') for s in SKIP_DIR_PARTS):
                    continue
                yield full


def blocks(text):
    """(line_no, block) per bullet or paragraph.

    A claim and the slug it is about share a bullet, not a line — the index wraps its
    entries over three or four — so the bullet is the unit that has to be read. A dated
    heading switches off the rest of the file: below it is history."""
    out, cur, start = [], [], 1

    def flush():
        nonlocal cur
        if cur:
            out.append((start, '\n'.join(cur)))
            cur = []

    for i, ln in enumerate(text.split('\n'), 1):
        if LOG_HEADING.match(ln):
            break
        # A TABLE ROW IS ITS OWN BLOCK. These READMEs carry "seams" tables listing several
        # siblings, one per row. Treated as one paragraph, a single "unpublished" in any
        # row was attributed to every slug in the table — 60-odd false positives on the
        # first full sweep, which is exactly how a checker gets switched off.
        if ln.lstrip().startswith('|'):
            flush()
            out.append((i, ln))
            continue
        if (ln.startswith(('- ', '* ', '+ ')) or not ln.strip()) and cur:
            flush()
        if not ln.strip():
            continue
        if not cur:
            start = i
        cur.append(ln)
    flush()
    return out


def check(paths, pieces_dir, outlets_file, prefer):
    outlets, legacy = load_outlets(outlets_file)
    manifests = load_manifests(pieces_dir, outlets, legacy)
    if not manifests:
        print(f"error: no piece manifests under {pieces_dir}", file=sys.stderr)
        return None
    if prefer and prefer not in outlets:
        print(f"error: --prefer {prefer} is not an outlet in {outlets_file}", file=sys.stderr)
        return None

    findings = []
    for path in markdown_files(paths):
        try:
            text = open(path).read()
        except (OSError, UnicodeDecodeError):
            continue
        rule_here = bool(RULE_STATED.search(text))

        for line_no, block in blocks(text):
            if SUPERSESSION.search(block):
                continue
            refs = [s for s in SLUG_REF.findall(block) if s in manifests]
            if not refs:
                continue
            links = MD_LINK.findall(block)

            for slug in refs:
                man = manifests[slug]
                urls = man['urls']
                live = bool(urls)

                if live and _claims_near(block, slug, UNPUBLISHED):
                    where = ', '.join(f"{o}={u}" for o, u in urls.items() if u) or \
                            ', '.join(urls)
                    findings.append((path, line_no, 'unpublished', slug,
                                     f"prose says unpublished; manifest has {where}"))
                    continue

                if not live and links:
                    title = man['title'] or ''
                    names_it = any(
                        _slugify(t.strip('*_ ')) in (slug, _slugify(title))
                        for t, _ in links)
                    if names_it:
                        findings.append((path, line_no, 'phantom', slug,
                                         "prose links it as live; manifest has no reader URL"))
                    continue

                if live and rule_here and not links:
                    findings.append((path, line_no, 'unlinked', slug,
                                     "live, and this file states that live pieces link "
                                     "to their reader URL"))
                    continue

                if prefer and live and links:
                    want = urls.get(prefer)
                    if not want:
                        continue
                    hrefs = [u.rstrip('/') for _t, u in links]
                    if want in hrefs:
                        continue
                    other = [(o, u) for o, u in urls.items()
                             if o != prefer and u and u in hrefs]
                    if other:
                        findings.append((path, line_no, 'address', slug,
                                         f"links {other[0][0]} ({other[0][1]}); "
                                         f"{prefer} is {want}"))
    return findings


# How far a claim can sit from the slug it is about and still be about it. An index entry
# puts them in the same sentence; the dashboard puts twenty slugs and one stray
# "unpublished" in a single 3,000-character block, and attributing that word to all twenty
# produced 57 false positives on the first full sweep. Proximity is what separates the two,
# and it is a better rule than excluding the file — the dashboard's claims are worth
# checking, just not at block scale.
NEAR = 320


def _claims_near(block, slug, pattern):
    """Does `pattern` match within NEAR characters of a `slug` reference in this block?"""
    refs = [m.start() for m in re.finditer(r'`%s`' % re.escape(slug), block)]
    if not refs:
        return False
    return any(abs(m.start() - r) <= NEAR
               for m in pattern.finditer(block) for r in refs)


def _slugify(t):
    s = str(t).lower().replace('’', "'").replace("'", '')
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--pieces', default='pieces')
    ap.add_argument('--outlets', default='publishing/outlets.yaml')
    ap.add_argument('--prefer', default=None)
    ap.add_argument('--quiet', action='store_true')
    o = ap.parse_args()
    if yaml is None:
        print("error: pyyaml is required", file=sys.stderr)
        return 1

    findings = check(o.paths or ['.'], o.pieces, o.outlets, o.prefer)
    if findings is None:
        return 1
    if not findings:
        if not o.quiet:
            print("ok  prose agrees with the manifests")
        return 0

    by_kind = {}
    for f in findings:
        by_kind.setdefault(f[2], []).append(f)
    for kind in sorted(by_kind):
        print(f"\n{kind}  ({len(by_kind[kind])})")
        for path, line, _k, slug, why in sorted(by_kind[kind]):
            print(f"  {path}:{line}  `{slug}`")
            print(f"      {why}")
    print(f"\n{len(findings)} disagreement(s). The manifest is the witness: it is written "
          f"by the sync\ntools against the live post; the prose is written by hand.")
    return 4


if __name__ == '__main__':
    sys.exit(main())
