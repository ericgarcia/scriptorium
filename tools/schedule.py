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
    root = pieces_root()
    cand = os.path.join(root, ref) if root else None
    if cand and os.path.isdir(cand):
        return cand
    sys.exit(f'no such piece: {ref}')


def all_pieces():
    root = pieces_root()
    if not root:
        return []
    return sorted(os.path.join(root, d) for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)))


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
