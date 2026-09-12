#!/usr/bin/env python3
"""
schedule.py — a piece can be finished and still not be due yet.

A piece is sealed on one day and meant to go live on another. Between those two days
there is nothing in the desk that knows the difference, and every tool that publishes
will happily publish. This is the thing that knows: one field in the manifest, one
moment, and a refusal before it.

  publish_at: 2026-09-15 09:00 America/New_York

Read it with `state()`, or from the command line:

  python3 tools/schedule.py check <piece>...     exit 4 while a piece is embargoed
  python3 tools/schedule.py list                 every piece that carries the field
  python3 tools/schedule.py due [--within 48h]   what opens inside the window (or has)
  python3 tools/schedule.py set <piece> "<moment>"
  python3 tools/schedule.py clear <piece>
  python3 tools/schedule.py runbook <piece>      the prompt a scheduled wake-up needs
  python3 tools/schedule.py arm <piece> --task … --does … --reviewed "<who, when>"
  python3 tools/schedule.py armed                what is armed across the desk

THE ORDER IS NOT NEGOTIABLE: compose the drafts, let the author read them, THEN arm. A
scheduled publication fires with nobody watching, so the reading has to have happened
first (Eric, 2026-09-11: "we don't set the schedule until the drafts are reviewed and
approved"). `arm` refuses without `--reviewed`, and records who approved it.

WHAT IT GATES, AND WHAT IT DELIBERATELY DOES NOT.

  REFUSES   Anything that makes the piece public or queues it to become public:
            `md_to_site.py` will not export an embargoed piece into the store bundle
            (exit 12), which is what a site reads.

  WARNS     Composing. A Substack draft is private and a LinkedIn file is a file on
            this Mac; composing early is how a scheduled publication is prepared at
            all, so `md_to_substack.py` and `md_to_linkedin.py` print the embargo and
            carry on. The `publish` skill reads this tool before it clicks anything.

  KNOWS     Nothing about clocks. It compares a moment to now, and the refusal is the
            whole mechanism. Nothing here fires on its own, on purpose: an unattended
            publish is a decision the author makes explicitly elsewhere (for Substack,
            its own scheduler, set in the composer once the draft is ready).

WHY A TIMEZONE IS REQUIRED. "2026-09-15" is not a moment, it is a date in whatever zone
the reader happens to be in, and an embargo that opens at a different instant depending
on who asks is not an embargo. A moment with no zone is refused (exit 2) rather than
assumed. Write the zone you mean: `America/New_York` reads correctly across a DST
boundary, where a fixed `-04:00` quietly does not.

Exit codes: 0 open (or no field) · 1 usage · 2 a malformed or zoneless moment ·
4 at least one piece is still embargoed.
"""

import argparse
import os
import re
import sys
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:                                            # pragma: no cover
    ZoneInfo = None

HERE = os.path.dirname(os.path.abspath(__file__))
FIELD = 'publish_at'

# `2026-09-15 09:00 America/New_York`, `2026-09-15T09:00:00-04:00`, `2026-09-15 09:00 UTC`.
_MOMENT = re.compile(
    r'^(?P<date>\d{4}-\d{2}-\d{2})'
    r'(?:[ T](?P<time>\d{2}:\d{2}(?::\d{2})?))?'
    r'(?:\s*(?P<zone>Z|UTC|[A-Za-z]+/[A-Za-z_+\-]+|[+-]\d{2}:?\d{2}))?$')


class Malformed(ValueError):
    """The moment cannot be read, or carries no zone."""


def parse_moment(raw):
    """'2026-09-15 09:00 America/New_York' -> an aware datetime. Raises Malformed."""
    s = str(raw).strip().strip('"\'')
    s = s.split('#', 1)[0].strip()
    m = _MOMENT.match(s)
    if not m:
        raise Malformed(f'cannot read {raw!r} as a moment — '
                        f'write it as `2026-09-15 09:00 America/New_York`')
    zone = m.group('zone')
    if not zone:
        raise Malformed(f'{raw!r} names no timezone, so it is a date and not a moment — '
                        f'write it as `{m.group("date")} '
                        f'{m.group("time") or "09:00"} America/New_York`')
    time = m.group('time') or '00:00'
    if len(time) == 5:
        time += ':00'
    naive = datetime.fromisoformat(f'{m.group("date")}T{time}')

    if zone in ('Z', 'UTC'):
        return naive.replace(tzinfo=timezone.utc)
    if zone[0] in '+-':
        zone = zone if ':' in zone else f'{zone[:3]}:{zone[3:]}'
        hh, mm = int(zone[1:3]), int(zone[4:6])
        off = timedelta(hours=hh, minutes=mm)
        return naive.replace(tzinfo=timezone(-off if zone[0] == '-' else off))
    if ZoneInfo is None:
        raise Malformed('this Python has no zoneinfo; write a numeric offset instead')
    try:
        return naive.replace(tzinfo=ZoneInfo(zone))
    except Exception:
        raise Malformed(f'{zone!r} is not a timezone this machine knows')


