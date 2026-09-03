#!/usr/bin/env python3
"""substack_verify.py — does the repo match what readers actually see?

The regression suite proves a draft matches its SEALED BASELINE. That is a claim about
this repository and nothing else: a baseline is a local file, and a piece can match its
baseline perfectly while the live post says something different — because someone edited
on Substack, because an "Update" was never clicked, or because a push half-landed.

This tool closes that gap from the reader's side. It fetches the PUBLIC page over plain
HTTP — no browser, no credentials, the same bytes a reader gets — pulls the post out of
the `window._preloads` blob the page ships, renders the local draft, and compares them
block for block and footnote for footnote.

It is deliberately NOT part of test_suite.py. That suite promises no network calls, and
that promise is worth more than the convenience of one runner.

    python3 substack_verify.py                # every published piece
    python3 substack_verify.py pieces/lord-lord
    python3 substack_verify.py --fresh        # bypass the CDN cache (use after an Update)
    python3 substack_verify.py --archive      # the reader's list: every live post has a
                                              # title + subtitle and the desk knows it

WITHOUT --fresh THIS TOOL CAN REPORT DRIFT THAT DOES NOT EXIST, and it did on 2026-09-03: a
sweep of 26 pieces returned three DRIFTED, and all three came back MATCH the moment the same
pieces were re-checked cache-busted. The CDN was serving pages older than the posts. A false
DRIFT is worse than a false MATCH here, because the obvious response to drift is to push the
draft over the live post — repairing something that was never broken, and overwriting whatever
the cached copy was too old to show. PREFER --fresh, and never act on a cached DRIFT.

Exit: 0 all checked pieces match | 1 drift | 2 nothing could be checked.

Reaching zero pieces is a FAILURE, not a pass. A run that checked nothing must never be
able to report success — that is the whole failure mode this tool exists to catch.
"""
import sys, os, re, json, time, argparse, subprocess, urllib.request, urllib.error
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from md_to_substack import read_manifest, render_reader          # noqa: E402
from substack_sync import H                                      # noqa: E402

UA = 'writing-desk-verify/1.0 (+repo consistency check)'
TIMEOUT = 15          # per request; a page that takes longer is not going to arrive
ATTEMPTS = 2
BUDGET = 300          # whole-run ceiling, seconds

VOID  = {'img','br','hr','input','source','meta','link','col','area','base','wbr','embed','track'}
BLOCK = {'p','h1','h2','h3','h4','h5','h6','blockquote','ul','ol','pre'}
SKIP_TAG   = {'figure','svg','button','style','script','picture','video','audio','noscript'}
SKIP_CLASS = {'captioned-image-container','subscribe-widget','button-wrapper','poll',
              'embedded-post-wrap','embedded-post','paywall','digest-post-embed',
              'tweet','native-video-embed','footnote-number','pullquote','image-link',
              'subscription-widget-wrap','subscription-widget-wrap-editor',
              'subscription-widget','share-dialog','comments-section'}


