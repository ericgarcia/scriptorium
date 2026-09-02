#!/usr/bin/env python3
"""test_concurrency.py — the multi-session guards, tested.  Run:

    python3 framework/tools/test_concurrency.py

SAFETY, on the same terms `test_suite.py` sets for itself:

  * DELETES NOTHING outside one `tempfile.TemporaryDirectory` the interpreter removes on exit.
    No `rm`, no path interpolated into a shell command.
  * NO NETWORK and NO BROWSER.  The one socket test binds 127.0.0.1 on an ephemeral port and
    closes it; it never serves and never fetches.
  * The real repository is READ ONLY here.  Every write goes to the temp instance.

It is a SEPARATE runner from `test_suite.py` on purpose and not out of preference: that file is
under active edit by another session as this is written, and adding to it would have been the
very collision these guards exist to prevent.  Fold it in when the desk is quiet.

Every case below is a failure that actually happened on 2026-09-02, or the precise inverse of
one — the ways a fix like this goes wrong are as instructive as the bugs.
"""
import os, sys, json, time, shutil, socket, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import session_port, lease, dashboard, check_refs        # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print('%s %s%s' % ('  ok  ' if cond else '  FAIL', name, ('   ' + detail) if detail and not cond else ''))


def make_instance(tmp):
    """A miniature desk: two pieces, a dashboard, a log that must be ignored."""
    root = os.path.join(tmp, 'desk')
    for slug, title in (('alpha', 'The Alpha Piece'), ('beta', 'Beta Rising')):
        d = os.path.join(root, 'pieces', slug)
        os.makedirs(os.path.join(d, 'log'))
        open(os.path.join(d, 'README.md'), 'w').write('# %s *(slug `%s`)*\n\nbody\n' % (title, slug))
        open(os.path.join(d, 'log', '2026-09.md'), 'w').write(
            '# log\n\n## alpha *(title **An Ancient Name**)*\nhistory, must be ignored\n')
    open(os.path.join(root, 'DASHBOARD.md'), 'w').write(
        '# Desk\n\npreamble text\n\n'
        '## alpha *(title **The Alpha Piece**)*\n**Stage:** one\n**Next:** do a thing\n\n'
        '## beta *(title **Beta Rising**)*\n**Stage:** two\n**Next:** do another\n\n'
        '## Books\nbooks section\n')
    return root


# ---------------------------------------------------------------- session_port
def test_ports():
    a = session_port.port_for()
    os.environ['DESK_SESSION_ID'] = 'session-A'
    pa, pa_fn = session_port.port_for(), session_port.port_for('fn')
    os.environ['DESK_SESSION_ID'] = 'session-B'
    pb = session_port.port_for()
    del os.environ['DESK_SESSION_ID']

    check('port: deterministic within a session', session_port.port_for() == a)
    check('port: two sessions differ', pa != pb, '%d == %d' % (pa, pb))
    check('port: sub-names differ within a session', pa != pa_fn)
    check('port: inside the allowed range',
          all(session_port.PORT_LO <= p < session_port.PORT_HI for p in (pa, pb, pa_fn)))

    # THE BUG: a taken port must raise, never silently fall back to a shared one.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    taken = s.getsockname()[1]
    s.listen(1)
    raised = False
    try:
        session_port.make_server(tempfile.gettempdir(), port=taken).server_close()
    except OSError:
        raised = True
    s.close()
    check('port: a taken port raises instead of falling back', raised)
    check('port: is_free agrees with reality', session_port.is_free(taken) is True)


def test_sha_gate():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, 'a.js')
        open(p, 'w').write('payload one')
        h1 = session_port.expected_sha256(p)
        open(p, 'w').write('payload two')
        check('sha: content change changes the hash', h1 != session_port.expected_sha256(p))
        check('sha: stable for identical bytes',
              session_port.expected_sha256(p) == session_port.expected_sha256(p))


