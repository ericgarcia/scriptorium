#!/usr/bin/env python3
"""
substack_notes.py — one Substack Note per publication, and a backlog worked one a day.

A Note is Substack's short-form feed post. Every live post gets exactly one, announcing it:
the piece's `note` companion, then the post's public URL alone as the last paragraph. The Notes
composer turns a bare post URL into that post's card by itself (measured 2026-09-10:
`setContent` with the URL as plain text rendered the publication name, the title and the hero
within three seconds), so the text is all the desk has to carry.

WHERE THE STATE LIVES — per piece, never in a shared queue

  pieces/<slug>/publish.yaml       declares the Note as the piece's `note` companion
                                   (docs/COMPANIONS.md):

                                       companions:
                                         note: note.md

  pieces/<slug>/note.md            the Note's text, under a `form:` / `style:` header closed by
                                   `---`. Form `note` (short prose paragraphs) or `poem` (lines
                                   and stanzas). Plain text; NO URL — the post's own link is
                                   appended here, from publish.yaml, when the Note is built.

  pieces/<slug>/publish.yaml       a `substack_note:` block, written by `record`:

                                       substack_note:
                                         posted_at: 2026-09-11
                                         note_url: https://substack.com/@<handle>/note/c-<id>

                                   or `substack_note:` / `  skip: <reason>` for a post that
                                   should never get one.

  The backlog is DERIVED — every live post with no Note, oldest `published_at` first — so
  there is no queue file for two sessions to read, edit and write back over each other.

A POEM IN A NOTE (measured 2026-09-11)

  The Notes editor's schema has no hard-break node (paragraph, text, lists, blockquote,
  codeBlock, mention — nothing else), so a line break inside a paragraph cannot be sent. A poem
  goes ONE PARAGRAPH PER LINE, which is how multi-line Notes already render in the feed: tight
  lines, no gap (a posted five-line Note is five <p>, no <br>). An EMPTY paragraph between stanzas
  is kept by the editor and DROPPED by the server: measured 2026-09-11 on the first poem Note
  (c-334978586), 64 paragraphs sent with 11 empty, 53 live with 0 empty. The same day, a private
  Notes draft (POST /api/v1/comment/draft) showed the rule: any whitespace-only paragraph is
  stripped (empty, U+00A0, U+200B, U+3000) and a non-whitespace one is kept (U+2800, "·").
  So a stanza gap is a MARKER line — `stanza_break:` in note.md's header: `braille` (U+2800,
  reads as an empty line; the default), `dot` ("·", visible), or `none`. Screen readers may
  announce U+2800; `dot` is the accessible choice.

CADENCE

  A FRESH publication's Note (posted_at == published_at) goes out with the post, always.
  A BACKLOG Note (any other day) goes out at most one per calendar day: `next` exits 3 once
  today's is recorded. That is the whole of "catch up one day at a time", and it is a guard
  rather than a reminder because a backlog posted in one sitting is the thing it prevents.

Commands

  status                  every live post: posted / drafted / missing / skip, and what's next
  next                    the next backlog post (exit 3 when today's backlog Note is done)
  text <slug>             the Note as JSON: paragraphs, sha256, and the composer snippet
  record <slug> --url U   write the substack_note block after the Post click; refuses twice
  verify [<slug> ...]     read the PUBLIC notes feed (no login) and confirm each recorded Note
                          exists and names its post — and list Notes the desk has no record of

Posting is not this tool's job. It prepares the text and checks the result; the `publish`
skill drives the composer, and a Note is posted only on the author's word.

Exit: 0 ok, 1 problem found, 2 could not read, 3 today's backlog Note is already out.
"""
import sys, os, re, json, argparse, datetime, hashlib, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from md_to_substack import read_manifest                                  # noqa: E402
import companions                                                         # noqa: E402

BLOCK = 'substack_note'
FEED = 'https://substack.com/api/v1/reader/feed/profile/{id}?types%5B%5D=note'
UA = 'Mozilla/5.0 (writing-desk substack_notes)'


def default_pieces():
    env = os.environ.get('DESK_PIECES')
    if env:
        return os.path.abspath(env)
    return os.path.join(os.path.dirname(os.path.dirname(HERE)), 'pieces')


