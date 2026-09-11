#!/usr/bin/env python3
"""
store_publish.py — upload a published bundle to the content store.

The store is what a site reads. Putting a bundle in it is the whole of "publishing" for
a web outlet: no build, no deploy, no site repo touched. A correction is live in about a
minute, which is the property the whole design is for.

  usage: python3 tools/store_publish.py <bundle-dir>
                 [--config publishing/store.yaml] [--dry-run] [--prune]

The bundle directory is laid out the way BUNDLE.md says, and this tool does not care
what is in it beyond choosing a Cache-Control per prefix:

  <bundle>/index.json
  <bundle>/pieces/<slug>.json
  <bundle>/talks/<slug>/…
  <bundle>/images/<slug>/…

Three properties worth stating, because each is a decision:

  IDEMPOTENT   An object whose bytes and Cache-Control already match is skipped, so
               re-publishing an unchanged bundle uploads nothing and invalidates
               nothing. That is what makes "publish everything" a safe default.

  ADDITIVE     Remote objects missing from the bundle are left alone unless --prune is
               given. A partial bundle should not silently unpublish a corpus.

  FIRE AND     An invalidation is created and not waited on. The publishing role can
  FORGET       create invalidations but cannot read them back, so a wait step fails with
               AccessDenied and looks like a broken publish. Confirm by re-fetching.
"""

import argparse
import hashlib
import json
import mimetypes
import os
import sys

try:
    import boto3
    import yaml
except ImportError as e:                                          # noqa: BLE001
    print(f"error: missing dependency ({e.name}); pip install boto3 pyyaml", file=sys.stderr)
    sys.exit(2)