def read_field(piece_dir):
    """The raw `publish_at:` line from a manifest, or None. Deliberately a line-reader
    rather than a YAML load: this runs inside tools that parse the manifest their own
    way, and one field should not drag a parser in behind it."""
    path = os.path.join(piece_dir, 'publish.yaml')
    if not os.path.exists(path):
        return None
    for line in open(path, encoding='utf-8'):
        if line.startswith(f'{FIELD}:'):
            value = line.split(':', 1)[1]
            value = value.split('#', 1)[0].strip()
            return value or None
    return None


def state(piece_dir, now=None):
    """('none'|'open'|'embargoed', moment_or_None). Raises Malformed on a bad field."""
    raw = read_field(piece_dir)
    if raw is None:
        return 'none', None
    moment = parse_moment(raw)
    now = now or datetime.now(timezone.utc)
    return ('open' if now >= moment else 'embargoed'), moment


def refuse_if_embargoed(piece_dir, now=None):
    """For a caller that publishes. Returns a refusal string, or None to proceed."""
    try:
        st, moment = state(piece_dir, now)
    except Malformed as e:
        return f'{os.path.basename(piece_dir.rstrip("/"))}: {FIELD} is unusable — {e}'
    if st != 'embargoed':
        return None
    return (f'{os.path.basename(piece_dir.rstrip("/"))} is embargoed until '
            f'{fmt(moment)} ({human_delta(moment, now)}). '
            f'Publishing it now is the one thing the field exists to prevent; '
            f'clear or move it with `schedule.py set` if the date really changed.')


def fmt(moment):
    return moment.strftime('%Y-%m-%d %H:%M %Z').strip()


def human_delta(moment, now=None):
    now = now or datetime.now(timezone.utc)
    secs = (moment - now).total_seconds()
    past = secs < 0
    secs = abs(secs)
    if secs < 3600:
        said = f'{int(secs // 60)}m'
    elif secs < 86400:
        said = f'{int(secs // 3600)}h {int(secs % 3600 // 60)}m'
    else:
        said = f'{int(secs // 86400)}d {int(secs % 86400 // 3600)}h'
    return f'{said} ago' if past else f'in {said}'


# --------------------------------------------------------------------------- CLI


def pieces_root(start=None):
    d = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(d, 'pieces')):
            return os.path.join(d, 'pieces')
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def resolve(ref):
    if os.path.isdir(ref):
        return os.path.abspath(ref)
    import corpus
    found = corpus.find(corpus.desk_root(), ref)
    if found:
        return found
    sys.exit(f'no such piece: {ref}')


def all_pieces():
    import corpus
    return [d for _s, d, _k in corpus.texts(corpus.desk_root())]


def parse_window(s):
    m = re.match(r'^(\d+)\s*([hd])$', s.strip(), re.I)
    if not m:
        sys.exit(f'--within wants something like 48h or 7d, not {s!r}')
    n = int(m.group(1))
    return timedelta(hours=n) if m.group(2).lower() == 'h' else timedelta(days=n)


def cmd_check(args):
    bad = 0
    for ref in args.pieces:
        pdir = resolve(ref)
        refusal = refuse_if_embargoed(pdir)
        if refusal:
            print(f'EMBARGOED  {refusal}')
            bad += 1
        else:
            st, moment = state(pdir)
            print(f'open       {os.path.basename(pdir)}'
                  + (f' — opened {fmt(moment)} ({human_delta(moment)})' if moment else
                     f' — no {FIELD}'))
    return 4 if bad else 0


def cmd_list(args):
    rows, bad = [], 0
    for pdir in all_pieces():
        raw = read_field(pdir)
        if raw is None:
            continue
        try:
            st, moment = state(pdir)
            rows.append((st.upper(), os.path.basename(pdir), fmt(moment),
                         human_delta(moment)))
            bad += st == 'embargoed'
        except Malformed as e:
            rows.append(('MALFORMED', os.path.basename(pdir), raw, str(e)))
            bad += 1
    if not rows:
        print(f'no piece carries {FIELD}')
        return 0
    w = max(len(r[1]) for r in rows)
    for st, slug, moment, note in sorted(rows, key=lambda r: r[2]):
        print(f'{st:10} {slug:{w}}  {moment}  ({note})')
    return 4 if any(r[0] == 'EMBARGOED' for r in rows) else 0


