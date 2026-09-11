#!/usr/bin/env python3
"""pane_carry.py — hand a large generated snippet to the BUILT-IN BROWSER PANE.

WHY THIS EXISTS (2026-09-10).  A re-sync needs an 80-125 KB snippet inside the page, and the
agent must never retype it: a transcription slip publishes a typo in the author's voice and
every downstream guard reads it as an intended edit.  In real Chrome the system clipboard does
this.  In the built-in pane it cannot, and neither can the network:

    fetch('http://127.0.0.1:<port>/...')        -> TypeError: Failed to fetch
    <script src="http://127.0.0.1:<port>/...">  -> onerror
    window.open(...) + postMessage to opener    -> the pane NAVIGATES THE TAB; no opener

Neither of the first two REACHES THE SERVER (the access log stays empty), so the pane blocks
http subresources from an https document, client-side.  Both were tried with correct CORS and
with `Access-Control-Allow-Private-Network: true` for Chrome's PNA preflight.  No response
header opens that door; do not go debugging the server.

What works is `window.name`, which survives a cross-origin top-level navigation.  This tool
serves the carrier page and the payload, and prints the sha256 the page must agree with.

USAGE
    python3 framework/tools/pane_carry.py <snippet-path>

Then, in the pane:
    1. navigate to the printed carry URL      (loads window.name)
    2. navigate to the post editor            (window.name crosses intact)
    3. re-hash in the page, compare to the printed sha256, and only then execute

A PORT IS NOT AN IDENTITY.  Step 3 is the whole reason this hop is safe: `session_port.py`
already learned that binding a port proves nothing about who answers on it, so the bytes are
identified AT THE POINT OF USE rather than trusted because they arrived.
"""
import functools, http.server, os, socketserver, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session_port
import substack_account

CARRY = """<!doctype html><meta charset="utf-8"><title>desk carry</title><body>carrying…</body>
<script>
(async () => {
  const f = new URLSearchParams(location.search).get('f');
  const r = await fetch('/' + f, { cache: 'no-store' });
  const text = await r.text();
  const hash = [...new Uint8Array(await crypto.subtle.digest(
      'SHA-256', new TextEncoder().encode(text)))]
    .map(b => b.toString(16).padStart(2, '0')).join('');
  window.name = JSON.stringify({ __desk: 1, file: f, hash, text });
  document.body.textContent = 'carrying ' + f + ' len=' + text.length + ' sha=' + hash.slice(0, 16);
})();
</script>
"""


class _H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Harmless here and correct for any other consumer; note that NONE of it unblocks the
        # pane's subresource ban — window.name is the route, not CORS.
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, *a):
        pass


def main(argv):
    if len(argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    snippet = os.path.abspath(argv[1])
    if not os.path.isfile(snippet):
        sys.stderr.write('pane_carry: no such file: %s\n' % snippet)
        return 2
    # A Substack snippet must carry its own account guard (substack_account.py): the pane's login
    # is shared by every session and can change between any check and this run. One without it —
    # stale, or hand-made — is not carried.
    with open(snippet, encoding='utf-8', errors='replace') as fh:
        payload = fh.read()
    handle = substack_account.guard_handle(payload)
    if substack_account.drives_substack(payload) and not handle:
        sys.stderr.write(
            'pane_carry: refusing %s: it drives a Substack editor or API but carries no account\n'
            'guard. Regenerate it with the framework tool that made it; never hand-make one.\n' % snippet)
        return 2
    directory = os.path.dirname(snippet)
    with open(os.path.join(directory, 'carry.html'), 'w') as fh:
        fh.write(CARRY)

    port = session_port.port_for()
    socketserver.TCPServer.allow_reuse_address = False   # a taken port is an error, never a fallback
    try:
        srv = socketserver.TCPServer(('127.0.0.1', port),
                                     functools.partial(_H, directory=directory))
    except OSError as e:
        sys.stderr.write(
            'pane_carry: could not bind %d — %s\n'
            'Another session very likely holds it. NOT falling back to a shared port: that is\n'
            "what served one session's code to another session's browser on 2026-09-02.\n" % (port, e))
        return 2

    name = os.path.basename(snippet)
    print('carry URL : http://127.0.0.1:%d/carry.html?f=%s' % (port, name))
    print('sha256    : %s' % session_port.expected_sha256(snippet))
    print('bytes     : %d' % os.path.getsize(snippet))
    if handle:
        print('account   : @%s — the snippet stops before touching anything unless the page is\n'
              '            signed in as that account' % handle)
    print('\nnavigate the pane to the carry URL, then to the post editor, then verify the sha256')
    print('IN THE PAGE before executing. Ctrl-C here when the snippet has run.', flush=True)
    srv.serve_forever()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