# ---------------------------------------------------------------- lease
def test_lease():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_instance(tmp)
        os.environ['DESK_INSTANCE'] = root
        os.environ['DESK_SESSION_ID'] = 'sess-1'
        ok, _ = lease.acquire('alpha', 'drafting', root=root)
        check('lease: acquire on a free piece', ok)
        ok2, _ = lease.acquire('alpha', 'again', root=root)
        check('lease: re-acquire by the same session is fine', ok2)

        os.environ['DESK_SESSION_ID'] = 'sess-2'
        ok3, holder = lease.acquire('alpha', 'other work', root=root)
        check('lease: a second session is refused', not ok3)
        check('lease: refusal names the holder', holder and holder.get('session') == 'sess-1')
        ok4, _ = lease.acquire('beta', 'unrelated', root=root)
        check('lease: a different piece is unaffected', ok4)

        rel_ok, _ = lease.release('alpha', root=root)
        check('lease: cannot release another session\'s lease', not rel_ok)
        forced, rec = lease.acquire('alpha', 'taking over', root=root, force=True)
        check('lease: --force breaks it', forced)
        check('lease: the break is recorded, not silent',
              bool(rec.get('broke')) and rec['broke']['session'] == 'sess-1')
        check('lease: a live break is not mislabelled abandoned',
              rec['broke']['looked_abandoned'] is False)

        # THE CORRECTED MODEL.  "Abandoned" needs BOTH a dead process and real age.  A dead pid
        # alone means nothing, because every CLI-taken lease has a dead pid one millisecond
        # later — which is exactly what made the first design break live leases.
        p = os.path.join(root, '.desk', 'locks', 'beta.json')
        rec = json.load(open(p))
        rec['pid'] = 999999                       # dead process, but taken just now
        json.dump(rec, open(p, 'w'))
        check('lease: a dead pid ALONE is not abandoned (the CLI case)',
              lease.read('beta', root=root)['looks_abandoned'] is False)
        rec['acquired_at'] = int(time.time()) - int(lease.STALE_HINT_HOURS * 3600) - 60
        json.dump(rec, open(p, 'w'))
        check('lease: dead pid AND old reads as idle-looking',
              lease.read('beta', root=root)['looks_abandoned'] is True)
        rec['pid'] = os.getpid()                  # ancient, but the process is alive
        json.dump(rec, open(p, 'w'))
        check('lease: an old lease with a LIVE pid is never abandoned',
              lease.read('beta', root=root)['looks_abandoned'] is False)

        # REGRESSION (found by integration test, not by the unit tests above): every CLI call
        # is its own process, so the recorded pid dies immediately and EVERY lease looked stale.
        # The old code auto-broke on that and one session silently took another's lease.
        p2 = os.path.join(root, '.desk', 'locks', 'gamma.json')
        os.environ['DESK_SESSION_ID'] = 'sess-1'
        lease.acquire('gamma', 'held', root=root)
        rec = json.load(open(p2)); rec['pid'] = 999999; json.dump(rec, open(p2, 'w'))
        os.environ['DESK_SESSION_ID'] = 'sess-2'
        ok5, holder5 = lease.acquire('gamma', 'grab', root=root)
        check('lease: a DEAD-pid lease is still refused (no auto-break)', not ok5)
        check('lease: ...and the refusal still names the holder',
              holder5 and holder5.get('session') == 'sess-1')
        ok6, _ = lease.acquire('gamma', 'grab', root=root, force=True)
        check('lease: --force is the only way past it', ok6)

        # REGRESSION (found by DOGFOODING, after the other two were fixed): the identity
        # fallback was this process's pid, so `acquire` and `release` from two separate CLI
        # invocations disagreed about who "mine" was and nine leases wedged open. A pid is not
        # a session; the parent shell is. This asserts the identity is stable across calls that
        # share a parent, which is what every CLI invocation in one session does.
        os.environ.pop('DESK_SESSION_ID', None)
        first = lease.session_id()
        check('lease: identity is stable across invocations (not the pid)',
              first == lease.session_id() and str(os.getpid()) not in first,
              'got %r' % first)
        lease.acquire('delta', 'take', root=root)
        rel_ok2, _ = lease.release('delta', root=root)
        check('lease: a session can release what it acquired', rel_ok2)
        check('lease: ...and the file is gone',
              not os.path.isfile(os.path.join(root, '.desk', 'locks', 'delta.json')))
        os.environ['DESK_SESSION_ID'] = 'sess-2'

        check('lease: writes are atomic (no .tmp left behind)',
              not any(f.endswith('.tmp') for f in os.listdir(os.path.join(root, '.desk', 'locks'))))
        for v in ('DESK_INSTANCE', 'DESK_SESSION_ID'):
            os.environ.pop(v, None)