def cmd_due(args):
    window = parse_window(args.within)
    now = datetime.now(timezone.utc)
    found = 0
    for pdir in all_pieces():
        if read_field(pdir) is None:
            continue
        try:
            st, moment = state(pdir, now)
        except Malformed:
            continue
        if moment <= now + window:
            found += 1
            print(f'{"OPEN" if st == "open" else "opens"}  {os.path.basename(pdir)}  '
                  f'{fmt(moment)} ({human_delta(moment, now)})')
    if not found:
        print(f'nothing due within {args.within}')
    return 0


RUNBOOK = """\
Publication day for {slug} — "{title}".

You are a fresh session with no memory of how this was arranged. Everything you need is here
and in the piece; read pieces/{slug}/README.md first, and do not improvise past this list.

The desk is {root}. The moment is {moment}; `python3 framework/tools/schedule.py check {slug}`
must say OPEN before anything public happens. If it says EMBARGOED, stop: you woke early.

IF YOU ARE RUNNING LATE — the app was closed and this fired at launch instead of on time — say
so in your first line, then check what already went out before you touch anything: the Substack
post and the LinkedIn article are on their own platforms' schedulers and may already be live.

1. `python3 framework/tools/lease.py acquire {slug} --what "publication day"`.
2. Gates: `schedule.py check`, `check_verified.py`, `check_links.py`, `check_refs.py` — any
   refusal stops the run and is reported, not worked around.
3. The canonical goes first. Cutover steps 1-3 in the README: copy original_published_at to
   published_at, record blog_url and canonical, export the bundle, publish it to the store, then
   remove {slug} from TAKEN_DOWN_FOR_REDRAFT in muffinlabs-web/next.config.ts and deploy — a
   config redirect beats the page route, so the piece cannot appear at its URL until that lands.
4. Verify the live page yourself before saying it is up, on a cache-busted URL.
5. Substack and LinkedIn publish on their own schedulers. Confirm rather than assume: if the
   Substack post is not live within ten minutes of the moment, say so and stop — do NOT click
   Publish yourself, because that decision was made against a draft the author reviewed and
   whatever went wrong needs a human.
6. LinkedIn's Article copy links the canonical, so it is composed only after step 4 passes. If it
   is still a draft, leave it and say so.
7. Record it: post_url / blog_url / linkedin_url in publish.yaml, README and the dashboard
   fragment to published, an append-only log entry, `dashboard.py sync`, release the lease, and
   commit by path (never `git add` then a bare commit).
8. Notify the author with: what is live, what is not, and what is left for them (the Note is
   always theirs — never post it).
"""


def cmd_runbook(args):
    """Print the self-contained prompt for the scheduled wake-up.

    A scheduled task starts with no memory of the conversation that created it, so the prompt
    has to carry the piece, the moment, the order and the gates. It is generated from the
    manifest rather than typed, so moving `publish_at` cannot leave a stale moment inside a
    prompt nobody re-reads."""
    pdir = resolve(args.piece)
    st, moment = state(pdir)
    if not moment:
        sys.exit(f'{os.path.basename(pdir)} has no {FIELD} — nothing to arm')
    title = ''
    for line in open(os.path.join(pdir, 'publish.yaml'), encoding='utf-8'):
        if line.startswith('title:'):
            title = line.split(':', 1)[1].strip().strip('"\'')
            break
    print(RUNBOOK.format(slug=os.path.basename(pdir), title=title, moment=fmt(moment),
                         root=os.path.dirname(os.path.dirname(os.path.abspath(pdir)))))
    return 0


def cmd_arm(args):
    """Record that a wake-up has been scheduled for this piece, and by what.

    The task itself is created by the session (the scheduler lives in the app, not in this
    tool). What this writes is the desk's record of it, so `armed` can answer the question
    a week later and a moved moment shows up as a contradiction rather than a surprise.

    `--reviewed` is required, and it is the rule rather than a formality: **the schedule is
    not set until the drafts are reviewed and approved** (Eric, 2026-09-11). A scheduled
    publication fires with nobody watching, so the reading has to have happened first — and
    the composing is what produces the thing to read, which puts it before the arming and
    never after. Naming who approved it makes the order auditable in the manifest."""
    pdir = resolve(args.piece)
    st, moment = state(pdir)
    if not moment:
        sys.exit(f'{os.path.basename(pdir)} has no {FIELD} — set one before arming')
    if not args.reviewed:
        sys.exit('refusing to arm: --reviewed is required.\n'
                 '  The schedule is not set until the drafts are reviewed and approved, because\n'
                 '  a scheduled publication fires with nobody watching. Compose the drafts, let\n'
                 '  the author read them, then arm with --reviewed "<who, when>".')
    path = os.path.join(pdir, 'publish.yaml')
    src = open(path, encoding='utf-8').read()
    block = (f'# A scheduled wake-up is armed for this piece. The moment of record is {FIELD};\n'
             f'# this block is only the note that something was told to fire near it. Armed only\n'
             f'# after the drafts were read and approved — see `approved`.\n'
             f'scheduled:\n'
             f'  task: {args.task}\n'
             f'  fires: {args.fires or fmt(moment)}\n'
             f'  does: {args.does}\n'
             f'  approved: {args.reviewed}\n')
    src = re.sub(r'(?ms)^# A scheduled wake-up.*?^  does: .*?$\n', '', src)
    src = src.rstrip('\n') + '\n\n' + block
    open(path, 'w', encoding='utf-8').write(src)
    print(f'{os.path.basename(pdir)}: armed — {args.task} fires {args.fires or fmt(moment)}')
    return 0


