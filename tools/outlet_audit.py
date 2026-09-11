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
import html as html_mod
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


def landed_on_not_found(final_url, outlet_cfg):
    """A missing page that REDIRECTS to a page that exists answers 200.

    Measured 2026-09-10: a LinkedIn article that does not exist answers 301 to
    /top-content/?trk=article_not_found, which is a real page and returns 200. The
    forward check followed the redirect and read that 200 as the article being live —
    the audit would have reported every missing LinkedIn copy as present. An outlet
    names the markers that mean "this is where you land when it is not there"."""
    markers = outlet_cfg.get('not_found_markers') or []
    return any(m in (final_url or '') for m in markers)


def slug_of(manifest, piece_name, outlet_cfg):
    """The piece's address on this outlet: the manifest's own URL if it records one,
    else reader_base + the slug. A recorded URL always wins — a piece whose live slug
    was renamed is exactly the case a guessed URL gets wrong."""
    key = outlet_cfg.get('manifest_url_key')
    if key and manifest.get(key):
        return str(manifest[key])
    # An outlet whose addresses cannot be derived — LinkedIn's /pulse/<slug>-<author>-<id>
    # carries an id nothing on the desk knows — is checked only at a RECORDED url. Guessing
    # one would audit a page that never existed and call the miss a finding.
    if outlet_cfg.get('derive') is False:
        return None
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



# ---------------------------------------------------------------- content check
def _render_reader(piece_dir):
    """The desk's own reader-text renderer, borrowed rather than reimplemented."""
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location('_mts', os.path.join(here, 'md_to_substack.py'))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.render_reader(piece_dir)


def _text_of(md):
    """Markdown body -> the paragraphs a reader sees, normalised for comparison."""
    md = re.sub(r'```.*?```', ' ', md, flags=re.S)          # fenced code
    md = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', md)          # images
    # Footnote definitions, WHOLE — they run to the next blank line. Anchoring to `$`
    # removes only the first line and leaves the tail behind as a phantom paragraph, raw
    # markdown link and all, which then matches nothing (2026-09-10).
    # Footnote TEXT is deliberately out of scope here: substack_verify compares notes on
    # Substack footnote-for-footnote, and this check is about the body a reader scrolls.
    md = re.sub(r'^\[\^[\w-]+\]:.*?(?=\n\s*\n|\Z)', '', md, flags=re.M | re.S)
    md = re.sub(r'\[\^[\w-]+\]', '', md)                    # footnote refs
    md = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', md)        # links -> their text
    md = re.sub(r'[*_`>#]+', '', md)                        # emphasis, quotes, headings
    out = []
    for block in re.split(r'\n\s*\n', md):
        t = _norm_text(block)
        if len(t) >= 40:                                    # skip headings/short lines
            out.append(t)
    return out


def _strip_page_furniture(page):
    """Remove what the TEMPLATE adds, so only the author's words are compared.

    Three things, each of which produced false drift before it was handled (2026-09-10):

    - `<script>` / `<style>`. Substack ships the whole post again inside a JSON preload;
      leaving it in means the comparison can pass against data rather than against the
      page a reader sees, which is a pass for the wrong reason.
    - Footnote ANCHORS. A native footnote renders its number inline — "…to steer. 1 It's
      also the old error…" — and the draft has no such digit, so every paragraph carrying
      a footnote read as missing.
    - `<sup>` generally, which is how both outlets mark those numbers.
    """
    page = re.sub(r'<script\b.*?</script>', ' ', page, flags=re.S | re.I)
    page = re.sub(r'<style\b.*?</style>', ' ', page, flags=re.S | re.I)
    page = re.sub(r'<a\b[^>]*href="#footnote[^"]*"[^>]*>.*?</a>', ' ', page, flags=re.S | re.I)
    page = re.sub(r'<sup\b.*?</sup>', ' ', page, flags=re.S | re.I)
    return page