# ------------------------------------------------------------------------ the corpus
def load(pieces_dir):
    """Every piece that is a live POST (not a page), with its Note state."""
    out = []
    for slug in sorted(os.listdir(pieces_dir)):
        d = os.path.join(pieces_dir, slug)
        man = read_manifest(os.path.join(d, 'publish.yaml'))
        url, date = man.get('public_url', ''), man.get('published_at', '')
        if not url or not re.match(r'\d{4}-\d{2}-\d{2}$', date):
            continue                                        # not live
        if man.get('substack_type') == 'page':
            continue                                        # a page is not announced
        block = man.get(BLOCK) if isinstance(man.get(BLOCK), dict) else {}
        if block.get('skip'):
            state = 'skip'
        elif block.get('posted_at'):
            state = 'posted'
        elif companions.companion(d, 'note'):
            state = 'drafted'
        else:
            state = 'missing'
        out.append({'slug': slug, 'dir': d, 'title': man.get('title', slug),
                    'public_url': url, 'published_at': date, 'state': state,
                    'posted_at': block.get('posted_at', ''),
                    'note_url': block.get('note_url', ''), 'skip': block.get('skip', '')})
    out.sort(key=lambda p: (p['published_at'], p['slug']))
    return out


def backlog(corpus):
    return [p for p in corpus if p['state'] in ('drafted', 'missing')]


def backlog_done_today(corpus, today):
    """The backlog Note that already went out today, if any. A fresh publication's own
    Note (posted the day the post went live) does not count against the cadence."""
    for p in corpus:
        if p['posted_at'] == today and p['posted_at'] != p['published_at']:
            return p
    return None


# ------------------------------------------------------------------------ the text
def note_paragraphs(comp):
    """The companion as composer paragraphs. A poem: one per line, a MARKER line between
    stanzas. Prose: one per paragraph. See A POEM IN A NOTE above for why."""
    blocks = companions.paragraphs(comp)
    if companions.FORMS[comp['form']]['lines'] != 'keep':
        return [b[0] for b in blocks]
    gap = companions.stanza_marker(comp)
    out = []
    for i, stanza in enumerate(blocks):
        if i:
            out.append(gap)
        out += stanza
    return out + [gap]                       # the last stanza's gap, before the card


def read_note(piece_dir, public_url):
    """-> (paragraphs, problems). The last paragraph is the post URL, added here."""
    comp = companions.companion(piece_dir, 'note')
    if not comp:
        return [], ['no `note` companion declared in publish.yaml']
    problems = companions.problems_of(comp, piece_dir)
    if problems:
        return [], problems
    return note_paragraphs(comp) + [public_url], []


def note_hash(paras):
    """What the composer must echo back: paragraph texts joined by a blank line. Computed
    from the editor's JSON on the page side, so it cannot depend on getText()'s separator."""
    return hashlib.sha256('\n\n'.join(paras).encode('utf-8')).hexdigest()


def composer_js(paras, title):
    doc = {'type': 'doc', 'content': [
        {'type': 'paragraph', 'content': [{'type': 'text', 'text': t}]} if t
        else {'type': 'paragraph'} for t in paras]}
    return (
        "await (async () => {\n"
        # Substack keeps a hidden [role=dialog] in the DOM after the composer closes, so
        # the FIRST dialog is not the composer. Take the editor that is actually on screen.
        "  const eds = [...document.querySelectorAll('[role=dialog] .tiptap')]\n"
        "    .filter(e => e.getBoundingClientRect().height > 0);\n"
        "  if (eds.length !== 1) return {refused: `need exactly one open Notes composer, found ${eds.length}`};\n"
        "  const el = eds[0], d = el.closest('[role=dialog]');\n"
        "  if (!el.editor) return {refused: 'composer has no editor handle'};\n"
        "  const ed = el.editor;\n"
        "  if (ed.getText().trim()) return {refused: 'composer is not empty', has: ed.getText().slice(0, 200)};\n"
        f"  ed.commands.setContent({json.dumps(doc, ensure_ascii=False)});\n"
        "  await new Promise(r => setTimeout(r, 3000));\n"
        "  const paras = ed.getJSON().content.map(p => (p.content || []).map(n => n.text || '').join(''));\n"
        "  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(paras.join('\\n\\n')));\n"
        "  const sha256 = [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');\n"
        f"  const card = d.innerText.includes({json.dumps(title, ensure_ascii=False)});\n"
        "  const post = [...d.querySelectorAll('button')].find(b => b.innerText.trim() === 'Post');\n"
        "  return {sha256, card, postEnabled: !!post && !post.disabled};\n"
        "})()\n")