# ---------------------------------------------------------------- dashboard
def test_dashboard():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_instance(tmp)
        before = open(os.path.join(root, 'DASHBOARD.md')).read()

        check('dash: split succeeds', dashboard.do_split(root) == 0)
        frags = dashboard.fragments(root)
        check('dash: one fragment per block plus preamble', len(frags) == 4, str(frags))
        check('dash: fragments are named by slug',
              [s for _n, s, _p in frags] == ['preamble', 'alpha', 'beta', 'books'])
        check('dash: render round-trips byte for byte', dashboard.render_text(root) == before)
        check('dash: check passes on an untouched desk', dashboard.do_check(root) == 0)
        check('dash: split refuses to clobber existing fragments', dashboard.do_split(root) == 1)

        # TWO SESSIONS, TWO PIECES, ONE DASHBOARD — the case that lost data three times.
        a = [p for _n, s, p in dashboard.fragments(root) if s == 'alpha'][0]
        b = [p for _n, s, p in dashboard.fragments(root) if s == 'beta'][0]
        open(a, 'w').write('## alpha *(title **The Alpha Piece**)*\n**Stage:** EDITED BY SESSION 1\n')
        open(b, 'w').write('## beta *(title **Beta Rising**)*\n**Stage:** EDITED BY SESSION 2\n')
        dashboard.do_render(root, quiet=True)
        out = open(os.path.join(root, 'DASHBOARD.md')).read()
        check('dash: BOTH concurrent edits survive',
              'EDITED BY SESSION 1' in out and 'EDITED BY SESSION 2' in out)
        check('dash: untouched blocks are preserved', 'books section' in out and 'preamble text' in out)

        # A session that has not learned the new layout edits DASHBOARD.md directly.
        # A blind render would eat that; sync must not.
        live = open(os.path.join(root, 'DASHBOARD.md')).read().replace(
            '**Stage:** EDITED BY SESSION 1', '**Stage:** HAND EDIT IN THE GENERATED FILE')
        open(os.path.join(root, 'DASHBOARD.md'), 'w').write(live)
        check('dash: check DETECTS the hand edit', dashboard.do_check(root) == 1)
        dashboard.do_ingest(root, quiet=True)
        check('dash: ingest pulls the hand edit into the fragment',
              'HAND EDIT IN THE GENERATED FILE' in open(a).read())
        dashboard.do_render(root, quiet=True)
        check('dash: sync preserves it end to end',
              'HAND EDIT IN THE GENERATED FILE' in open(os.path.join(root, 'DASHBOARD.md')).read())
        check('dash: check passes again after sync', dashboard.do_check(root) == 0)

        # REGRESSION (found by integration test): the DOCUMENTED workflow is edit-fragment-then-
        # sync.  The first ingest assumed DASHBOARD.md was always newer and reverted the fragment
        # from the older generated file — destroying the very edit it had just told you to make.
        import time as _t
        dash = os.path.join(root, 'DASHBOARD.md')
        os.utime(dash, (1_600_000_000, 1_600_000_000))          # dashboard is OLD
        open(a, 'w').write('## alpha *(title **The Alpha Piece**)*\n**Stage:** FRAGMENT IS NEWER\n')
        _t.sleep(0.01)
        dashboard.do_ingest(root, quiet=True)
        check('dash: a fragment newer than DASHBOARD.md is NOT reverted',
              'FRAGMENT IS NEWER' in open(a).read())
        dashboard.do_render(root, quiet=True)
        check('dash: ...and reaches the generated file',
              'FRAGMENT IS NEWER' in open(dash).read())

        # ...and the other direction still works: dashboard newer => the hand edit is pulled down.
        _t.sleep(0.01)
        live2 = open(dash).read().replace('**Stage:** FRAGMENT IS NEWER',
                                          '**Stage:** DASHBOARD IS NEWER')
        open(dash, 'w').write(live2)
        dashboard.do_ingest(root, quiet=True)
        check('dash: a DASHBOARD.md newer than the fragment IS ingested',
              'DASHBOARD IS NEWER' in open(a).read())

        # A wholly new piece appears only in the generated file.
        live = open(os.path.join(root, 'DASHBOARD.md')).read().replace(
            '## Books', '## gamma *(title **Gamma**)*\n**Stage:** brand new\n\n## Books')
        open(os.path.join(root, 'DASHBOARD.md'), 'w').write(live)
        dashboard.do_ingest(root, quiet=True)
        check('dash: a new block becomes a new fragment',
              'gamma' in [s for _n, s, _p in dashboard.fragments(root)])

        # An orphan fragment must never be deleted on a guess.
        open(os.path.join(root, DASHBOARD_D(root), '900-ghost.md'), 'w').write('## ghost\nx\n')
        dashboard.do_ingest(root, quiet=True)
        check('dash: an orphan fragment is KEPT, not deleted',
              os.path.isfile(os.path.join(DASHBOARD_D(root), '900-ghost.md')))

        check('dash: no .tmp files left behind',
              not any(f.endswith('.tmp') or '.tmp' in f for f in os.listdir(DASHBOARD_D(root))))