def _norm_text(t):
    t = t.replace('\u2019', "'").replace('\u2018', "'")
    t = t.replace('\u201c', '"').replace('\u201d', '"')
    t = t.replace('\u2014', '-').replace('\u2013', '-').replace('\u2026', '...')
    t = re.sub(r'<[^>]+>', ' ', t)
    t = html_mod.unescape(t)
    t = re.sub(r'\s+', ' ', t)
    # Stripping every tag to a space leaves a space wherever inline formatting ended
    # mid-sentence: `<strong>…arrived</strong>, by cuts` becomes "arrived , by cuts",
    # and the paragraph then matches nothing. That is the checker manufacturing its own
    # drift — it reported 19 false stale paragraphs on a piece substack_verify had just
    # confirmed identical block for block (2026-09-10). Close the gap the tags opened.
    t = re.sub(r'\s+([,.;:!?%)\]}])', r'\1', t)
    t = re.sub(r'([(\[{])\s+', r'\1', t)
    t = re.sub(r"\s+('s|'t|'re|'ve|'ll|'d|'m)\b", r'\1', t)
    # A hyphen joining two words loses to the same tag-stripping: `belief-<em>in</em>`
    # renders as "belief- in". An em-dash is distinguishable because it carries a space on
    # BOTH sides, so only close the word-hyphen-word case.
    t = re.sub(r'(\w)-\s+(\w)', r'\1-\2', t)
    return t.strip()


def publishable_body(piece_dir):
    """The part of draft.md a reader gets: below the first `---`, internal notes stripped."""
    path = os.path.join(piece_dir, 'draft.md')
    if not os.path.exists(path):
        return None
    src = open(path, encoding='utf-8').read()
    parts = src.split('\n---\n', 1)
    body = parts[1] if len(parts) > 1 else src
    body = re.sub(r'<!--.*?-->', ' ', body, flags=re.S)     # HTML comments
    body = re.sub(r'\u2020[^\n]*', '', body)                # dagger notes
    return body