class Extract(HTMLParser):
    """body_html -> the (body, footnotes) shape render_reader produces for a draft."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.body, self.fns = [], []
        self.depth = 0
        self.skip_to = self.fn_to = self.cap_to = self.anchor_to = None
        self.buf = self.buf_depth = self.buf_tag = None

    def _enter(self, tag, attrs):
        cls = set(dict(attrs).get('class', '').split())
        if self.skip_to is not None:
            return
        if 'footnote-anchor' in cls:                 # superscript marker: drop its text
            self.anchor_to = self.depth; return
        if 'footnote-content' in cls:
            self.cap_to = self.depth; self.buf = []; self.buf_depth = None; return
        if 'footnote' in cls:
            self.fn_to = self.depth; return
        if tag in SKIP_TAG or (cls & SKIP_CLASS):
            self.skip_to = self.depth; return
        if self.cap_to is not None or self.fn_to is not None:
            return
        if tag in BLOCK and self.buf is None:
            # Only the OUTERMOST block opens a buffer. Substack nests prose as
            # <li><p>..</p></li> and <blockquote><p>..</p></blockquote>; letting an
            # inner </p> close the buffer splits one block into several and reports
            # drift that is not there.
            self.buf, self.buf_depth, self.buf_tag = [], self.depth, tag

    def _leave(self, tag):
        if self.skip_to is not None:
            if self.depth == self.skip_to: self.skip_to = None
            return
        if self.anchor_to is not None and self.depth == self.anchor_to:
            self.anchor_to = None; return
        if self.cap_to is not None:
            if self.depth == self.cap_to:
                self.cap_to = None
                self.fns.append(''.join(self.buf or [])); self.buf = None
            return
        if self.fn_to is not None:
            if self.depth == self.fn_to: self.fn_to = None
            return
        if tag in BLOCK and self.buf is not None and self.depth == self.buf_depth:
            t = ''.join(self.buf)
            if t.strip(): self.body.append((self.buf_tag, t))
            self.buf = self.buf_depth = self.buf_tag = None

    def handle_starttag(self, tag, attrs):
        if tag in VOID: return
        self._enter(tag, attrs); self.depth += 1

    def handle_startendtag(self, tag, attrs):
        pass                                          # self-closing: no subtree, no text

    def handle_endtag(self, tag):
        if tag in VOID: return
        self.depth -= 1; self._leave(tag)

    def handle_data(self, d):
        if self.skip_to is not None or self.anchor_to is not None: return
        if self.buf is not None: self.buf.append(d)


def live_blocks(body_html):
    p = Extract(); p.feed(body_html); p.close()
    # The draft renderer merges adjacent blockquotes; Substack keeps them separate.
    out = []
    for tag, text in p.body:
        if tag == 'blockquote' and out and out[-1][0] == 'blockquote':
            out[-1] = (tag, out[-1][1] + text)
        else:
            out.append((tag, text))
    return [t for _, t in out], p.fns


def fetch_public(url, fresh=False, attempts=ATTEMPTS):
    if fresh:
        url += ('&' if '?' in url else '?') + f'_cb={int(time.time())}'
    headers = {'User-Agent': UA}
    if fresh:
        headers['Cache-Control'] = 'no-cache'
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            # An HTTP status is a definitive answer from the server. Retrying a 403 or
            # a 404 just spends time to be told the same thing again.
            raise
        except Exception as e:                                    # noqa: BLE001
            last = e
            if i + 1 < attempts:
                time.sleep(2 * (i + 1))
    raise last


def extract_post(page_html):
    m = re.search(r'window\._preloads\s*=\s*JSON\.parse\((".*?")\)\s*;?\s*</script>',
                  page_html, re.S)
    if not m:
        return None
    return json.loads(json.loads(m.group(1))).get('post')


def pieces_touched_by(repo, rev_range):
    """Piece slugs whose directory a commit range touched.

    Scoping the check to what changed is the difference between a verifier you run and
    one you mean to run: the full sweep is 23 network round-trips, and most commits
    touch one piece.

    An empty range is NOT an error and NOT a silent pass -- the caller reports that
    nothing published was touched, so "no pieces to check" can never be mistaken for
    "everything matches".
    """
    try:
        out = subprocess.run(['git', '-C', repo, 'diff', '--name-only', rev_range],
                             capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            return None, out.stderr.strip().splitlines()[-1] if out.stderr else 'git failed'
    except Exception as e:                                        # noqa: BLE001
        return None, f'{type(e).__name__}: {e}'
    slugs = []
    for path in out.stdout.splitlines():
        parts = path.split('/')
        if len(parts) >= 2 and parts[0] == 'pieces' and parts[1] not in slugs:
            slugs.append(parts[1])
    return slugs, None


def resolve_piece(repo, arg):
    """Resolve a piece argument to a directory, and say WHY when it cannot.

    Accepts either a path (`pieces/not-yet`) or a bare slug (`not-yet`), because the rest of the
    desk's tooling is addressed by slug and there is no reason this one should differ.

    Returns `(dir, url, reason)`. Exactly one of `url` / `reason` is set.

    The reason strings matter more than the convenience. Before this existed, every failure
    printed "no public_url — not published": a typo'd slug, a piece that was never composed, and
    a genuinely unpublished piece were indistinguishable. On 2026-09-02 that cost a real
    diagnosis — `substack_verify --fresh forking-paths` reported a freshly published essay as not
    published, because the bare slug resolved to a directory that does not exist and an absent
    file reads as an empty manifest. A message that names the wrong cause is worse than no
    message, because it is believed.
    """
    arg = arg.rstrip('/')
    d = arg if os.path.isdir(arg) else None
    if d is None:
        cand = os.path.join(repo, 'pieces', os.path.basename(arg))
        d = cand if os.path.isdir(cand) else None
    if d is None:
        return (arg, None, f"no such piece — tried ./{arg}/ and pieces/{os.path.basename(arg)}/")
    man = os.path.join(d, 'publish.yaml')
    if not os.path.isfile(man):
        return (d, None, "no publish.yaml — never composed to Substack")
    url = read_manifest(man).get('public_url')
    if not url:
        return (d, None, "no public_url in publish.yaml — composed but not published")
    return (d, url, None)


def published_pieces(repo, only=None):
    out = []
    pieces = os.path.join(repo, 'pieces')
    if not os.path.isdir(pieces):
        return out
    for name in sorted(os.listdir(pieces)):
        if only is not None and name not in only:
            continue
        d = os.path.join(pieces, name)
        if not os.path.isfile(os.path.join(d, 'draft.md')):
            continue
        url = read_manifest(os.path.join(d, 'publish.yaml')).get('public_url')
        if not url or '.invalid' in url:          # fixtures are not reachable by design
            continue
        out.append((name, d, url))
    return out


def _norm_header(s):
    s = (s or '')
    for a, b in (('\u2018', "'"), ('\u2019', "'"), ('\u201c', '"'), ('\u201d', '"'),
                 ('\u2014', '--'), ('\u2013', '-'), ('\u2026', '...'), ('\u00a0', ' ')):
        s = s.replace(a, b)
    return re.sub(r'\s+', ' ', s).strip()


def header_drift(post, man):
    """Title and subtitle: the two lines of a post the body comparison never sees.

    The body check was blind to them by construction -- it compares blocks of body_html,
    and the header is not in body_html. So a post could match block-for-block while its
    subtitle was empty, and one did: live from 2026-08-05, found 2026-09-03, never once
    reported by a verify run. An EMPTY live subtitle is drift even if the manifest is empty
    too, because the reader sees the archive card, not the manifest."""
    out = []
    for k in ('title', 'subtitle'):
        live, want = _norm_header(post.get(k)), _norm_header(man.get(k))
        if not live:
            out.append(f'live post has NO {k}')
        elif want and live != want:
            out.append(f'{k} differs: live {live[:60]!r} vs manifest {want[:60]!r}')
    return out


def walk_archive(base, fresh=False, page=50):
    """Every post the publication serves publicly, via its archive API, newest first.

    This is the check that does not start from the repo. `published_pieces()` can only
    verify what the desk knows about; a post composed straight in Substack, or one that
    predates the desk, is invisible to it. The archive is the reader's list, and the
    reader's list is the one that has to be right."""
    posts, offset, seen = [], 0, set()
    while True:
        url = f'{base}/api/v1/archive?sort=new&limit={page}&offset={offset}'
        batch = [p for p in json.loads(fetch_public(url, fresh)) if p.get('id') not in seen]
        # A SHORT PAGE IS NOT THE LAST PAGE. Substack caps a page below the limit asked for
        # (measured 2026-09-03: limit=50 returned 23, and offset=23 returned 6 more), so the
        # only end-of-list signal that can be trusted is an empty one. Stopping on a short
        # page silently dropped the six oldest posts -- including the one with no subtitle.
        if not batch:
            return posts
        posts += batch
        seen.update(p.get('id') for p in batch)
        offset += len(batch)


