#!/usr/bin/env python3
"""lease.py — advisory, per-piece leases so concurrent sessions collide LOUDLY.

WHY (2026-09-02).  Six interactive sessions were running against one writing desk at the same
time.  Three of them wrote the same aggregate file and the last writer silently won, three
times in a row.  One retitled a piece while another was mid-draft, so cross-references went
stale inside minutes.  None of that was detected by anything; it was noticed, twice, by luck.

WHAT THIS IS, EXACTLY.  An ADVISORY lease.  It cannot stop anybody — nothing here holds a file
open or takes an OS lock — and pretending otherwise would be worse than not having it, because
a lock people trust and that does not hold is how you get bolder about racing.  What it buys is
the one thing conventions cannot: a session that is about to touch a piece can find out, in one
call, that somebody else already is, AND WHO.  Silent races become loud ones.

DESIGN NOTES, each of which is a mistake not to repeat:

  * STALENESS IS A HINT, AND NEVER AN ACTION.  An earlier version auto-broke any lease whose
    recorded pid was gone.  Integration testing killed that design in one line: every CLI call
    is its own short-lived process, so the pid it records is dead the instant the command
    returns, and EVERY lease read as stale immediately.  One session then silently took another
    session's lease — the tool committing, inside itself, the exact silent clobber it exists to
    prevent.  So `acquire` now REFUSES any lease it does not own, however abandoned it looks,
    and staleness is printed as guidance for a human deciding whether to `--force`.  A lock that
    breaks itself on a guess is not a lock.

  * THE HINT USES BOTH SIGNALS, and neither alone.  A live pid on this host means held for
    certain.  Otherwise age is all there is — reported, not acted on — because a CLI-taken lease
    has no process to point at and a long draft is normal work, not an abandonment.

  * BREAKING IS EXPLICIT AND RECORDED.  `--force` writes who broke what and when into the new
    lease.  A break that leaves no trace is indistinguishable from a lease that was never taken.

  * WRITES ARE ATOMIC.  Temp file in the same directory, then `os.replace`.  A lease file that
    can be observed half-written is a lease file that will be, with six sessions running.

  * THE LEASE DIRECTORY IS MACHINE-LOCAL AND NOT COMMITTED.  A lease describes a process on one
    computer; committing one would ship a lie to every other checkout.
"""
import json, os, sys, time, socket, errno

LEASE_DIRNAME = os.path.join('.desk', 'locks')


def instance_root(start=None):
    """Walk up to the desk root — the directory that holds `pieces/`."""
    cur = os.path.abspath(start or os.environ.get('DESK_INSTANCE') or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(cur, 'pieces')):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())
        cur = parent


def lease_dir(root=None):
    d = os.path.join(instance_root(root), LEASE_DIRNAME)
    os.makedirs(d, exist_ok=True)
    return d


def _path(slug, root=None):
    return os.path.join(lease_dir(root), '%s.json' % slug)


def session_id():
    """Who holds a lease.  MUST be stable across separate CLI invocations.

    THE BUG THIS FIXES, and it is the third one in this file from a single confusion.  The
    fallback used to be this process's own pid.  Every `lease.py` call is its own process, so
    `acquire` and `release` reported different identities and a session could not release the
    lease it had just taken — nine of them wedged in one sweep.  Earlier the same confusion made
    every lease look stale, and before that let one session silently take another's.

    A PID IS NOT A SESSION.  The parent is: every command a session runs comes from the same
    shell, so PPID is stable across invocations and still distinct between sessions.  An explicit
    env var beats it whenever the harness provides one.
    """
    for var in ('CLAUDE_SESSION_ID', 'DESK_SESSION_ID'):
        v = os.environ.get(var)
        if v:
            return v
    return 'shell%d' % os.getppid()


def pid_alive(pid):
    """True if the pid exists. Signal 0 checks existence without touching the process.

    EPERM means it exists and belongs to somebody else — which is still ALIVE.  Reading EPERM
    as 'gone' would break a lease that is actively held, so the two errno cases are separated
    deliberately rather than collapsed into a bare `except`.
    """
    if pid is None:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError as e:
        return e.errno == errno.EPERM
    except (TypeError, ValueError):
        return False


STALE_HINT_HOURS = 4


def read(slug, root=None):
    try:
        with open(_path(slug, root)) as fh:
            rec = json.load(fh)
    except (OSError, ValueError):
        return None
    rec['mine'] = rec.get('session') == session_id()
    live = rec.get('host') == socket.gethostname() and pid_alive(rec.get('pid'))
    age_h = (time.time() - int(rec.get('acquired_at') or 0)) / 3600.0
    rec['live_process'] = bool(live)
    rec['age_hours'] = round(age_h, 2)
    # A HINT for a human, never a trigger. See the module docstring.
    rec['looks_abandoned'] = (not live) and age_h > STALE_HINT_HOURS
    rec['stale'] = rec['looks_abandoned']
    return rec


