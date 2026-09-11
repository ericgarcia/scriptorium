#!/usr/bin/env python3
"""Bring a published post's images down into the piece, so they round-trip.

WHY THIS EXISTS
  Images uploaded in the Substack composer live only on Substack. `draft.md` knows
  nothing about them, so a recompose from the draft silently drops every picture in
  the post. This tool closes that loop: it stores each image with the piece under
  `assets/`, and records in `publish.yaml` which Substack URL each one was uploaded
  to, so the converter can point at the existing asset instead of uploading a
  duplicate.

WHAT IT PREFERS
  The ORIGINAL you uploaded, if it can find it. Substack stores PNGs byte-for-byte,
  so an md5 of the served file matches the file on your disk exactly — the match is
  proven, never guessed. Failing that it keeps Substack's copy, which is the same
  bytes anyway; the only thing lost is your filename.

USAGE
  python3 sync_post_images.py <piece_dir> [--source-dir DIR ...] [--apply]

  Dry run by default: prints what it would do and changes nothing. `--apply` writes.
  --source-dir may be repeated; ~/Downloads is searched by default.

EXIT
  0 ok (or nothing to do)   1 usage / no slug   4 an image could not be resolved
"""
import sys, os, re, json, html, hashlib, shutil, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from md_to_substack import read_manifest                            # noqa: E402
import substack_account as sa                                       # noqa: E402

UA = {'User-Agent': 'writing-desk-image-sync/1.0'}
DEFAULT_ORIGIN = 'https://elmuffin.substack.com'


def log(*a): print(*a)


def read_manifest_text(piece_dir):
    p = os.path.join(piece_dir, 'publish.yaml')
    return (open(p).read() if os.path.exists(p) else ''), p


def post_address(piece_dir, manifest_text):
    """-> (origin, slug): WHOSE Substack this post is on, and what it is called there.

    Both answers come from the piece's OWN outlet. Each outlet declares the manifest field
    its reader URL is written under (`manifest_url_key`, publishing/outlets.yaml), and this
    read `public_url` — which is one outlet's key (`substack`, Being Good), not a universal
    one. On a second Substack publication that is not a near miss but a silent
    cross-publication fetch: `public_url` is absent, so the slug fell through to the first
    `/p/<slug>` anywhere in the file and the origin fell back to a hard-coded
    elmuffin.substack.com — the other publication's host. The post either 404s, or worse
    resolves to a different post that happens to share the slug, and its images are pulled
    into this piece. Fixed 2026-09-11, the day after substack_verify and substack_notes
    learned the same convention (scriptorium c1e192f).

    The fallbacks are kept for a desk with no registry, which is what a one-outlet desk is.
    """
    try:
        _outlet, spec = sa.substack_outlet_for_piece(piece_dir)
    except Exception:                                   # noqa: BLE001 — unplaceable: fall back
        spec = {}
    url = str(read_manifest(os.path.join(piece_dir, 'publish.yaml'))
              .get((spec or {}).get('manifest_url_key') or 'public_url') or '')
    m = re.search(r'(https?://[^/\s]+)/p/([a-z0-9-]+)', url)
    if m:
        return m.group(1), m.group(2)
    # No recorded reader URL. The outlet still knows its own host; only the slug has to be
    # scavenged, and a slug read off the wrong publication's URL is the failure above.
    base = re.match(r'https?://[^/]+', str((spec or {}).get('reader_base') or ''))
    m = re.search(r'(https?://[^/\s]+)/p/([a-z0-9-]+)', manifest_text)
    if m:
        return (base.group(0) if base else m.group(1)), m.group(2)
    return (base.group(0) if base else DEFAULT_ORIGIN), None


def fetch_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode())