def audit_archive(repo, fresh):
    """Cross the live archive with the desk. Returns (rows, problems)."""
    known = {}
    pieces = os.path.join(repo, 'pieces')
    for name in sorted(os.listdir(pieces)) if os.path.isdir(pieces) else []:
        man = read_manifest(os.path.join(pieces, name, 'publish.yaml'))
        u = man.get('public_url', '')
        if u:
            known[u.rstrip('/').rsplit('/', 1)[-1]] = (name, man)
    if not known:
        return [], ['no piece records a public_url, so the publication cannot be located']
    base = re.match(r'https?://[^/]+', next(iter(known.values()))[1]['public_url']).group(0)
    posts = walk_archive(base, fresh)
    rows, problems = [], []
    for p in posts:
        slug = p.get('slug', '')
        name, man = known.get(slug, (None, None))
        flags = []
        if not _norm_header(p.get('subtitle')):
            flags.append('NO SUBTITLE')
        if not _norm_header(p.get('title')):
            flags.append('NO TITLE')
        if name is None:
            flags.append('not in the desk')
        elif man is not None:
            flags += [f for f in header_drift(p, man) if 'differs' in f]
        rows.append((slug, name or '-', (p.get('post_date') or '')[:10], flags))
        problems += [f'{slug}: {f}' for f in flags]
    return rows, problems


