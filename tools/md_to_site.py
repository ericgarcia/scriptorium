#!/usr/bin/env python3
"""md_to_site.py — turn pieces into a content bundle a website can render.

WHY THIS EXISTS
  Substack is bespoke because Substack chose to have no write API. Nothing else has
  to be. This emits the neutral artifact described in docs/BUNDLE.md — markdown plus
  front matter plus derived images — so a destination is learned once instead of once
  per site.

WHAT IT REFUSES TO DO
  Leak the desk. `draft.md` is a working file: everything above the first `---` is
  voice notes and verification status, HTML comments are asides, and a `†` inside a
  footnote marks an internal verify note. All three are stripped here, by the same
  rules the Substack converter uses. A draft with no `---` is an ERROR, not a
  best-effort export — guessing at that boundary is how an editorial note reaches a
  reader.

  Publish a piece nobody opted in. `site: true` in publish.yaml is required. A
  directory copy would eventually ship a draft; an allowlist cannot.

USAGE
  python3 md_to_site.py <bundle-dir> <piece-dir>... [options]

    --canonical-base URL   piece home is <URL>/<slug>; omit for no canonical
    --syndicated PLATFORM  record publish.yaml's public_url as syndication
                           (e.g. --syndicated substack)
    --max-width PX         longest edge of a derived image (default 1600)
    --quality N            WebP quality (default 82)
    --image-store NAME     repo (default) | s3 — recorded in bundle.json
    --force                export even pieces without `site: true`
    --apply                write. Dry run by default.

EXIT
  0 ok    1 usage    3 nothing opted in    4 a draft is missing its `---`
  5 an image could not be resolved
"""
import sys, os, re, json, argparse, hashlib, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import yaml                                                          # noqa: E402
from md_to_substack import clean_footnote, render_reader             # noqa: E402

try:
    from PIL import Image
except ImportError:
    Image = None

BUNDLE_SPEC = "1.1"
FOOTNOTE_DEF = re.compile(r'^(\[\^[^\]]+\]:)(.*)$')
IMAGE_MD = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)')


