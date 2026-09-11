#!/usr/bin/env python3
"""substack_account.py — which browser a Substack operation runs in, and is it the right person?

WHY (2026-09-11).  A desk can own several Substack outlets on different accounts — one per
byline, because a Substack profile has one display name across every publication under it. A
Substack login is ONE cookie for every `*.substack.com` publication, and the built-in browser
pane's cookie store is shared by every tab and every session: a cookie set in one pane tab was
present in a fresh one, and a session that had never signed in found the pane signed in as the
other session's account. So the pane can hold one Substack account, never two — and signing it
out, or into another account, silently turns every concurrent session's work into the other
byline's: a compose lands in the wrong publication, a re-sync edits a post its session does not
own, and nothing errors.

THE RULE (Eric, 2026-09-11).  With more than one Substack outlet, ONE is the PRIMARY. The primary
uses the built-in browser pane for all its Substack operations; every other Substack outlet opens
in Claude in Chrome, each in its own named browser holding its own login. Naming the primary
explicitly beats inferring it from whatever the pane happens to be signed in as. Changing it is a
deliberate, desk-wide act (`primary <outlet>`), because it changes whose login the pane must hold.

Every write still proves it is on the right account first (`check`), so a session caught
mid-switch is refused rather than published under the wrong byline.

CONFIG (instance-side, publishing/outlets.yaml; the framework holds no handles)

    substack_primary: substack            # top level — names exactly one Substack outlet
    outlets:
      substack:
        reader_base: https://elmuffin.substack.com/p/
        account_handle: elmuffin          # the profile handle that must be signed in to write
        chrome_browser: <name>            # only needed if it is ever demoted
      substack-muffinlabs:
        reader_base: https://muffinlabs.substack.com/p/
        account_handle: ericgarciaphd
        chrome_browser: eric@muffinlabs.ai   # REQUIRED for a non-primary: it opens in Chrome

  A Substack outlet is one whose `reader_base` is on `*.substack.com`, or that says
  `platform: substack` (a custom domain). With only one Substack outlet it is the primary without
  saying so. `account_handle` falls back to `notes_handle`, the same person.

USAGE
    substack_account.py route <outlet>          # its surface (pane | chrome + browser), account, snippet
    substack_account.py primary                 # the primary, and where every Substack outlet runs
    substack_account.py primary <outlet>        # make <outlet> the primary (edits outlets.yaml)
    substack_account.py check <outlet> --handle <h> [--surface pane|chrome]
    substack_account.py snippet

  Run the snippet on any `*.substack.com` page of that surface — the publication's own host, where
  the editor lives, is fine. It must be SAME-ORIGIN: a fetch from a publication host to
  substack.com fails in the pane (measured), so the snippet uses a relative path.

EXIT
  0  ok — signed in as the outlet's account, on the outlet's surface (or: primary changed)
  1  usage, or no such outlet
  3  signed out — the author signs in (automation never enters credentials)
  4  checked on the wrong surface — this outlet runs in the other browser
  5  signed in as SOMEONE ELSE — stop; do not write here, and do not switch this surface
  6  misconfigured — no account declared, several Substack outlets and no primary, a non-primary
     with no chrome_browser, or a demotion that would leave an outlet nowhere to run
"""
import argparse
import json
import os
import re
import sys
import tempfile
from urllib.parse import urlparse

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
PRIMARY_KEY = 'substack_primary'


def load(path):
    """The whole registry: {'outlets': {...}, 'substack_primary': ...}."""
    if yaml is None:
        raise SystemExit("substack_account: pyyaml is required")
    with open(path, encoding='utf-8') as fh:
        doc = yaml.safe_load(fh) or {}
    doc.setdefault('outlets', {})
    doc['outlets'] = doc['outlets'] or {}
    return doc


def norm(handle):
    return str(handle or '').strip().lstrip('@').lower()


def expected(spec):
    """The handle allowed to write to this outlet: `account_handle`, else `notes_handle`."""
    spec = spec or {}
    return norm(spec.get('account_handle') or spec.get('notes_handle')) or None


