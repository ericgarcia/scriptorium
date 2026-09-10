#!/usr/bin/env python3
"""substack_cover.py — set a post's Substack COVER (featured) image from the repo.

WHY THIS EXISTS (2026-09-10).  The cover was the last manual step in publishing.  Both
`publish` and `rewrite` said flatly that "the converter does not set Substack's featured
image — attaching it is a composer-UI action", and every piece therefore ended with the
author hunting through Downloads for a file the repo already had.  That claim turned out
to be untested rather than true.  Measured on post 214063778:

    POST /api/v1/image        {"image": "<data URI>"}   -> 200 {"id","url","imageWidth",…}
    PUT  /api/v1/drafts/<id>  {"cover_image": "<url>"}  -> 200, and it persists on read-back

So the cover is settable, and it should come from `pieces/<slug>/assets/` — the bytes the
repo already holds and has already disclosed the provenance of — rather than from whatever
is in the author's Downloads folder.

WHAT THIS EMITS
    A self-contained JS snippet that uploads the image, sets `cover_image`, reads the draft
    back, and returns the result.  It does NOT publish, does not touch the body, and does
    not send email.  Run it in the post's editor.

    In the BUILT-IN PANE, carry it in with `pane_carry.py` — never retype it; the payload is
    the image, and a transcription slip is a corrupted upload.
    In REAL CHROME the clipboard works too.

USAGE
    python3 framework/tools/substack_cover.py pieces/<slug> --post <id> [--out cover.js]
    python3 framework/tools/substack_cover.py pieces/<slug> --post <id> --max-width 1600

REFUSALS, and each is a real failure this would otherwise cause
    - no `cover:` in publish.yaml            -> nothing to set; say so rather than guess
    - the file named there is missing         -> the manifest and the disk disagree
    - the file is not an image                -> a data URI of the wrong type uploads fine
                                                 and renders as a broken cover
    - no provenance recorded for the cover    -> the house rule is that a cover's origin is
                                                 disclosed (generated vs photograph) before
                                                 it is attached to anything public
"""
import base64, json, mimetypes, os, re, sys, hashlib

def read_manifest(path):
    man, pending = {}, []
    if not os.path.exists(path):
        return man
    for line in open(path, encoding='utf-8'):
        m = re.match(r'\s*(cover|cover_caption|title|post_url)\s*:\s*(.*)', line)
        if m:
            v = re.sub(r'\s+#.*$', '', m.group(2).strip()).strip().strip('"\'')
            # a YAML block scalar (`>-`, `|`) puts the value on the FOLLOWING lines; taking the
            # marker as the value printed `>-` as this piece's caption
            if v in ('>-', '>', '|', '|-', ''):
                pending.append(m.group(1))
                continue
            man.setdefault(m.group(1), v)
        elif pending and line.startswith((' ', '\t')) and line.strip():
            man.setdefault(pending.pop(0), line.strip())
        elif line.strip():
            pending.clear()
    man['_raw'] = open(path, encoding='utf-8').read() if os.path.exists(path) else ''
    return man

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print(__doc__); sys.exit(1)
    piece = args[0].rstrip('/')
    out_js = 'cover.js'
    post_id = None
    max_w = None
    for i, a in enumerate(sys.argv):
        if a == '--out' and i + 1 < len(sys.argv): out_js = sys.argv[i+1]
        if a == '--post' and i + 1 < len(sys.argv): post_id = sys.argv[i+1]
        if a == '--max-width' and i + 1 < len(sys.argv): max_w = int(sys.argv[i+1])

    man = read_manifest(os.path.join(piece, 'publish.yaml'))
    cover = man.get('cover')
    if not cover:
        print(f"No `cover:` in {piece}/publish.yaml — nothing to set."); sys.exit(2)

    src = cover if os.path.isabs(cover) else os.path.join(piece, cover)
    if not os.path.exists(src):
        print(f"Refusing: publish.yaml names `{cover}` and it is not on disk at {src}."); sys.exit(3)

    mime, _ = mimetypes.guess_type(src)
    if not mime or not mime.startswith('image/'):
        print(f"Refusing: {src} is {mime or 'an unknown type'}, not an image. A wrong-type data "
              f"URI uploads cleanly and renders as a broken cover."); sys.exit(4)

    raw = open(src, 'rb').read()
    if max_w:
        try:
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(raw)).convert('RGB')
            if im.width > max_w:
                im.thumbnail((max_w, max_w * 10), Image.LANCZOS)
                buf = io.BytesIO(); im.save(buf, 'JPEG', quality=88, optimize=True)
                raw, mime = buf.getvalue(), 'image/jpeg'
        except ImportError:
            print("note: --max-width needs Pillow; sending the original bytes instead.")

    # provenance is a gate, not a nicety: a cover is the most public thing a post has
    if not re.search(r'provenance|generated|photograph', man.get('_raw', ''), re.I):
        print(f"Refusing: {piece}/publish.yaml records no provenance for the cover. Say whether "
              f"it is a photograph or generated — a photorealistic cover can imply a real person, "
              f"or re-attach a biographical reading the prose dropped."); sys.exit(5)

    b64 = base64.b64encode(raw).decode('ascii')
    data_uri = f"data:{mime};base64,{b64}"
    caption = man.get('cover_caption', '')

    snippet = """(async () => {
  const POST = %s;
  const DATA = "%s";
  const up = await fetch('/api/v1/image', {
    method: 'POST', credentials: 'include',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify({image: DATA})
  });
  if (!up.ok) return JSON.stringify({step: 'upload', status: up.status});
  const img = await up.json();
  const put = await fetch('/api/v1/drafts/' + POST, {
    method: 'PUT', credentials: 'include',
    headers: {'content-type': 'application/json'},
    body: JSON.stringify({cover_image: img.url})
  });
  if (!put.ok) return JSON.stringify({step: 'set', status: put.status, uploaded: img.url});
  const back = await (await fetch('/api/v1/drafts/' + POST, {credentials: 'include'})).json();
  return JSON.stringify({
    uploaded: img.url, width: img.imageWidth, height: img.imageHeight, bytes: img.bytes,
    coverNow: back.cover_image, matches: back.cover_image === img.url,
    stillUnpublished: back.is_published === false
  });
})()""" % (json.dumps(post_id or ''), data_uri)

    open(out_js, 'w', encoding='utf-8').write(snippet)
    print(f"{os.path.basename(src)}  {len(raw):,} bytes  {mime}  sha256={hashlib.sha256(raw).hexdigest()[:16]}")
    if caption:
        print(f"caption (set in the composer; the API field is separate): {caption}")
    print(f"wrote {out_js} ({len(snippet):,} bytes)")
    if not post_id:
        print("NOTE: no --post given, so the snippet has an empty id and will fail. Pass the "
              "draft id from the editor URL.")
    print("\nRun it in the post's editor. In the built-in pane, carry it with pane_carry.py; "
          "never retype it.\nIt uploads, sets cover_image, and reads back — it does not publish "
          "and does not send email.")

if __name__ == '__main__':
    main()