def DASHBOARD_D(root):
    return os.path.join(root, dashboard.FRAGDIR)


def test_slug_of():
    cases = [('## hearing-firsthand *(title **Secondhand**)*', 'hearing-firsthand'),
             ('## darkness-and-light *(working title **The Kingdom That Isn\'t**)*', 'darkness-and-light'),
             ('## flow *(was `us`)*', 'flow'),
             ('## the-opposite-of-love-is-cynicism', 'the-opposite-of-love-is-cynicism'),
             ('## Books', 'books')]
    for head, want in cases:
        got = dashboard.slug_of(head)
        check('slug_of: %s' % want, got == want, 'got %r' % got)


# ---------------------------------------------------------------- check_refs
def test_check_refs():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_instance(tmp)
        check('refs: a consistent desk passes', check_refs.main([None, root]) == 0)

        # THE BUG: a piece is retitled; another file still names the old title.
        open(os.path.join(root, 'pieces', 'alpha', 'README.md'), 'w').write(
            '# The Alpha Piece Renamed *(slug `alpha`)*\n\nbody\n')
        check('refs: a stale title is caught', check_refs.main([None, root]) == 1)

        # ...and the append-only log naming the old title is NOT an error.
        open(os.path.join(root, 'pieces', 'alpha', 'README.md'), 'w').write(
            '# An Ancient Name *(slug `alpha`)*\n\nbody\n')
        open(os.path.join(root, 'DASHBOARD.md'), 'w').write(
            '# Desk\n\n## alpha *(title **An Ancient Name**)*\nx\n\n'
            '## beta *(title **Beta Rising**)*\ny\n')
        rc = check_refs.main([None, root])
        check('refs: append-only logs are exempt', rc == 0)

        # A supersession note is the correct use of an old title.
        open(os.path.join(root, 'pieces', 'beta', 'notes.md'), 'w').write(
            'Retired: the working title *Beta Falling*.\n')
        check('refs: a marked supersession is not flagged', check_refs.main([None, root]) == 0)

        # A reference to a piece that does not exist.
        open(os.path.join(root, 'pieces', 'beta', 'notes.md'), 'w').write(
            'see [The Ghost Piece](../ghost/README.md)\n')
        check('refs: a reference to a missing piece is caught', check_refs.main([None, root]) == 1)


def test_h1_title():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, 'R.md')
        for text, want in (('# Secondhand *(slug `x`)*\n', 'Secondhand'),
                           ('# In the Name (The Ambassador) *(was "The Name")*\n',
                            'In the Name (The Ambassador)'),
                           ('# Plain Title\n', 'Plain Title')):
            open(p, 'w').write(text)
            got = check_refs.h1_title(p)
            check('h1: %s' % want, got == want, 'got %r' % got)


def main():
    print('session_port'); test_ports(); test_sha_gate()
    print('lease');        test_lease()
    print('dashboard');    test_slug_of(); test_dashboard()
    print('check_refs');   test_h1_title(); test_check_refs()
    print('\n%d passed, %d failed' % (len(PASS), len(FAIL)))
    if FAIL:
        print('failing: ' + ', '.join(FAIL))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