def is_substack(spec):
    spec = spec or {}
    if spec.get('platform') == 'substack':
        return True
    host = urlparse(str(spec.get('reader_base') or '')).hostname or ''
    return host == 'substack.com' or host.endswith('.substack.com')


def substack_outlets(doc):
    return [n for n, s in doc['outlets'].items() if is_substack(s)]


def primary(doc):
    """-> (name or None, problem or None)."""
    subs = substack_outlets(doc)
    declared = doc.get(PRIMARY_KEY)
    if declared:
        if declared not in doc['outlets']:
            return None, f"{PRIMARY_KEY}: {declared!r} is not an outlet"
        if declared not in subs:
            return None, f"{PRIMARY_KEY}: {declared!r} is not a Substack outlet"
        return declared, None
    if len(subs) == 1:
        return subs[0], None
    if not subs:
        return None, "no Substack outlets"
    return None, (f"{len(subs)} Substack outlets ({', '.join(subs)}) and no {PRIMARY_KEY} — "
                  f"name one: substack_account.py primary <outlet>")


def route(doc, name):
    """-> dict, or None for an unknown outlet. `problem` is set when it cannot be run anywhere."""
    spec = doc['outlets'].get(name)
    if spec is None:
        return None
    prim, problem = primary(doc)
    is_primary = (name == prim)
    r = {'outlet': name, 'account': expected(spec), 'primary': is_primary,
         'surface': 'pane' if is_primary else 'chrome',
         'chrome_browser': (spec or {}).get('chrome_browser'),
         'problem': None, 'snippet': SNIPPET}
    if not is_substack(spec):
        r['problem'] = f"{name} is not a Substack outlet"
    elif problem and prim is None:
        r['problem'] = problem
    elif not is_primary and not r['chrome_browser']:
        r['problem'] = (f"{name} is not the primary, so it opens in Claude in Chrome — but it names "
                        f"no chrome_browser. Add the browser that holds its login to outlets.yaml.")
    return r


def verdict(doc, name, observed, surface=None):
    """-> (exit code, message). `observed` is the handle the snippet returned, or None;
    `surface` is where it was read."""
    r = route(doc, name)
    if r is None:
        return 1, f"no outlet {name!r} in the registry"
    if r['problem']:
        return 6, r['problem']
    want = r['account']
    if not want:
        return 6, (f"{name} names no account_handle — refusing rather than assuming who may "
                   f"write there. Add one to outlets.yaml.")
    where = ("the built-in pane (it is the primary)" if r['surface'] == 'pane'
             else f"Claude in Chrome, browser {r['chrome_browser']!r}")
    if surface and surface != r['surface']:
        return 4, (f"STOP: {name} runs in {where}, not the {surface}. Checking or writing it here "
                   f"would use whichever account this surface holds.")
    got = norm(observed)
    if not got:
        return 3, (f"signed out in {where}. {name} needs @{want}; the author signs in — "
                   f"automation never enters credentials.")
    if got != want:
        return 5, (f"STOP: {where} is signed in as @{got}, and {name} needs @{want}. Do not write, "
                   f"and do not sign this surface into another account — "
                   + ("every session shares the pane's login." if r['surface'] == 'pane'
                      else "fix the browser's login, or the outlet's chrome_browser."))
    return 0, f"ok: {where} is signed in as @{got}, the account {name} publishes as"