# ------------------------------------------------------------------------ recording
def record(piece_dir, date, note_url):
    """Write the substack_note block into publish.yaml. Text edit, so every comment in the
    manifest survives. Refuses when a Note is already recorded: a post gets one."""
    path = os.path.join(piece_dir, 'publish.yaml')
    lines = open(path, encoding='utf-8').read().splitlines(keepends=True)
    start = next((i for i, l in enumerate(lines) if re.match(rf'{BLOCK}:\s*(#.*)?$', l)), None)
    block = [f'{BLOCK}:\n', f'  posted_at: {date}\n', f'  note_url: {note_url}\n']
    if start is None:
        if lines and not lines[-1].endswith('\n'):
            lines[-1] += '\n'
        lines += ['\n', '# --- Substack Note (substack_notes.py record) ---\n'] + block
    else:
        end = start + 1
        while end < len(lines) and (lines[end].startswith((' ', '\t')) or not lines[end].strip()):
            end += 1
        existing = ''.join(lines[start:end])
        if 'posted_at:' in existing:
            raise SystemExit(f'refused: {path} already records a Note\n{existing}')
        if 'skip:' in existing:
            raise SystemExit(f'refused: {path} marks this post skip\n{existing}')
        lines[start:end] = block
    open(path, 'w', encoding='utf-8').writelines(lines)


def normalize_note_url(u, handle):
    """Accept a full URL, `c-<id>`, or a bare id."""
    m = re.search(r'c-(\d+)', u) or re.fullmatch(r'(\d+)', u.strip())
    if not m:
        raise SystemExit(f'not a Note URL or id: {u!r}')
    return f'https://substack.com/@{handle}/note/c-{m.group(1)}'


# ------------------------------------------------------------------------ the feed
def fetch_notes(profile_id, max_pages=40):
    """Every Note on the profile, from the PUBLIC feed. -> list of {id, date, blob}."""
    notes, cursor = [], None
    for _ in range(max_pages):
        url = FEED.format(id=profile_id) + (f'&cursor={cursor}' if cursor else '')
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            j = json.load(r)
        for it in j.get('items', []):
            c = it.get('comment') or {}
            if c.get('id'):
                notes.append({'id': c['id'], 'date': c.get('date', ''),
                              'blob': json.dumps(c, ensure_ascii=False)})
        cursor = j.get('nextCursor')
        if not cursor:
            break
    return notes


def slug_of(public_url):
    return public_url.rstrip('/').rsplit('/p/', 1)[-1]


def match_notes(corpus, notes):
    """-> {piece slug: [note ids that name its post]}"""
    hits = {}
    for p in corpus:
        needle = f'/p/{slug_of(p["public_url"])}'
        ids = [n['id'] for n in notes
               if re.search(re.escape(needle) + r'(?![\w-])', n['blob'])]
        if ids:
            hits[p['slug']] = ids
    return hits


# ------------------------------------------------------------------------ config
def config(args):
    """Profile id and handle: flags, else the instance's outlets.yaml."""
    pid, handle = args.profile, args.handle
    path = args.outlets
    if (not pid or not handle) and path and os.path.exists(path):
        import yaml
        sub = (yaml.safe_load(open(path)) or {}).get('outlets', {}).get('substack', {})
        pid = pid or str(sub.get('notes_profile_id') or '')
        handle = handle or sub.get('notes_handle')
    return pid, handle


