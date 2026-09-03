#!/usr/bin/env python3
"""session_port.py — a localhost port that belongs to THIS session, and a server that
fails loudly when it does not get one.

WHY THIS EXISTS (2026-09-02, and it is not hypothetical).  A compose pass served a footnote
snippet over `http://127.0.0.1:8791` for the browser to fetch and eval.  Another session on the
same machine already held that port.  The bind failed, `nohup` swallowed the error, and the page
fetched THE OTHER SESSION'S snippet — thirty-five footnotes belonging to a different essay — and
evaluated it against the wrong post.  Nothing applied, because none of its markers existed in
that document, so the accident was survivable.  It was survivable by luck.

Two faults produced it and this module removes both:

  1. A CONSTANT PORT.  Every session picked the same number, so every session collided.
     `port_for()` derives a port from the session identity instead, so two sessions collide
     only on a hash collision rather than on every single run.

  2. A SILENT BIND.  `allow_reuse_address = True` plus a swallowed exception meant "the port is
     taken" and "the server is up" looked identical from the outside.  `serve` sets
     `allow_reuse_address = False` and lets `OSError` reach the caller, so a taken port is an
     error and never a fallback.

The deeper rule, worth stating because it outlives this module: A PORT IS NOT AN IDENTITY.
Binding one proves nothing about who answers on it, so anything fetched over localhost is
identified AT THE POINT OF USE — see `expected_sha256` below, and the hash gate the publish
skill runs inside the page before it evaluates anything.
"""
import functools, hashlib, http.server, os, socket, socketserver, sys

PORT_LO, PORT_HI = 20000, 60000


SHELLS = {'zsh', 'bash', 'sh', 'dash', 'fish', 'ksh', 'tcsh', 'csh', 'python', 'python3'}


def _parent_of(pid):
    """(ppid, command) for a pid, or (None, None)."""
    import subprocess
    try:
        out = subprocess.run(['ps', '-o', 'ppid=,comm=', '-p', str(pid)],
                             capture_output=True, text=True, timeout=5).stdout.split(None, 1)
        if len(out) < 2:
            return None, None
        return int(out[0]), out[1].strip().split('/')[-1]
    except Exception:
        return None, None


def session_anchor(start=None, parent_of=None, max_hops=8):
    """The nearest ancestor that is NOT a shell — stable for the life of a session.

    THIS FUNCTION LIVES HERE AND `lease.py` IMPORTS IT, because there were two copies and only
    one of them got fixed.  The pid fallback made every invocation a different session; the PPID
    fallback that replaced it looked stable when called twice inside one shell command and was
    not, because this harness starts a fresh shell per command.  `lease.py` was repaired and
    `session_port.py` was not, so `port_for()` went on returning a different port every call —
    caught only when a hash gate refused to eval a file served on a port nothing was listening on.
    **One definition, imported, so the next repair cannot land in half the places.**
    """
    parent_of = parent_of or _parent_of
    pid = start if start is not None else os.getppid()
    seen = set()
    for _ in range(max_hops):
        if pid is None or pid in seen or pid <= 1:
            break
        seen.add(pid)
        ppid, comm = parent_of(pid)
        if comm is None:
            break
        if comm.lower() not in SHELLS:
            return pid
        pid = ppid
    try:
        return os.getsid(0)
    except Exception:
        return os.getpid()


def session_id():
    """Best available identity for this session; an explicit env var wins."""
    for var in ('CLAUDE_SESSION_ID', 'DESK_SESSION_ID'):
        v = os.environ.get(var)
        if v:
            return v
    return 'sess%d' % session_anchor()


def port_for(name=None, lo=PORT_LO, hi=PORT_HI):
    """Deterministic port in [lo, hi) for this session (and an optional sub-name).

    Deterministic so a second command in the same session finds the same server without
    passing the number around, and so a human can reproduce it while debugging.
    """
    key = ('%s::%s' % (session_id(), name or '')).encode()
    return lo + int.from_bytes(hashlib.sha256(key).digest()[:4], 'big') % (hi - lo)


def is_free(port, host='127.0.0.1'):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


class _CORS(http.server.SimpleHTTPRequestHandler):
    """Localhost origins are 'potentially trustworthy', so an https page may fetch them without
    tripping mixed-content blocking.  It still needs CORS, and it must never be cached: a cached
    snippet is a stale snippet, and a stale snippet is the failure this module exists to prevent.
    """

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, *a):
        pass


def make_server(directory, name=None, port=None, host='127.0.0.1'):
    """Bind, or raise.  `allow_reuse_address` stays False ON PURPOSE — see the module docstring."""
    port = port or port_for(name)
    socketserver.TCPServer.allow_reuse_address = False
    handler = functools.partial(_CORS, directory=os.path.abspath(directory))
    srv = socketserver.TCPServer((host, port), handler)   # OSError if taken: let it out
    srv.desk_port = port
    return srv


def expected_sha256(path):
    """The hash a fetcher must check THE BYTES IT RECEIVED against.

    Hashing the local file and then reporting it as though it described the served response is
    exactly the mistake that let another session's code reach a browser on 2026-09-02.  Hash the
    file here; compare it against what came back over the wire, at the point of use.
    """
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


USAGE = ("usage: session_port.py port [name]        # print this session's port\n"
         "       session_port.py serve DIR [name]   # serve DIR on it (fails loudly if taken)\n"
         "       session_port.py sha FILE           # sha256 for the point-of-use gate")


def main(argv):
    if len(argv) < 2 or argv[1] in ('-h', '--help'):
        print(__doc__)
        print(USAGE)
        return 0
    cmd = argv[1]
    if cmd == 'port':
        print(port_for(argv[2] if len(argv) > 2 else None))
        return 0
    if cmd == 'sha':
        print(expected_sha256(argv[2]))
        return 0
    if cmd == 'serve':
        directory = argv[2]
        name = argv[3] if len(argv) > 3 else None
        try:
            srv = make_server(directory, name)
        except OSError as e:
            sys.stderr.write(
                'session_port: could not bind %d — %s\n'
                'The port is held by another process (very likely another session on this\n'
                'machine). NOT falling back to a shared port: that is what served one session\'s\n'
                'code to another session\'s browser on 2026-09-02. Re-run to pick a fresh port.\n'
                % (port_for(name), e))
            return 2
        print('serving %s on http://127.0.0.1:%d/' % (os.path.abspath(directory), srv.desk_port),
              flush=True)
        srv.serve_forever()
        return 0
    sys.stderr.write('session_port: unknown command %r\n%s\n' % (cmd, USAGE))
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
