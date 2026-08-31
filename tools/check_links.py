#!/usr/bin/env python3
"""Status-check the in-body cross-links of a piece before it publishes.

WHY THIS EXISTS
  The house convention names a previously-published sibling essay in the body and
  hyperlinks it to its live post. Those URLs get copied from the scaffold — a
  README, a DASHBOARD block — and a copied URL is unverified by default.

  On 2026-08-29 a slug that had been a piece's canonical address since publication
  turned out to 302 to a 404. Nothing had ever followed it; it had only ever been
  copied. A published essay can carry a dead link to a sibling indefinitely,
  because nothing in the pipeline clicks.

USAGE
  python3 check_links.py <piece_dir> [--all]

  Checks every http(s) link in draft.md whose host matches the piece's own
  publication (inferred from publish.yaml's post_url/public_url), which is the set
  the convention governs. --all checks every external link instead.

EXIT
  0  every link resolved 2xx
  1  usage / no draft
  4  at least one link did not resolve — the message names it
"""
import sys, os, re, urllib.request, urllib.error

LINK_RE = re.compile(r'\]\((https?://[^)\s]+)\)')
UA = {'User-Agent': 'writing-desk-link-check/1.0'}


def manifest_host(piece_dir):
    """Host of this piece's own publication, from publish.yaml. None if absent."""
    path = os.path.join(piece_dir, 'publish.yaml')
    if not os.path.exists(path):
        return None
    for line in open(path):
        m = re.match(r'\s*(?:public_url|post_url)\s*:\s*(\S+)', line)
        if m:
            hm = re.match(r'https?://([^/]+)', m.group(1))
            if hm:
                return hm.group(1)
    return None


def check(url):
    """Return (ok, detail). Follows redirects; a redirect ENDING in an error is
    the failure mode that matters — /p/they-them returned 302 then 404."""
    try:
        req = urllib.request.Request(url, headers=UA, method='GET')
        with urllib.request.urlopen(req, timeout=20) as r:
            final = r.geturl()
            note = f"{r.status}" + (f" (-> {final})" if final.rstrip('/') != url.rstrip('/') else "")
            return 200 <= r.status < 300, note
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print(__doc__.strip())
        sys.exit(1)
    piece_dir = args[0].rstrip('/')
    draft = os.path.join(piece_dir, 'draft.md')
    if not os.path.exists(draft):
        print(f"no draft.md in {piece_dir}")
        sys.exit(1)

    host = manifest_host(piece_dir)
    urls = sorted(set(LINK_RE.findall(open(draft).read())))
    if '--all' not in sys.argv and host:
        urls = [u for u in urls if host in u]

    if not urls:
        print(f"no in-body cross-links to check ({'host ' + host if host else 'no host in manifest'})")
        return

    bad = []
    for u in urls:
        ok, note = check(u)
        print(f"  {'OK  ' if ok else 'DEAD'}  {note:24s}  {u}")
        if not ok:
            bad.append((u, note))

    print(f"checked {len(urls)} link(s), {len(bad)} dead")
    if bad:
        print("\nA dead cross-link must be fixed before composing — find the live slug in the "
              "publication's archive, correct it here AND in every scaffold file that repeats it "
              "(README, DASHBOARD), then re-run.")
        sys.exit(4)


if __name__ == '__main__':
    main()
