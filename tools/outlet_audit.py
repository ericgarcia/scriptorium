#!/usr/bin/env python3
"""outlet_audit.py — does every piece actually exist on every outlet it declares?

WHY THIS EXISTS (2026-09-09, and it is not hypothetical)

  A piece was published, went live on one outlet, and was HTTP 404 on a second live
  outlet that had been standing unfed for weeks. Every step reported success, because
  each outlet's own checks only ever looked at that outlet. `substack_verify --archive`
  audits one publication against the desk; nothing compared the desk's outlets to each
  other. It was found by a person running `curl` by hand.

  HALF-PUBLISHED IS THE STATE NOTHING REPORTS, because both halves look complete from
  inside themselves. This is the check that looks across.

WHAT IT CHECKS

  forward   every piece that is PUBLISHED and DECLARES an outlet resolves there (200,
            and the page actually mentions the piece). A 404 is drift, not an error.
  declared  a piece that is live on an outlet it does not declare — the manifest is
            lying about where the piece went, which is how an outlet quietly acquires
            content nobody tracks.
  reverse   every URL the outlet itself lists (sitemap or index) is a piece the desk
            knows about. This is the only direction that can see a page the desk never
            produced.

WHAT IT REFUSES TO CONCLUDE

  That a piece is fine because it was not checked. "Could not reach" is its own exit
  code and never wears the same face as "matches" — the same rule substack_verify sets.

CONFIG (instance-side; the framework holds no URLs)

  publishing/outlets.yaml:

    legacy_outlet: alignmentfellowship   # what a pre-outlets `site: true` means
    outlets:
      substack:
        reader_base: https://elmuffin.substack.com/p/
        manifest_url_key: public_url
      alignmentfellowship:
        reader_base: https://alignmentfellowship.org/writings/
        trailing_slash: true
        manifest_url_key: site_url
        sitemap: https://alignmentfellowship.org/sitemap.xml

USAGE
  python3 outlet_audit.py [--config publishing/outlets.yaml] [--pieces pieces]
                          [--outlet NAME] [--no-reverse] [--quiet]

EXIT
  0 every declared outlet has its piece      3 drift (something missing or undeclared)
  1 usage / config                           2 nothing could be reached
"""
import sys, os, re, json, time, argparse, urllib.request, urllib.error
import concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import yaml

UA = 'scriptorium-outlet-audit/1.0'


def die(code, msg):
    print(f"outlet_audit: {msg}", file=sys.stderr)
    sys.exit(code)


class _Redirect308(urllib.request.HTTPRedirectHandler):
    """urllib does not follow 308 on its own, and a site that renames slugs answers
    almost entirely in 308s. Reading those as misses is how an audit invents 19
    failures that are all the same fact: the desk's directory name is not the
    published slug."""
    def http_error_308(self, req, fp, code, msg, headers):
        return self.http_error_301(req, fp, 301, msg, headers)


_OPENER = urllib.request.build_opener(_Redirect308)


def fetch(url, timeout=20):
    """(status, text, final_url). status None means the request itself failed."""
    bust = url + (('&' if '?' in url else '?') + f'_cb={int(time.time())}')
    req = urllib.request.Request(bust, headers={
        'User-Agent': UA, 'Cache-Control': 'no-cache', 'Pragma': 'no-cache'})
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8', 'replace'), r.geturl().split('?')[0]
    except urllib.error.HTTPError as e:
        return e.code, '', url
    except Exception:
        return None, '', url


def slug_of(manifest, piece_name, outlet_cfg):
    """The piece's address on this outlet: the manifest's own URL if it records one,
    else reader_base + the slug. A recorded URL always wins — a piece whose live slug
    was renamed is exactly the case a guessed URL gets wrong."""
    key = outlet_cfg.get('manifest_url_key')
    if key and manifest.get(key):
        return str(manifest[key])
    base = outlet_cfg.get('reader_base', '')
    if not base:
        return None
    # The desk's DIRECTORY name is not the published slug: pieces get retitled and the
    # directory keeps its original name (`thousand-faces` publishes as
    # `the-mask-comes-off-last`). Prefer the slug the piece already has on another
    # outlet, which is derived from the title the same way.
    slug = piece_name
    src = outlet_cfg.get('slug_source')
    if src and manifest.get(src):
        slug = str(manifest[src]).rstrip('/').split('/')[-1]
    url = base.rstrip('/') + '/' + slug
    return url + '/' if outlet_cfg.get('trailing_slash') else url