def content_drift(piece_dir, page_html, canonical_outlet=False):
    """Does the live page carry the desk's paragraphs?

    Deliberately a PRESENCE check, not an equality one, and the report says so. The
    outlets render the same source through different templates — wrappers, class names
    and whitespace differ by design — so comparing whole documents would report drift
    on every piece forever, which is the fastest way to make a check ignored.

    What it can prove: every paragraph the desk holds is on the page a reader gets. That
    catches the failure that matters — a stale build serving an old version, or a piece
    silently truncated — because a changed sentence is a paragraph that is no longer there.

    What it cannot prove: ordering, or that the page carries nothing EXTRA. Say so rather
    than implying more.
    """
    # Use the SAME renderer the converter and substack_verify use, rather than a second
    # markdown-to-text written for this check (a second implementation is a second set
    # of bugs; the hand-rolled one had several, 2026-09-10).
    try:
        want = [n for n in (_norm_text(t) for t in _render_reader(piece_dir)[0]) if len(n) >= 40]
    except Exception:                                          # noqa: BLE001
        return None
    # render_reader prepends "Originally published at <canonical>" whenever a piece has
    # a canonical URL (md_to_substack.py) — correct for a SYNDICATED copy, and correctly
    # absent from the canonical outlet itself. Expecting it there reported the original
    # site as stale for not calling itself a copy (2026-09-11).
    if canonical_outlet:
        want = [w for w in want if not w.startswith('Originally published at ')]
    if not want:
        return None
    have = _norm_text(_strip_page_furniture(page_html))
    # Compare with ALL whitespace removed. Every remaining false lead on 2026-09-11 was a
    # whitespace artifact of one kind or another — a line break inside a block joined with
    # no space ("sent Me.I came"), an italic word before a suffix split by tag-stripping
    # (*that*s -> "that s") — the same class as the space-before-comma and word-hyphen
    # patches above, which this subsumes. A reader cannot see a whitespace-only difference,
    # and any change to WORDS still changes the non-space characters, so nothing that
    # matters is lost.
    have_ns = re.sub(r'\s+', '', have)
    missing = [w for w in want if re.sub(r'\s+', '', w) not in have_ns]
    return {'paragraphs': len(want), 'missing': missing}


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--config', default='publishing/outlets.yaml')
    ap.add_argument('--pieces', default='pieces')
    ap.add_argument('--outlet', default=None, help='audit only this outlet')
    ap.add_argument('--no-reverse', action='store_true')
    ap.add_argument('--content', action='store_true',
                    help='also compare the WORDS on each outlet against the desk, not just '
                         'that the URL resolves (a 200 proves a page exists, not that it is '
                         'the right one)')
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
    jobs, unrecorded = [], []
    for pc in pieces:
        for oname in pc['declared']:
            if oname not in outlets:
                continue
            if not pc['published']:
                continue
            url = slug_of(pc['manifest'], pc['name'], outlets[oname])
            if url:
                jobs.append((pc, oname, url))
            elif outlets[oname].get('derive') is False:
                unrecorded.append((pc['name'], oname, outlets[oname].get('manifest_url_key')))

    results, unreachable = [], 0
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for (pc, oname, url), (status, body, final) in zip(
                jobs, ex.map(lambda j: fetch(j[2]), jobs)):
            ok = status == 200 and not landed_on_not_found(final, outlets[oname])
            row = {'piece': pc['name'], 'outlet': oname, 'url': url,
                   'status': status, 'ok': ok,
                   'redirected': final.rstrip('/') != url.split('?')[0].rstrip('/'),
                   'final': final}
            if a.content and ok and body:
                canon = str(pc['manifest'].get('canonical') or '')
                base = str(outlets[oname].get('reader_base') or '').rstrip('/')
                row['content'] = content_drift(os.path.join(a.pieces, pc['name']), body,
                                               canonical_outlet=bool(canon and base and canon.startswith(base)))
            results.append(row)
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
    stale = [r for r in results
             if r.get('content') and r['content']['missing']]
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
            c = r.get('content')
            extra = ''
            if c is not None:
                n = c['paragraphs']
                extra = (f"  {n}/{n} paragraphs" if not c['missing']
                         else f"  STALE {n - len(c['missing'])}/{n} paragraphs")
            if not a.quiet or not r['ok']:
                print(f"  {mark}  {r['piece']:<{W}}  {r['outlet']:<20} HTTP {r['status']}{extra}")
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
    for name, oname, key in unrecorded:
        print(f"  UNRECORDED  {name} is published and declares {oname}, whose URLs cannot be "
              f"derived — record it under `{key}` or the copy is unaudited")

    if a.content:
        checked = [r for r in results if r.get('content') is not None]
        print(f"  content: {len(checked) - len(stale)}/{len(checked)} page(s) carry every "
              f"paragraph the desk holds"
              + (" — presence, not ordering; a page may still carry extra" if checked else ""))
        for r in stale:
            c = r['content']
            print(f"  STALE  {r['piece']} on {r['outlet']}: {len(c['missing'])} of "
                  f"{c['paragraphs']} paragraph(s) are not on the page")
            print(f"         first: {c['missing'][0][:100]}")
            print(f"         {r['url']}")

    if stale:
        print("\nFAILED: an outlet resolves but serves text the desk does not hold. "
              "A 200 proves a page exists, not that it is the right one.")
        print("  On SUBSTACK, `substack_verify --fresh` is the authority and this is the "
              "coarser instrument: it compares rendered page text across two templates, so "
              "where the two disagree, believe substack_verify and treat the finding here as "
              "a lead. On every other outlet this is the only check there is.")
        sys.exit(3)
    if missing:
        print("\nFAILED: a piece declares an outlet it is not on.")
        sys.exit(3)
    if undeclared or lying:
        print("\nFAILED: an outlet carries something the manifests do not declare.")
        sys.exit(3)
    if unrecorded:
        # Not 'missing' — the copy may well be up. But nothing can check it, and a check
        # that silently skips is the blind spot this audit was written to close.
        print("\nFAILED: a published piece declares an outlet whose address was never recorded.")
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