def _atomic_write(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.outlets-', suffix='.yaml')
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write(text)
    os.replace(tmp, path)


def set_primary(path, name):
    """Make `name` the primary by editing outlets.yaml in place, comments intact.
    -> (exit code, message)."""
    doc = load(path)
    spec = doc['outlets'].get(name)
    if spec is None:
        return 1, f"no outlet {name!r} in {path}"
    if not is_substack(spec):
        return 1, f"{name} is not a Substack outlet"
    if not expected(spec):
        return 6, f"{name} names no account_handle — declare the account before making it primary"
    old, _ = primary(doc)
    if old == name and doc.get(PRIMARY_KEY) == name:
        return 0, f"{name} is already the primary"
    if old and old != name and not (doc['outlets'][old] or {}).get('chrome_browser'):
        return 6, (f"demoting {old} would send it to Claude in Chrome, but it names no chrome_browser — "
                   f"add the browser that holds @{expected(doc['outlets'][old])}'s login first")
    others = [n for n in substack_outlets(doc) if n != name]
    homeless = [n for n in others if not (doc['outlets'][n] or {}).get('chrome_browser')]
    if homeless:
        return 6, f"{', '.join(homeless)} would have nowhere to run: add a chrome_browser first"

    src = open(path, encoding='utf-8').read()
    line = f"{PRIMARY_KEY}: {name}"
    if re.search(rf'^{PRIMARY_KEY}:', src, re.M):
        new = re.sub(rf'^{PRIMARY_KEY}:[^\n#]*', line + ' ', src, count=1, flags=re.M)
        new = re.sub(rf'^({PRIMARY_KEY}: \S+) +(#|\n)', r'\1 \2', new, count=1, flags=re.M)
        new = new.replace(line + ' \n', line + '\n')
    else:
        m = re.search(r'^outlets:', src, re.M)
        if not m:
            return 6, f"{path} has no top-level outlets: mapping"
        new = src[:m.start()] + line + "\n\n" + src[m.start():]
    if load_text_primary(new) != name:
        return 6, "refusing to write: the edit did not land where it was meant to"
    _atomic_write(path, new)

    want = expected(spec)
    msg = [f"{name} is now the primary: it uses the built-in pane for every Substack operation."]
    msg.append(f"  Sign the PANE in as @{want} — until then every write to {name} is refused (check exit 5).")
    for n in others:
        s = doc['outlets'][n] or {}
        msg.append(f"  {n} opens in Claude in Chrome, browser {s.get('chrome_browser')!r} — "
                   f"it must be signed in as @{expected(s)}.")
    msg.append("  The pane's login is shared by every session: tell anyone mid-write before you switch it.")
    return 0, "\n".join(msg)


def load_text_primary(text):
    return (yaml.safe_load(text) or {}).get(PRIMARY_KEY)


def _describe(r):
    if r['problem']:
        return f"UNRUNNABLE — {r['problem']}"
    return ("built-in pane (primary)" if r['surface'] == 'pane'
            else f"Claude in Chrome, browser {r['chrome_browser']!r}")


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--outlets', default='publishing/outlets.yaml')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('route'); p.add_argument('outlet')
    p = sub.add_parser('primary'); p.add_argument('outlet', nargs='?')
    sub.add_parser('snippet')
    p = sub.add_parser('check'); p.add_argument('outlet'); p.add_argument('--handle', default='')
    p.add_argument('--surface', choices=('pane', 'chrome'), default=None,
                   help='where the snippet ran; checking in the wrong browser is exit 4')
    p.add_argument('--json', action='store_true', help='print the verdict as JSON')
    o = ap.parse_args(argv)

    if o.cmd == 'snippet':
        print(SNIPPET)
        return 0
    if o.cmd == 'primary' and o.outlet:
        code, msg = set_primary(o.outlets, o.outlet)
        print(msg, file=sys.stdout if code == 0 else sys.stderr)
        return code
    doc = load(o.outlets)
    if o.cmd == 'primary':
        prim, problem = primary(doc)
        print(f"primary  {prim or '— none: ' + str(problem)}")
        for n in substack_outlets(doc):
            print(f"  {n:24} @{expected(doc['outlets'][n]) or '?':16} {_describe(route(doc, n))}")
        return 0 if prim and not any(route(doc, n)['problem'] for n in substack_outlets(doc)) else 6
    if o.cmd == 'route':
        r = route(doc, o.outlet)
        if r is None:
            print(f"no outlet {o.outlet!r} in {o.outlets}", file=sys.stderr)
            return 1
        print(f"outlet   {r['outlet']}\naccount  @{r['account'] or '?  (none declared — check will refuse)'}\n"
              f"surface  {_describe(r)}\nsnippet  {r['snippet']}")
        return 6 if r['problem'] else 0
    code, msg = verdict(doc, o.outlet, o.handle, o.surface)
    print(json.dumps({'code': code, 'message': msg}) if o.json else msg,
          file=sys.stdout if code == 0 else sys.stderr)
    return code


if __name__ == '__main__':
    sys.exit(main())
