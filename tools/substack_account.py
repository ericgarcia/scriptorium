#!/usr/bin/env python3
"""substack_account.py — is the browser about to write to Substack signed in as the right person?

WHY (2026-09-11).  A desk can own two Substack accounts — one per byline, because a Substack
profile has one display name across every publication under it. A Substack login is ONE cookie
for every `*.substack.com` publication, and the built-in browser pane's cookie store is shared by
every tab and every session: a cookie set in one pane tab was present in a fresh one, and a
session that had never signed in found the pane signed in as the other session's account. So:

  * the pane can hold one Substack account, never two, and
  * signing the pane out, or into the other account, silently turns every concurrent session's
    work into the other byline's — a compose lands in the wrong publication, a re-sync edits a
    post its session does not own, and nothing errors.

The fix has the same shape as giving a CLI a second config directory instead of re-logging the
first: each account gets its own PERSISTENT login, and every write first proves it is on the
right one. `outlets.yaml` names, per Substack outlet, the account allowed to write there and the
surface where that login lives; this tool routes to it and checks it. The check is surface-
independent — the same snippet runs in the pane or in a Chrome profile.

CONFIG (instance-side, publishing/outlets.yaml; the framework holds no handles)

    substack:
      account_handle: elmuffin     # the profile handle that must be signed in to write here
      surface: pane                # pane (default) | chrome
    substack-muffinlabs:
      account_handle: ericgarciaphd
      surface: pane                # THE PANE FIRST, always — the author's default surface
      fallback_surface: chrome     # used only when the pane is signed in as someone else
      chrome_browser: eric@muffinlabs.ai   # the Claude in Chrome browser holding that login

  The pane is tried first for every outlet (Eric, 2026-09-11: "we should use the inapp browser
  by default if possible"). It can only be possible for ONE account at a time, so an outlet whose
  account the pane does not hold names a fallback — and the check sends you there rather than
  letting anyone switch the pane.

  `account_handle` falls back to `notes_handle` — the same person — so an older registry works.

USAGE
    substack_account.py route <outlet>                  # surface, browser, account, and the snippet
    substack_account.py snippet                         # just the snippet
    substack_account.py check <outlet> --handle <h>     # after running the snippet on that surface

  Run the snippet on any `*.substack.com` page of that surface — the publication's own host, where
  the editor lives, is fine. It must be SAME-ORIGIN: a fetch from a publication host to
  substack.com fails in the pane (measured), so the snippet uses a relative path.

EXIT
  0  signed in as the outlet's account — proceed
  1  usage, or no such outlet
  3  signed out — the author signs in (automation never enters credentials)
  5  signed in as SOMEONE ELSE — stop; use the outlet's surface, do not switch this one
  6  the outlet names no account — refuse rather than assume
"""
import argparse
import json
import os
import sys

try:
    import yaml
except ImportError:
    yaml = None

# One expression, so a browser tool can evaluate it and return the result. Relative path on
# purpose: see USAGE.
SNIPPET = (
    "await (async () => { const r = await fetch('/api/v1/user/profile/self', "
    "{credentials: 'include'}); if (r.status !== 200) return {signed_in: false, "
    "status: r.status, origin: location.origin}; const j = await r.json(); "
    "return {signed_in: true, handle: j.handle, name: j.name, origin: location.origin}; })()"
)


def load(path):
    if yaml is None:
        raise SystemExit("substack_account: pyyaml is required")
    with open(path, encoding='utf-8') as fh:
        return (yaml.safe_load(fh) or {}).get('outlets') or {}


def norm(handle):
    return str(handle or '').strip().lstrip('@').lower()


def expected(spec):
    """The handle allowed to write to this outlet: `account_handle`, else `notes_handle`."""
    spec = spec or {}
    return norm(spec.get('account_handle') or spec.get('notes_handle')) or None


def route(outlets, name):
    spec = outlets.get(name)
    if spec is None:
        return None
    return {
        'outlet': name,
        'account': expected(spec),
        'surface': (spec or {}).get('surface') or 'pane',
        'fallback': (spec or {}).get('fallback_surface'),
        'chrome_browser': (spec or {}).get('chrome_browser'),
        'snippet': SNIPPET,
    }


def verdict(outlets, name, observed, surface=None):
    """-> (exit code, message). `observed` is the handle the snippet returned, or None;
    `surface` is where it was read, so a refusal can point at the fallback."""
    r = route(outlets, name)
    if r is None:
        return 1, f"no outlet {name!r} in the registry"
    want = r['account']
    if not want:
        return 6, (f"{name} names no account_handle — refusing rather than assuming who may "
                   f"write there. Add one to outlets.yaml.")
    got = norm(observed)
    if not got:
        return 3, (f"signed out on this surface. {name} needs @{want}; the author signs in — "
                   f"automation never enters credentials.")
    if got != want:
        on = surface or r['surface']
        if r['fallback'] and on == r['surface']:
            where = (f"This outlet falls back to {r['fallback']}"
                     + (f" (Claude in Chrome browser {r['chrome_browser']!r})" if r['chrome_browser'] else '')
                     + " when the pane holds another account — run the snippet there")
        else:
            where = (f"its surface is {r['surface']}"
                     + (f", then {r['fallback']}" if r['fallback'] else '')
                     + (f" (Claude in Chrome browser {r['chrome_browser']!r})" if r['chrome_browser'] else ''))
        return 5, (f"STOP: this surface is signed in as @{got}, and {name} needs @{want}. "
                   f"Do not write here, and do not sign this surface into the other account — "
                   f"its login is shared by every session using it. {where}.")
    return 0, f"ok: signed in as @{got}, the account {name} publishes as"


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--outlets', default='publishing/outlets.yaml')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('route'); p.add_argument('outlet')
    sub.add_parser('snippet')
    p = sub.add_parser('check'); p.add_argument('outlet'); p.add_argument('--handle', default='')
    p.add_argument('--surface', choices=('pane', 'chrome'), default=None,
                   help='where the snippet ran; a refusal in the pane then names the fallback')
    p.add_argument('--json', action='store_true', help='print the verdict as JSON')
    o = ap.parse_args(argv)

    if o.cmd == 'snippet':
        print(SNIPPET)
        return 0
    outlets = load(o.outlets)
    if o.cmd == 'route':
        r = route(outlets, o.outlet)
        if r is None:
            print(f"no outlet {o.outlet!r} in {o.outlets}", file=sys.stderr)
            return 1
        print(f"outlet   {r['outlet']}\naccount  @{r['account'] or '?  (none declared — check will refuse)'}\n"
              f"surface  {r['surface']}"
              + (f", falling back to {r['fallback']} when the pane holds another account" if r['fallback'] else '')
              + (f"  (Claude in Chrome browser {r['chrome_browser']!r})" if r['chrome_browser'] else '')
              + f"\nsnippet  {r['snippet']}")
        return 0
    code, msg = verdict(outlets, o.outlet, o.handle, o.surface)
    print(json.dumps({'code': code, 'message': msg}) if o.json else msg,
          file=sys.stdout if code == 0 else sys.stderr)
    return code


if __name__ == '__main__':
    sys.exit(main())