def _write(slug, rec, root=None):
    path = _path(slug, root)
    tmp = '%s.tmp%d' % (path, os.getpid())
    with open(tmp, 'w') as fh:
        json.dump(rec, fh, indent=2, sort_keys=True)
        fh.write('\n')
    os.replace(tmp, path)      # atomic within a filesystem
    return path


def acquire(slug, what='', root=None, force=False):
    """Take the lease.  Returns (ok, record).  Never raises on contention."""
    cur = read(slug, root)
    if cur and not cur['mine'] and not force:
        return False, cur          # never auto-break: staleness is a hint, not a licence
    rec = {'slug': slug, 'session': session_id(), 'pid': os.getpid(),
           'host': socket.gethostname(), 'what': what,
           'acquired': time.strftime('%Y-%m-%dT%H:%M:%S'), 'acquired_at': int(time.time())}
    if cur and not cur['mine']:
        rec['broke'] = {'session': cur.get('session'), 'pid': cur.get('pid'),
                        'what': cur.get('what'), 'acquired': cur.get('acquired'),
                        'looked_abandoned': cur['looks_abandoned'],
                        'age_hours': cur['age_hours']}
    _write(slug, rec, root)
    return True, rec


def release(slug, root=None, force=False):
    cur = read(slug, root)
    if not cur:
        return True, None
    if not cur['mine'] and not force:
        return False, cur
    try:
        os.unlink(_path(slug, root))
    except OSError:
        pass
    return True, cur


def held(root=None):
    out = []
    d = lease_dir(root)
    for fn in sorted(os.listdir(d)):
        if fn.endswith('.json'):
            rec = read(fn[:-5], root)
            if rec:
                out.append(rec)
    return out


def _fmt(rec):
    age = int(time.time()) - int(rec.get('acquired_at') or 0)
    tag = 'mine ' if rec['mine'] else ('idle?' if rec['looks_abandoned'] else 'HELD ')
    return '  %s %-28s %s  pid %-7s %4dm  %s' % (
        tag, rec['slug'], (rec.get('session') or '?')[:12], rec.get('pid'),
        age // 60, rec.get('what') or '')


USAGE = ("usage: lease.py acquire SLUG [--what TEXT] [--force]\n"
         "       lease.py release SLUG [--force]\n"
         "       lease.py check SLUG          # exit 0 free/mine, 3 held by another\n"
         "       lease.py list [--prune]")


def main(argv):
    if len(argv) < 2 or argv[1] in ('-h', '--help'):
        print(__doc__)
        print(USAGE)
        return 0
    cmd = argv[1]
    force = '--force' in argv
    what = ''
    if '--what' in argv:
        i = argv.index('--what')
        if i + 1 < len(argv):
            what = argv[i + 1]

    if cmd == 'list':
        rows = held()
        if '--prune' in argv:
            for r in rows:
                if r['looks_abandoned']:      # explicit human action, never automatic
                    os.unlink(_path(r['slug']))
            rows = held()
        if not rows:
            print('no leases held')
            return 0
        print('leases (%s):' % instance_root())
        for r in rows:
            print(_fmt(r))
        return 0

    if len(argv) < 3:
        sys.stderr.write(USAGE + '\n')
        return 2
    slug = argv[2]

    if cmd == 'check':
        rec = read(slug)
        if not rec or rec['mine']:
            print('free' if not rec else 'mine')
            return 0
        print('HELD by %s (pid %s) since %s — %s' %
              (rec.get('session'), rec.get('pid'), rec.get('acquired'), rec.get('what') or 'no note'))
        return 3

    if cmd == 'acquire':
        ok, rec = acquire(slug, what, force=force)
        if ok:
            note = ''
            if rec.get('broke'):
                note = '  (BROKE the %s lease held by %s, %.1fh old)' % (
                    'idle-looking' if rec['broke']['looked_abandoned'] else 'active',
                    rec['broke']['session'], rec['broke']['age_hours'])
            print('acquired %s%s' % (slug, note))
            return 0
        sys.stderr.write(
            'lease: %s is HELD by %s since %s (%.1fh) — %s\n'
            '%s'
            'This is advisory: nothing stops you. But another session claimed that piece, and the\n'
            'last writer wins silently. Coordinate, or --force (the break is recorded).\n'
            % (slug, rec.get('session'), rec.get('acquired'), rec['age_hours'],
               rec.get('what') or 'no note',
               '  It looks idle (no live process, older than %dh) — but that is a guess, not a\n'
               '  fact: a lease taken from the command line has no process left to point at.\n'
               % STALE_HINT_HOURS if rec['looks_abandoned'] else ''))
        return 3

    if cmd == 'release':
        ok, rec = release(slug, force=force)
        if not ok:
            sys.stderr.write('lease: %s is held by %s, not by this session; --force to release\n'
                             % (slug, rec.get('session')))
            return 3
        print('released %s' % slug if rec else 'no lease on %s' % slug)
        return 0

    sys.stderr.write('lease: unknown command %r\n%s\n' % (cmd, USAGE))
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