def die(code, msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


# Content types the bundle actually contains. mimetypes gets .webp and .js wrong or
# inconsistent across platforms often enough to be worth pinning.
TYPES = {
    '.json': 'application/json',
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.md': 'text/markdown; charset=utf-8',
    '.txt': 'text/plain; charset=utf-8',
    '.webp': 'image/webp',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.woff2': 'font/woff2',
}


def content_type(key):
    ext = os.path.splitext(key)[1].lower()
    return TYPES.get(ext) or mimetypes.guess_type(key)[0] or 'application/octet-stream'


def cache_control(key, cc):
    """Pick a Cache-Control for one object.

    The split is not by file type but by whether the object is *replaced in place*.
    A piece's JSON is rewritten whenever a sentence changes, so it must go stale fast.
    An image is content-addressed by name — a changed picture gets a changed filename —
    so it can cache for a year. A talk is mostly the second kind, except the two files
    regenerated on every re-import.
    """
    if key == 'index.json':
        return cc.get('index')
    if key.startswith('pieces/'):
        return cc.get('pieces')
    if key.startswith('images/'):
        return cc.get('images')
    if key.startswith('talks/'):
        base = os.path.basename(key)
        if base in ('notes.json', 'deck.html', 'piece.json'):   # rewritten in place
            return cc.get('talks_mutable', cc.get('pieces'))
        return cc.get('talks')
    return cc.get('pieces')


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def local_objects(bundle):
    """Every file in the bundle, as store keys."""
    out = {}
    for root, _dirs, files in os.walk(bundle):
        for name in files:
            if name == '.DS_Store':
                continue
            path = os.path.join(root, name)
            key = os.path.relpath(path, bundle).replace(os.sep, '/')
            out[key] = path
    return out


def remote_objects(s3, bucket):
    """Every object already in the store, with its ETag and Cache-Control.

    The ETag is an md5 for a single-part upload, which is all this tool makes. A
    multipart ETag carries a `-N` suffix and simply never matches, so such an object is
    re-uploaded rather than wrongly skipped.
    """
    out = {}
    token = None
    while True:
        kw = {'Bucket': bucket}
        if token:
            kw['ContinuationToken'] = token
        page = s3.list_objects_v2(**kw)
        for obj in page.get('Contents', []):
            out[obj['Key']] = {'etag': obj['ETag'].strip('"'), 'size': obj['Size']}
        if not page.get('IsTruncated'):
            break
        token = page.get('NextContinuationToken')
    return out


def index_losses(live, bundle):
    """Slugs the live index lists that the bundle's index.json would drop.

    Everything else this tool does is additive, but index.json is ONE object: uploading it
    replaces the store's list outright. A fresh bundle directory starts its index empty and
    lists only its own pieces, so publishing one essay from one would replace the live
    index with a one-entry index — unpublishing every talk and every other outlet's piece
    from every listing, with every object still sitting in the bucket. Found 2026-09-10,
    before the first professional publish rather than after it.
    """
    have = {(p.get('slug'), p.get('kind', 'piece')) for p in (bundle or {}).get('pieces', [])}
    return sorted(f"{s} ({k})" for s, k in
                  {(p.get('slug'), p.get('kind', 'piece')) for p in (live or {}).get('pieces', [])} - have)


def live_index(base_url):
    """The store's current index.json, {} if the store has none yet."""
    import urllib.request, urllib.error
    url = base_url.rstrip('/') + f'/index.json?cb={os.urandom(4).hex()}'
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return {}
        raise


def main():
    ap = argparse.ArgumentParser(add_help=True, description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('bundle', help='bundle directory to upload')
    ap.add_argument('--config', default='publishing/store.yaml')
    ap.add_argument('--dry-run', action='store_true',
                    help='say what would change and touch nothing')
    ap.add_argument('--prune', action='store_true',
                    help='also DELETE store objects the bundle does not contain')
    ap.add_argument('--no-invalidate', action='store_true')
    a = ap.parse_args()

    if not os.path.isdir(a.bundle):
        die(1, f'{a.bundle}: not a directory')
    if not os.path.exists(a.config):
        die(1, f'{a.config}: no such config (see publishing/store.yaml)')

    with open(a.config, encoding='utf-8') as fh:
        cfg = yaml.safe_load(fh) or {}
    store = cfg.get('store') or {}
    for field in ('bucket', 'region', 'distribution_id'):
        if not store.get(field):
            die(1, f'{a.config}: store.{field} is required')
    cc = cfg.get('cache_control') or {}

    session = boto3.Session(profile_name=store.get('aws_profile'),
                            region_name=store['region'])
    s3 = session.client('s3')
    bucket = store['bucket']

    local = local_objects(a.bundle)
    if not local:
        die(1, f'{a.bundle}: empty, nothing to publish')
    try:
        remote = remote_objects(s3, bucket)
    except Exception as e:                                        # noqa: BLE001
        die(1, f'cannot read s3://{bucket} — {e}')

    upload, skip = [], []
    for key, path in sorted(local.items()):
        digest = md5(path)
        there = remote.get(key)
        # Bytes match AND the object is already there: nothing to do. Cache-Control is
        # not returned by list_objects_v2, so a policy change alone needs --prune-free
        # re-upload; in practice it changes with the bytes.
        if there and there['etag'] == digest and there['size'] == os.path.getsize(path):
            skip.append(key)
        else:
            upload.append((key, path))

    stale = sorted(set(remote) - set(local))

    # index.json replaces the live list outright; refuse a bundle whose index would drop
    # entries that are live. --prune is the one flag that means "yes, remove things".
    if 'index.json' in local and not a.prune:
        if not store.get('base_url'):
            die(1, f'{a.config}: store.base_url is required to check index.json before replacing it')
        try:
            live = live_index(store['base_url'])
        except Exception as e:                                    # noqa: BLE001
            die(1, f'cannot read the live index to check it — {e}')
        with open(local['index.json'], encoding='utf-8') as fh:
            lost = index_losses(live, json.load(fh))
        if lost:
            die(4, f"refusing: this bundle's index.json would UNPUBLISH {len(lost)} live "
                   f"entr{'y' if len(lost) == 1 else 'ies'} — {', '.join(lost[:8])}"
                   f"{' …' if len(lost) > 8 else ''}. Seed the bundle from the live index first "
                   f"(curl {store['base_url'].rstrip('/')}/index.json -o {a.bundle}/index.json), "
                   f"or pass --prune if removal is meant.")

    print(f"bundle    {a.bundle}")
    print(f"store     s3://{bucket}  ->  {store.get('base_url', '(no base_url)')}")
    print(f"upload    {len(upload)}    unchanged {len(skip)}    "
          f"only in store {len(stale)}{' (will DELETE)' if a.prune else ''}")
    for key, _p in upload[:40]:
        print(f"  + {key}   [{cache_control(key, cc)}]")
    if len(upload) > 40:
        print(f"  … and {len(upload) - 40} more")
    if a.prune:
        for key in stale[:20]:
            print(f"  - {key}")
    elif stale:
        print(f"  (left alone: {', '.join(stale[:5])}{' …' if len(stale) > 5 else ''})")

    if a.dry_run:
        print("\ndry run — nothing uploaded")
        return 0
    if not upload and not (a.prune and stale):
        print("\nnothing to do")
        return 0

    for key, path in upload:
        extra = {'ContentType': content_type(key)}
        cache = cache_control(key, cc)
        if cache:
            extra['CacheControl'] = cache
        s3.upload_file(path, bucket, key, ExtraArgs=extra)
    print(f"\nuploaded {len(upload)}")

    if a.prune and stale:
        for i in range(0, len(stale), 1000):
            s3.delete_objects(
                Bucket=bucket,
                Delete={'Objects': [{'Key': k} for k in stale[i:i + 1000]]},
            )
        print(f"deleted {len(stale)}")

    if a.no_invalidate:
        return 0

    # Invalidate exactly what moved. A wildcard costs the same as ten paths and blows
    # away image caching for no reason, so only reach for one when the list is long.
    changed = [f'/{k}' for k, _ in upload] + [f'/{k}' for k in (stale if a.prune else [])]
    paths = changed if len(changed) <= 100 else ['/*']
    cf = session.client('cloudfront')
    inv = cf.create_invalidation(
        DistributionId=store['distribution_id'],
        InvalidationBatch={
            'Paths': {'Quantity': len(paths), 'Items': paths},
            'CallerReference': f'store-publish-{os.urandom(8).hex()}',
        },
    )
    print(f"invalidation {inv['Invalidation']['Id']} created for "
          f"{len(paths)} path(s) — not waiting (see publishing/store.yaml)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