def verify(name, piece_dir, url, fresh):
    try:
        post = extract_post(fetch_public(url, fresh))
    except urllib.error.HTTPError as e:
        return ('UNREACHABLE', f'HTTP {e.code} {e.reason}', {})
    except Exception as e:                                        # noqa: BLE001
        return ('UNREACHABLE', f'{type(e).__name__}: {str(e)[:60]}', {})
    if not post:
        return ('UNREACHABLE', 'no _preloads in page (login wall or layout change?)', {})

    lb, lf = live_blocks(post.get('body_html') or '')
    body, fns, _residual, _iss = render_reader(piece_dir)
    facts = {'audience': post.get('audience'),
             'emailed': post.get('email_sent_at'),
             'blocks': f'{len(lb)}/{len(body)}', 'fns': f'{len(lf)}/{len(fns)}'}
    header = header_drift(post, read_manifest(os.path.join(piece_dir, 'publish.yaml')))
    if (not header and [H(x) for x in lb] == [H(x) for x in body]
            and [H(x) for x in lf] == [H(x) for x in fns]):
        return ('MATCH', '', facts)

    detail = list(header)
    if len(lb) != len(body): detail.append(f'body {len(lb)} live vs {len(body)} draft')
    if len(lf) != len(fns):  detail.append(f'footnotes {len(lf)} live vs {len(fns)} draft')
    for i, (a, b) in enumerate(zip([H(x) for x in body], [H(x) for x in lb])):
        if a != b:
            detail.append(f'first differing block #{i}: live {lb[i][:70]!r}')
            break
    for i, (a, b) in enumerate(zip([H(x) for x in fns], [H(x) for x in lf])):
        if a != b:
            detail.append(f'first differing footnote #{i + 1}: live {lf[i][:70]!r}')
            break
    return ('DRIFT', '; '.join(detail), facts)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('pieces', nargs='*', help='piece dirs (default: every published piece)')
    ap.add_argument('--fresh', action='store_true', help='bypass the CDN cache')
    ap.add_argument('--repo', default=os.path.dirname(os.path.dirname(HERE)))
    ap.add_argument('--list', action='store_true',
                    help='list what is live (and therefore in scope) without fetching')
    ap.add_argument('--changed', nargs='?', const='HEAD~1..HEAD', metavar='RANGE',
                    help='only pieces this commit range touched (default HEAD~1..HEAD; '
                         'for a pre-push hook, origin/main..HEAD)')
    ap.add_argument('--budget', type=int, default=BUDGET,
                    help='stop after this many seconds rather than grinding (0 = no limit)')
    ap.add_argument('--archive', action='store_true',
                    help='walk the PUBLICATION\'s public archive instead of the repo: every '
                         'live post must have a title and a subtitle and be known to the desk')
    a = ap.parse_args()

    if a.archive:
        rows, problems = audit_archive(a.repo, a.fresh)
        if not rows:
            print('FAILED: the archive returned no posts' + (f' ({problems[0]})' if problems else ''))
            return 2
        w = max(len(r[0]) for r in rows)
        print(f"{len(rows)} live post(s) in the publication archive"
              + ("  [cache-busted]" if a.fresh else ""))
        for slug, name, date, flags in rows:
            print(f"  {slug:<{w}}  {date}  {name:<28} {'; '.join(flags)}")
        if problems:
            print(f"\nFAILED: {len(problems)} problem(s) a reader can see:")
            for pr in problems: print(f"  {pr}")
            return 1
        print("\nevery live post has a title and a subtitle, and the desk knows all of them.")
        return 0

    if a.list:
        # "Which pieces must match Substack?" should be one command, not an inference
        # from a filename. public_url is the authoritative answer and the only one.
        pieces = os.path.join(a.repo, 'pieces')
        rows = []
        for name in sorted(os.listdir(pieces)):
            d = os.path.join(pieces, name)
            if not os.path.isfile(os.path.join(d, 'draft.md')):
                continue
            man = read_manifest(os.path.join(d, 'publish.yaml'))
            if man.get('public_url'):
                state = 'LIVE'
            elif man.get('post_url'):
                state = 'composed'
            else:
                state = 'draft'
            rows.append((name, state, man.get('public_url', '')))
        w = max(len(r[0]) for r in rows) if rows else 0
        for name, state, url in rows:
            print(f"  {name:<{w}}  {state:<9} {url}")
        live = sum(1 for r in rows if r[1] == 'LIVE')
        print(f"\n{live} live (in scope for verification), "
              f"{sum(1 for r in rows if r[1]=='composed')} composed, "
              f"{sum(1 for r in rows if r[1]=='draft')} draft")
        return 0

    if a.changed:
        slugs, err = pieces_touched_by(a.repo, a.changed)
        if err:
            print(f"could not resolve {a.changed}: {err}")
            return 2
        if not slugs:
            print(f"{a.changed} touched no piece — nothing to verify")
            return 0
        targets = published_pieces(a.repo, only=set(slugs))
        unpublished = [s_ for s_ in slugs if s_ not in {t[0] for t in targets}]
        print(f"{a.changed} touched {len(slugs)} piece(s): {', '.join(slugs)}")
        for u in unpublished:
            print(f"  skip  {u}  (not published — nothing live to compare against)")
        if not targets:
            print("none of them are published — nothing to verify")
            return 0
    elif a.pieces:
        targets = []
        for arg in a.pieces:
            d, url, reason = resolve_piece(a.repo, arg)
            if reason:
                print(f"  skip  {os.path.basename(d)}  ({reason})")
                continue
            targets.append((os.path.basename(d), d, url))
    else:
        targets = published_pieces(a.repo)

    if not targets:
        print('no published pieces to verify'); return 2

    print(f"verifying {len(targets)} published piece(s) against the live publication"
          + ("  [cache-busted]" if a.fresh else ""))
    w = max(len(t[0]) for t in targets)
    drift, unreachable, ok, emailed = [], [], 0, []
    started, gave_up = time.time(), None
    for n, (name, d, url) in enumerate(targets):
        # Two ways to stop early, both so a blocked run reports quickly instead of
        # spending half an hour proving the same thing 23 times.
        if a.budget and time.time() - started > a.budget:
            gave_up = f'time budget of {a.budget}s exhausted'; break
        if n >= 3 and ok == 0 and len(drift) == 0 and len(unreachable) == n:
            gave_up = 'the first 3 pages were all unreachable — treating this as blocked'
            break
        status, detail, facts = verify(name, d, url, a.fresh)
        line = f"  {name:<{w}}  {status:<12}"
        if facts.get('blocks'): line += f" {facts['blocks']:>10} body {facts['fns']:>8} fn"
        print(line + (f"   {detail}" if detail else ''))
        if status == 'MATCH':
            ok += 1
            if facts.get('emailed'): emailed.append(f"{name} ({facts['emailed']})")
        elif status == 'DRIFT':
            drift.append(name)
        else:
            unreachable.append(f'{name}: {detail}')
        time.sleep(0.3)                                # be a polite client

    if gave_up:
        print(f"\nstopped early: {gave_up}")
        print(f"  {len(targets) - len(unreachable) - ok - len(drift)} piece(s) not attempted")
    print(f"\n{ok} match, {len(drift)} drifted, {len(unreachable)} unreachable")
    for u in unreachable: print(f"  unreachable  {u}")
    for d in drift:       print(f"  DRIFTED      {d}")
    if emailed:
        print("  note: these posts record an email send: " + ', '.join(emailed))

    # "Nothing checked" means nothing was FETCHED AND COMPARED. A piece that drifted
    # was checked -- that is a finding, not a failure to look.
    if ok + len(drift) == 0:
        print("\nFAILED: nothing could be checked. A run that verified no pages is not a pass.")
        return 2
    if drift:
        print(f"\nFAILED: {len(drift)} piece(s) differ from the live publication.")
        return 1
    print("\nthe repo matches the publication.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