def load_pieces(pieces_dir, legacy_outlet):
    out = []
    for name in sorted(os.listdir(pieces_dir)):
        p = os.path.join(pieces_dir, name, 'publish.yaml')
        if not os.path.isfile(p):
            continue
        with open(p) as f:
            m = yaml.safe_load(f) or {}
        declared = m.get('outlets')
        legacy = False
        if not isinstance(declared, list):
            declared = [legacy_outlet] if (m.get('site') is True and legacy_outlet) else []
            legacy = bool(declared)
        out.append({'name': name, 'manifest': m, 'declared': declared,
                    'legacy': legacy, 'published': bool(m.get('published_at'))})
    return out


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--config', default='publishing/outlets.yaml')
    ap.add_argument('--pieces', default='pieces')
    ap.add_argument('--outlet', default=None, help='audit only this outlet')
    ap.add_argument('--no-reverse', action='store_true')
    ap.add_argument('--quiet', action='store_true', help='only print problems')
    a = ap.parse_args()

    if not os.path.exists(a.config):
        die(1, f"no outlet config at {a.config} — the instance defines its outlets, not the framework")
    with open(a.config) as f:
        cfg = yaml.safe_load(f) or {}
    outlets = cfg.get('outlets') or {}
    if not outlets:
        die(1, f"{a.config} defines no outlets")
    legacy_outlet = cfg.get('legacy_outlet')
    if a.outlet:
        if a.outlet not in outlets:
            die(1, f"unknown outlet {a.outlet!r}; config has {', '.join(outlets)}")
        outlets = {a.outlet: outlets[a.outlet]}

    pieces = load_pieces(a.pieces, legacy_outlet)
    if not pieces:
        die(1, f"no publish.yaml under {a.pieces}")

    # ---- forward: declared + published -> must resolve -----------------------
    jobs = []
    for pc in pieces:
        for oname in pc['declared']:
            if oname not in outlets:
                continue
            if not pc['published']:
                continue
            url = slug_of(pc['manifest'], pc['name'], outlets[oname])
            if url:
                jobs.append((pc, oname, url))

    results, unreachable = [], 0
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for (pc, oname, url), (status, body, final) in zip(
                jobs, ex.map(lambda j: fetch(j[2]), jobs)):
            ok = status == 200
            results.append({'piece': pc['name'], 'outlet': oname, 'url': url,
                            'status': status, 'ok': ok,
                            'redirected': final.rstrip('/') != url.split('?')[0].rstrip('/'),
                            'final': final})
            if status is None:
                unreachable += 1

    # ---- reverse: what each outlet lists that the desk does not claim --------
    known = {pc['name'] for pc in pieces}
    for pc in pieces:
        for k in ('public_url', 'site_url'):
            if pc['manifest'].get(k):
                known.add(str(pc['manifest'][k]).rstrip('/').split('/')[-1])
    reverse = {}
    if not a.no_reverse:
        for oname, oc in outlets.items():
            sm = oc.get('sitemap')
            if not sm:
                continue
            status, body, _f = fetch(sm, timeout=25)
            if status != 200:
                reverse[oname] = {'error': f'sitemap unreachable (HTTP {status})'}
                continue
            base = oc.get('reader_base', '').rstrip('/')
            live = set()
            for loc in re.findall(r'<loc>([^<]+)</loc>', body):
                if base and loc.rstrip('/').startswith(base) and loc.rstrip('/') != base:
                    live.add(loc.rstrip('/').split('/')[-1])
            reverse[oname] = {'live': live, 'unknown': sorted(live - known)}

    # ---- report --------------------------------------------------------------
    missing = [r for r in results if not r['ok'] and r['status'] is not None]
    unreach = [r for r in results if r['status'] is None]
    pending = [pc for pc in pieces if pc['declared'] and not pc['published']]
    undeclared = []
    for oname, info in reverse.items():
        for slug in info.get('unknown', []):
            undeclared.append((oname, slug))
    # a piece live on an outlet its manifest does not name
    lying = []
    for pc in pieces:
        # A pre-outlets manifest is not lying, it predates the convention. Only a
        # piece that HAS declared a list can be wrong about what is in it.
        if not isinstance(pc['manifest'].get('outlets'), list):
            continue
        for oname, oc in outlets.items():
            if oname in pc['declared']:
                continue
            key = oc.get('manifest_url_key')
            if key and pc['manifest'].get(key):
                lying.append((pc['name'], oname))

    W = max([len(r['piece']) for r in results] + [12])
    if not a.quiet:
        print(f"auditing {len(pieces)} piece(s) across {len(outlets)} outlet(s)  [cache-busted]")
        for r in sorted(results, key=lambda x: (x['piece'], x['outlet'])):
            mark = 'ok  ' if r['ok'] else 'MISS'
            if not a.quiet or not r['ok']:
                print(f"  {mark}  {r['piece']:<{W}}  {r['outlet']:<20} HTTP {r['status']}")
    else:
        for r in missing + unreach:
            print(f"  MISS  {r['piece']:<{W}}  {r['outlet']:<20} HTTP {r['status']}  {r['url']}")

    legacy_n = sum(1 for pc in pieces if pc['legacy'])
    print()
    print(f"{len(results) - len(missing) - len(unreach)} present, {len(missing)} missing, "
          f"{len(unreach)} unreachable across {len(outlets)} outlet(s)")
    if pending:
        print(f"  {len(pending)} piece(s) declare an outlet but are not published yet "
              f"(not checked): {', '.join(p['name'] for p in pending)}")
    if legacy_n:
        print(f"  {legacy_n} piece(s) still opt in with legacy `site: true` rather than `outlets:` "
              f"— counted as {legacy_outlet!r}")
    for oname, info in reverse.items():
        if 'error' in info:
            print(f"  reverse {oname}: {info['error']}")
        elif info['unknown']:
            print(f"  reverse {oname}: {len(info['unknown'])} live URL(s) the desk does not know: "
                  f"{', '.join(info['unknown'][:8])}")
        else:
            print(f"  reverse {oname}: all {len(info['live'])} live URL(s) are known to the desk")
    for name, oname in lying:
        print(f"  UNDECLARED  {name} records a {oname} URL but does not list {oname} in `outlets:`")

    if missing:
        print("\nFAILED: a piece declares an outlet it is not on.")
        sys.exit(3)
    if undeclared or lying:
        print("\nFAILED: an outlet carries something the manifests do not declare.")
        sys.exit(3)
    if results and len(unreach) == len(results):
        print("\nFAILED: nothing could be reached — that is not a pass.")
        sys.exit(2)
    if unreach:
        print("\nFAILED: some outlets could not be reached; 'not checked' is not 'fine'.")
        sys.exit(2)
    print("\nevery published piece is on every outlet it declares.")
    sys.exit(0)


if __name__ == '__main__':
    main()