def die(code, msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def slug_of(piece_dir):
    """The DESK's identifier: the directory name. Stable for the life of the piece,
    because the desk cross-references by slug and titles move."""
    return os.path.basename(os.path.normpath(piece_dir))


def site_slug_of(man, source_slug):
    """The PUBLIC identifier: derived from the title, so a URL reads as what it is.

    These are two different jobs and they want two different names. The desk needs a
    handle that never moves; a reader needs an address that says what they are about to
    read. Substack already resolves it this way — 33 of the desk's 34 published pieces
    have a Substack slug equal to slugify(title) while their directory kept its original
    name — so deriving the same way keeps the two publications addressing a piece alike.

    An explicit `site_slug` in publish.yaml wins, for the case where the derivation is
    wrong or a published URL must be preserved verbatim."""
    if man.get('site_slug'):
        return str(man['site_slug'])
    title = man.get('title')
    if not title:
        return source_slug
    s = str(title).lower().replace('\u2019', "'").replace("'", '')
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s or source_slug


def load_manifest(piece_dir):
    p = os.path.join(piece_dir, 'publish.yaml')
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        return yaml.safe_load(f) or {}


def split_front_matter(src):
    """(front, body) on the first `---` line. Identical rule to piece_header.py:
    everything above it is desk-internal and can never reach a reader. Returns
    (None, src) when there is no separator — the caller must treat that as fatal."""
    lines = src.split('\n')
    for i, ln in enumerate(lines):
        if ln.strip() == '---':
            return '\n'.join(lines[:i]), '\n'.join(lines[i + 1:])
    return None, src


def strip_internal(body):
    """HTML comments anywhere; the dagger tail of every footnote definition.

    A definition is a BLOCK, not a line: it opens at `[^label]:` and runs to the next
    blank line, with continuations unindented. The dagger that opens an internal note
    usually falls on a continuation line, and clean_footnote strips from the dagger to
    the end of the string — so it has to see the whole block or it strips nothing.
    Line-at-a-time missed exactly that, and shipped two `(internal: …)` notes.

    Everything outside a footnote definition is passed through untouched."""
    body = re.sub(r'<!--.*?-->', '', body, flags=re.S)
    out, stripped = [], []
    label, rest = None, []                    # the open definition, if any

    def flush():
        nonlocal label, rest
        if label is not None:
            cleaned, removed = clean_footnote('\n'.join(rest))
            if removed:
                stripped.append(removed)
            out.append(f"{label} {cleaned}" if cleaned else label)
            label, rest = None, []

    for ln in body.split('\n'):
        m = FOOTNOTE_DEF.match(ln)
        if m:
            flush()
            label, rest = m.group(1), [m.group(2)]
        elif label is not None and ln.strip():
            rest.append(ln)
        else:
            flush()
            out.append(ln)
    flush()
    return '\n'.join(out), stripped


def derive_image(src_path, dest_path, max_width, quality, apply):
    """Web-size one image. Returns (width, height) of the derivative."""
    if Image is None:
        die(5, "Pillow is not installed; cannot derive images (pip install Pillow)")
    with Image.open(src_path) as im:
        im = im.convert('RGBA' if im.mode in ('RGBA', 'LA', 'P') else 'RGB')
        if im.width > max_width:
            im = im.resize((max_width, round(im.height * max_width / im.width)),
                           Image.LANCZOS)
        w, h = im.width, im.height
        if apply:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            im.save(dest_path, 'WEBP', quality=quality, method=6)
    return w, h


def resolve_images(piece_dir, slug, body, bundle, opts):
    """Rewrite every remote image URL to a bundle-relative path, deriving the file.

    The map in publish.yaml runs local -> remote (it exists so a recompose reuses an
    uploaded asset). Inverted here, it answers the question this tool actually has:
    which file on disk is this URL?"""
    man = load_manifest(piece_dir)
    imgs = man.get('images') if isinstance(man.get('images'), dict) else {}
    by_url = {v: k for k, v in imgs.items()}
    found, hero = [], None

    def repl(m):
        nonlocal hero
        alt, url = m.group(1), m.group(2)
        local = by_url.get(url) or (url if not url.startswith('http') else None)
        if not local:
            die(5, f"{slug}: no local file for {url}\n"
                   f"       run: python3 {HERE}/sync_post_images.py {piece_dir} --apply")
        src = os.path.join(piece_dir, local)
        if not os.path.exists(src):
            die(5, f"{slug}: {local} is mapped but missing on disk")
        name = os.path.splitext(os.path.basename(local))[0] + '.webp'
        dest = os.path.join(bundle, 'images', slug, name)
        w, h = derive_image(src, dest, opts.max_width, opts.quality, opts.apply)
        rel = f"../images/{slug}/{name}"
        rec = {'src': rel, 'alt': alt, 'width': w, 'height': h}
        found.append(rec)
        if hero is None:
            hero = rec
            return ''                       # hero is front matter; the site lays it out
        return f"![{alt}]({rel})"

    body = IMAGE_MD.sub(repl, body).strip()

    # A hero uploaded in the Substack composer is not referenced by draft.md — that is
    # the whole reason sync_post_images.py exists. Without this fallback such a piece
    # exports with no image at all, silently, while its picture sits on disk beside it.
    if hero is None and imgs:
        local = sorted(imgs)[0]
        src = os.path.join(piece_dir, local)
        if os.path.exists(src):
            name = os.path.splitext(os.path.basename(local))[0] + '.webp'
            dest = os.path.join(bundle, 'images', slug, name)
            w, h = derive_image(src, dest, opts.max_width, opts.quality, opts.apply)
            alt = (man.get('image_alt') or {}).get(local, '')
            hero = {'src': f"../images/{slug}/{name}", 'alt': alt, 'width': w, 'height': h}
            found.append(hero)

    return body, found, hero


def reader_digest(piece_dir):
    """sha256 over the same reader-text domain substack_verify diffs against, so a
    site and a Substack post are held to one bar rather than two."""
    body, fns, _residual, _issues = render_reader(piece_dir)
    h = hashlib.sha256()
    for chunk in list(body) + list(fns):
        h.update(chunk.encode('utf-8'))
        h.update(b'\x1e')
    return 'sha256:' + h.hexdigest()


def export_piece(piece_dir, bundle, opts):
    source_slug = slug_of(piece_dir)
    man = load_manifest(piece_dir)
    slug = site_slug_of(man, source_slug)

    draft = os.path.join(piece_dir, 'draft.md')
    if not os.path.exists(draft):
        die(1, f"{slug}: no draft.md")
    front, body = split_front_matter(open(draft).read())
    if front is None:
        die(4, f"{slug}: draft.md has no `---` separator, so the desk header cannot "
               f"be told from the body. Refusing to export rather than risk "
               f"publishing editorial notes.")

    body, stripped = strip_internal(body)
    body, images, hero = resolve_images(piece_dir, slug, body, bundle, opts)

    fm = {'slug': slug, 'title': man.get('title') or slug}
    if source_slug != slug:
        # What the desk calls it. Keeps a bundle traceable back to the piece it came
        # from, and lets the site emit a redirect from any URL it published before.
        fm['source_slug'] = source_slug
    for k in ('subtitle', 'published_at', 'footnotes'):
        if man.get(k):
            fm[k] = man[k]
    if opts.canonical_base:
        fm['canonical'] = f"{opts.canonical_base.rstrip('/')}/{slug}"
    if opts.syndicated and man.get('public_url'):
        fm['syndicated'] = [{'platform': opts.syndicated, 'url': man['public_url']}]
    if hero:
        fm['hero'] = hero
    if len(images) > 1:
        fm['images'] = images[1:]
    fm['digest'] = reader_digest(piece_dir)

    doc = ('---\n'
           + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=100)
           + '---\n\n' + body + '\n')
    out = os.path.join(bundle, 'content', f'{slug}.md')
    if opts.apply:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w') as f:
            f.write(doc)
    return slug, len(images), len(doc), len(stripped), source_slug


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('bundle')
    ap.add_argument('pieces', nargs='+')
    ap.add_argument('--canonical-base', default=None)
    ap.add_argument('--syndicated', default=None)
    ap.add_argument('--max-width', type=int, default=1600)
    ap.add_argument('--quality', type=int, default=82)
    ap.add_argument('--image-store', default='repo', choices=('repo', 's3'))
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--apply', action='store_true')
    o = ap.parse_args()

    selected, skipped = [], []
    for p in o.pieces:
        (selected if (load_manifest(p).get('site') is True or o.force)
         else skipped).append(p)
    if not selected:
        die(3, f"no piece has `site: true` in publish.yaml "
               f"({len(skipped)} skipped). Add it, or pass --force.")

    rows = [export_piece(p, o.bundle, o) for p in selected]

    meta = {'bundle_spec': BUNDLE_SPEC,
            'generator': 'scriptorium md_to_site.py',
            'generated_at': datetime.datetime.now(datetime.timezone.utc)
                            .replace(microsecond=0).isoformat(),
            'image_store': o.image_store,
            'pieces': [s for s, _n, _z, _k, _src in rows],
            'renames': {src: s for s, _n, _z, _k, src in rows if src != s}}
    if o.apply:
        os.makedirs(o.bundle, exist_ok=True)
        with open(os.path.join(o.bundle, 'bundle.json'), 'w') as f:
            json.dump(meta, f, indent=2)
            f.write('\n')

    notes = sum(k for _s, _n, _z, k, _src in rows)
    for s, n, size, k, src in rows:
        print(f"  {s:38} {n} image(s)  {size/1024:4.0f} KB"
              + (f"  [{k} note(s) stripped]" if k else '')
              + (f"  (was {src})" if src != s else ''))
    print(f"{len(rows)} piece(s), {notes} internal note(s) stripped -> {o.bundle}"
          + (f"  ({len(skipped)} not opted in)" if skipped else ''))
    if not o.apply:
        print("  (dry run — re-run with --apply to write)")


if __name__ == '__main__':
    main()