def originals_for(slug, origin=DEFAULT_ORIGIN):
    """Every distinct S3 original the post points at, cover first, then body order.
    Substack wraps images in a CDN transform URL with the real one percent-encoded
    inside; unwrap so we fetch the untouched upload rather than a re-encode."""
    post = fetch_json(f'{origin}/api/v1/posts/{slug}')
    def unwrap(u):
        if not u: return None
        m = re.search(r'(https%3A%2F%2F.+)$', u)
        u = urllib.parse.unquote(m.group(1)) if m else u
        return u if 'substack-post-media' in u else None
    seen, out = set(), []
    for u in [unwrap(post.get('cover_image'))]:
        if u and u not in seen: seen.add(u); out.append(u)
    body = html.unescape(post.get('body_html') or '')
    for m in re.finditer(r'https?://substack-post-media\.s3\.amazonaws\.com/public/images/[\w.%-]+', body):
        u = urllib.parse.unquote(m.group(0))
        if u not in seen: seen.add(u); out.append(u)
    for m in re.finditer(r'https%3A%2F%2Fsubstack-post-media[\w%.-]+', body):
        u = urllib.parse.unquote(m.group(0))
        if u not in seen: seen.add(u); out.append(u)
    return out, post


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def index_sources(dirs):
    """size -> [paths]. Size first because it is free; md5 confirms the winner."""
    idx = {}
    for d in dirs:
        d = os.path.expanduser(d)
        if not os.path.isdir(d): continue
        for name in os.listdir(d):
            fp = os.path.join(d, name)
            if os.path.isfile(fp):
                try: idx.setdefault(os.path.getsize(fp), []).append(fp)
                except OSError: pass
    return idx


def md5(b): return hashlib.md5(b).hexdigest()
def md5f(p): return md5(open(p, 'rb').read())


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    apply = '--apply' in sys.argv
    if not args:
        print(__doc__.strip()); sys.exit(1)
    piece_dir = args[0].rstrip('/')
    srcs = []
    for i, a in enumerate(sys.argv):
        if a == '--source-dir' and i + 1 < len(sys.argv): srcs.append(sys.argv[i + 1])
    srcs = srcs or ['~/Downloads']

    man_text, man_path = read_manifest_text(piece_dir)
    origin, slug = post_address(piece_dir, man_text)
    if not slug:
        log(f'{piece_dir}: no /p/<slug> in publish.yaml — not published yet, nothing to sync')
        sys.exit(0)

    log(f'  reading {origin}/p/{slug}')
    urls, post = originals_for(slug, origin)
    if not urls:
        log(f'{piece_dir} ({slug}): the post has no images'); sys.exit(0)

    assets = os.path.join(piece_dir, 'assets')
    existing = {}
    if os.path.isdir(assets):
        for n in os.listdir(assets):
            fp = os.path.join(assets, n)
            if os.path.isfile(fp) and not n.endswith('.md'):
                existing[md5f(fp)] = n

    src_idx = index_sources(srcs)
    mapping, problems = [], 0
    for i, url in enumerate(urls):
        blob = get(url)
        h, size = md5(blob), len(blob)
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1] or '.png'

        if h in existing:                                   # already stored with the piece
            rel = f'assets/{existing[h]}'
            log(f'  [have]  {rel}  ({size} bytes)')
            mapping.append((rel, url)); continue

        cand = [p for p in src_idx.get(size, []) if md5f(p) == h]
        if cand:
            base = 'hero' if i == 0 else f'image-{i+1}'
            name = base + ext
            rel = f'assets/{name}'
            log(f'  [origin] {rel}  <- {os.path.basename(cand[0])}  ({size} bytes, md5 verified)')
            if apply:
                os.makedirs(assets, exist_ok=True)
                shutil.copy2(cand[0], os.path.join(assets, name))
            mapping.append((rel, url))
        else:
            base = 'hero' if i == 0 else f'image-{i+1}'
            name = base + ext
            rel = f'assets/{name}'
            log(f'  [remote] {rel}  <- Substack copy ({size} bytes); no local original found')
            if apply:
                os.makedirs(assets, exist_ok=True)
                open(os.path.join(assets, name), 'wb').write(blob)
            mapping.append((rel, url))

    if apply:
        text = man_text
        text = re.sub(r'\n# --- images.*?(?=\n[a-z_#]|\Z)', '', text, flags=re.S)
        text = re.sub(r'\nimages:\n(?:[ \t]+\S.*\n)*', '\n', text)
        block = ['', '# --- images stored with the piece -------------------------------------------',
                 '# Each local file, and the Substack URL it is already uploaded to. The converter',
                 '# points at the URL instead of re-inlining the bytes, so recomposing reuses the',
                 '# asset in the post rather than uploading a duplicate. Delete a URL to force a',
                 '# fresh upload from the local file.', 'images:']
        for rel, url in mapping:
            block.append(f'  {rel}: {url}')
        text = text.rstrip('\n') + '\n' + '\n'.join(block) + '\n'
        open(man_path, 'w').write(text)
        log(f'  recorded {len(mapping)} image(s) in {man_path}')
    else:
        log('  (dry run — re-run with --apply to write)')
    sys.exit(4 if problems else 0)


if __name__ == '__main__':
    main()