# ------------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('cmd', choices=['status', 'next', 'text', 'record', 'verify'])
    ap.add_argument('slugs', nargs='*')
    ap.add_argument('--pieces', default=default_pieces())
    ap.add_argument('--url', help='record: the Note URL (or c-<id>)')
    ap.add_argument('--date', help='record: YYYY-MM-DD (default today, local)')
    ap.add_argument('--today', help=argparse.SUPPRESS)           # for tests
    ap.add_argument('--outlets', default='publishing/outlets.yaml')
    ap.add_argument('--profile'); ap.add_argument('--handle')
    args = ap.parse_args(argv)

    today = args.today or datetime.date.today().isoformat()
    corpus = load(args.pieces)
    by = {p['slug']: p for p in corpus}

    def piece(slug):
        slug = os.path.basename(slug.rstrip('/'))
        if slug not in by:
            raise SystemExit(f'{slug}: not a live post (needs public_url + published_at, not a page)')
        return by[slug]

    if args.cmd == 'status':
        for p in corpus:
            extra = p['posted_at'] or p['skip']
            print(f"  {p['published_at']}  {p['state']:8}  {p['slug']:36} {extra}")
        bl = backlog(corpus)
        counts = {s: sum(p['state'] == s for p in corpus) for s in ('posted', 'drafted', 'missing', 'skip')}
        print(f"\n{len(corpus)} live posts: " + ', '.join(f'{v} {k}' for k, v in counts.items()))
        done = backlog_done_today(corpus, today)
        if done:
            print(f"today's backlog Note is out ({done['slug']}); next one tomorrow")
        elif bl:
            print(f"next backlog Note: {bl[0]['slug']} ({bl[0]['state']})")
        if bl:
            print(f"backlog clears {(datetime.date.fromisoformat(today) + datetime.timedelta(days=len(bl) - (0 if done else 1))).isoformat()} at one a day")
        return 0

    if args.cmd == 'next':
        done = backlog_done_today(corpus, today)
        if done:
            print(f"today's backlog Note is already out: {done['slug']} ({done['note_url']})")
            return 3
        bl = backlog(corpus)
        if not bl:
            print('backlog clear')
            return 0
        p = bl[0]
        print(json.dumps({'slug': p['slug'], 'title': p['title'], 'public_url': p['public_url'],
                          'published_at': p['published_at'], 'state': p['state'],
                          'remaining': len(bl)}, indent=2))
        return 0

    if args.cmd == 'text':
        if len(args.slugs) != 1:
            ap.error('text takes one slug')
        p = piece(args.slugs[0])
        paras, problems = read_note(p['dir'], p['public_url'])
        if problems:
            print(f"{p['slug']}: " + '; '.join(problems), file=sys.stderr)
            return 1
        print(json.dumps({'slug': p['slug'], 'title': p['title'], 'paragraphs': paras,
                          'sha256': note_hash(paras), 'js': composer_js(paras, p['title'])},
                         indent=2, ensure_ascii=False))
        return 0

    if args.cmd == 'record':
        if len(args.slugs) != 1:
            ap.error('record takes one slug')
        pid, handle = config(args)
        p = piece(args.slugs[0])
        if args.url:
            url = normalize_note_url(args.url, handle or 'unknown')
        else:
            # No URL given: take it from the PUBLIC feed, which is the evidence the Note
            # exists at all. Exactly one Note must name the post, or nothing is written.
            if not pid:
                ap.error('no --url and no profile id to read the feed with')
            try:
                found = match_notes([p], fetch_notes(pid)).get(p['slug'], [])
            except (urllib.error.URLError, OSError, ValueError) as e:
                print(f'could not read the notes feed: {e}', file=sys.stderr)
                return 2
            if len(found) != 1:
                print(f"{p['slug']}: the feed has {len(found)} Notes naming this post {found}; "
                      "pass --url to say which", file=sys.stderr)
                return 1
            url = normalize_note_url(str(found[0]), handle or 'unknown')
        date = args.date or today
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
            ap.error('--date is YYYY-MM-DD')
        record(p['dir'], date, url)
        kind = 'fresh' if date == p['published_at'] else 'backlog'
        print(f"recorded {p['slug']}: {url} ({date}, {kind})")
        return 0

    if args.cmd == 'verify':
        pid, _handle = config(args)
        if not pid:
            print('no profile id: pass --profile or set outlets.substack.notes_profile_id', file=sys.stderr)
            return 2
        try:
            notes = fetch_notes(pid)
        except (urllib.error.URLError, OSError, ValueError) as e:
            print(f'could not read the notes feed: {e}', file=sys.stderr)
            return 2
        hits = match_notes(corpus, notes)
        scope = [piece(s) for s in args.slugs] if args.slugs else corpus
        bad = 0
        for p in scope:
            found = hits.get(p['slug'], [])
            rec = re.search(r'c-(\d+)', p['note_url'] or '')
            if p['state'] == 'posted':
                if rec and int(rec.group(1)) in found:
                    print(f"  ok          {p['slug']}  c-{rec.group(1)}")
                else:
                    bad += 1
                    print(f"  MISSING     {p['slug']}  recorded {p['note_url']}, feed has {found or 'none'}")
                if len(found) > 1:
                    print(f"  DUPLICATE   {p['slug']}  {len(found)} Notes name this post: {found}")
            elif found:
                bad += 1
                print(f"  UNRECORDED  {p['slug']}  feed has {found}; run `record` with that id")
        print(f"\n{len(notes)} Notes on the profile; {sum(p['state'] == 'posted' for p in scope)} recorded in scope")
        return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