def cmd_armed(args):
    rows = []
    for pdir in all_pieces():
        p = os.path.join(pdir, 'publish.yaml')
        if not os.path.exists(p):
            continue
        src = open(p, encoding='utf-8').read()
        m = re.search(r'(?ms)^scheduled:\n  task: (.+?)\n  fires: (.+?)\n  does: (.+?)$', src)
        if m:
            rows.append((os.path.basename(pdir), m.group(1), m.group(2), m.group(3)))
    if not rows:
        print('nothing armed')
        return 0
    w = max(len(r[0]) for r in rows)
    for slug, task, fires, does in rows:
        print(f'{slug:{w}}  {task}  fires {fires}  — {does}')
    return 0


def cmd_set(args):
    pdir = resolve(args.piece)
    moment = parse_moment(args.moment)                      # refuse before writing
    path = os.path.join(pdir, 'publish.yaml')
    lines = open(path, encoding='utf-8').read().split('\n')
    line = f'{FIELD}: {args.moment.strip()}'
    for i, ln in enumerate(lines):
        if ln.startswith(f'{FIELD}:'):
            lines[i] = line
            break
    else:
        note = ('# Not due yet. Nothing may be made public before this moment; '
                'schedule.py is the gate.')
        for i, ln in enumerate(lines):
            if ln.startswith('publication:'):
                lines[i:i] = [note, line]
                break
        else:
            lines.insert(1, note)
            lines.insert(2, line)
    open(path, 'w', encoding='utf-8').write('\n'.join(lines))
    print(f'{os.path.basename(pdir)}: {FIELD} = {fmt(moment)} ({human_delta(moment)})')
    return 0


def cmd_clear(args):
    pdir = resolve(args.piece)
    path = os.path.join(pdir, 'publish.yaml')
    lines = open(path, encoding='utf-8').read().split('\n')
    kept = [ln for ln in lines if not ln.startswith(f'{FIELD}:')]
    if len(kept) == len(lines):
        print(f'{os.path.basename(pdir)}: no {FIELD} to clear')
        return 0
    open(path, 'w', encoding='utf-8').write('\n'.join(kept))
    print(f'{os.path.basename(pdir)}: {FIELD} cleared — nothing gates this piece now')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    c = sub.add_parser('check', help='exit 4 while any named piece is embargoed')
    c.add_argument('pieces', nargs='+')
    c.set_defaults(fn=cmd_check)

    c = sub.add_parser('list', help='every piece carrying the field')
    c.set_defaults(fn=cmd_list)

    c = sub.add_parser('due', help='what opens inside a window')
    c.add_argument('--within', default='48h')
    c.set_defaults(fn=cmd_due)

    c = sub.add_parser('runbook', help='the self-contained prompt for a scheduled wake-up')
    c.add_argument('piece')
    c.set_defaults(fn=cmd_runbook)

    c = sub.add_parser('arm', help='record that a wake-up is scheduled (after the drafts are approved)')
    c.add_argument('piece')
    c.add_argument('--task', required=True, help='the scheduler\'s id for it')
    c.add_argument('--does', required=True, help='one line: what it will do when it fires')
    c.add_argument('--fires', help='when, if not the publish_at moment itself')
    c.add_argument('--reviewed', help='who approved the drafts, and when — REQUIRED')
    c.set_defaults(fn=cmd_arm)

    c = sub.add_parser('armed', help='what is armed across the desk')
    c.set_defaults(fn=cmd_armed)

    c = sub.add_parser('set', help='write the field')
    c.add_argument('piece')
    c.add_argument('moment')
    c.set_defaults(fn=cmd_set)

    c = sub.add_parser('clear', help='remove the field')
    c.add_argument('piece')
    c.set_defaults(fn=cmd_clear)

    args = ap.parse_args()
    try:
        return args.fn(args)
    except Malformed as e:
        print(f'refusing: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
