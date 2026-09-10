#!/usr/bin/env python3
"""
snapshot.py — take a complete, verified copy of the content store.

The store made publishing fast and made one host load-bearing. This is the way back:
a snapshot is a bundle on disk, in the form BUNDLE.md describes, holding everything
needed to rebuild the store or to vendor the corpus into a repo again.

  usage: python3 tools/snapshot.py <out-dir> [--config publishing/store.yaml]
                 [--outlet NAME] [--verify-only] [--push] [--list]

  OUT   <out>/bundle.json           spec, when, what is inside
        <out>/content/<slug>.md     front matter + markdown body
        <out>/images/<slug>/…       every picture a piece references
        <out>/talks/<slug>/…        deck.html, notes.json, deck-stage.js, assets

A DOWNLOAD IS NOT A SNAPSHOT. An archive nobody has checked is a promise, not a
backup, so this verifies as it goes and refuses to call the result complete unless:

  * every piece named in the index was fetched and parses;
  * the digest on the piece matches the digest in the index — two records of the same
    claim, written at different times, that must agree;
  * every image a piece references — hero, images[], and inline in the prose — is
    present on disk and non-empty;
  * every talk carries deck.html, notes.json, deck-stage.js and each asset its slides
    reference, with PNGs complete to their IEND chunk.

--push KEEPS IT OFF THIS MACHINE. A snapshot on the same laptop that runs the desk
survives a bad publish and nothing else, so `--push` copies the verified tree to a
second S3 bucket under a timestamped prefix. It is a different bucket from the store on
purpose: `store_publish.py --prune` deletes every object a bundle does not name, so a
snapshot kept beside the content would be destroyed by an ordinary publish — and a
backup sharing a bucket with its source dies with it. Nothing is pushed unless
verification passed; uploading an archive already known to be broken is worse than
having none, because it looks like one.

THE STORE CANNOT BE LISTED, ON PURPOSE. The CDN refuses a bucket listing, so this
cannot ask what is there; it discovers everything from index.json and from the files
themselves — a talk's assets by reading its deck. Anything the index does not name is
invisible here, which is the same rule the sites read by.
"""

import argparse
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, date

try:
    import yaml
except ImportError:
    print("error: missing dependency (yaml); pip install pyyaml", file=sys.stderr)
    sys.exit(2)


def die(code, msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
# The order BUNDLE.md documents. Kept explicit so a snapshot diffs cleanly against the
# bundle it came from rather than against yaml's idea of alphabetical.
FIELD_ORDER = ['slug', 'source_slug', 'title', 'subtitle', 'published_at', 'footnotes',
               'canonical', 'syndicated', 'hero', 'images', 'digest']


def fetch(url, binary=False):
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        return None, f'{e.code}'
    except Exception as e:                                        # noqa: BLE001
        return None, str(e)
    return (data if binary else data.decode('utf-8')), None


def image_refs(piece):
    """Every image a piece points at: hero, the images list, and inline in the prose."""
    refs = []
    hero = piece.get('hero') or {}
    if hero.get('src'):
        refs.append(hero['src'])
    for img in piece.get('images') or []:
        if img.get('src'):
            refs.append(img['src'])
    refs += re.findall(r'!\[[^\]]*\]\(([^)\s]+)', piece.get('body') or '')
    out, seen = [], set()
    for r in refs:
        key = r.lstrip('/').removeprefix('../')
        if key.startswith('images/') and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def write_piece_md(path, piece):
    """Back to front matter + markdown — the form a human reads and a diff shows."""
    meta = {}
    for k in FIELD_ORDER:
        if k == 'digest' or piece.get(k) not in (None, '', [], {}):
            if k in piece:
                meta[k] = piece[k]
    # A bare YYYY-MM-DD rather than a quoted string, matching the exporter's output.
    if isinstance(meta.get('published_at'), str):
        try:
            meta['published_at'] = date.fromisoformat(meta['published_at'][:10])
        except ValueError:
            pass
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=110)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('---\n' + head + '---\n\n' + (piece.get('body') or ''))


def check_file(path):
    """Present, non-empty, and — if it claims to be a PNG — not truncated."""
    if not os.path.exists(path):
        return 'missing'
    if os.path.getsize(path) == 0:
        return 'empty'
    if path.lower().endswith('.png'):
        with open(path, 'rb') as fh:
            buf = fh.read()
        if buf[:8] != PNG_MAGIC:
            return 'not a PNG'
        if buf[-8:-4] != b'IEND':
            return 'truncated (no IEND)'
    return None


def snapshot_bucket(cfg):
    b = (cfg.get('snapshots') or {}).get('bucket')
    if not b:
        die(1, 'snapshots.bucket is not set in the config')
    return b


def s3_client(cfg):
    try:
        import boto3
    except ImportError:
        die(2, 'missing dependency (boto3); pip install boto3')
    store = cfg.get('store') or {}
    return boto3.Session(profile_name=store.get('aws_profile'),
                         region_name=store.get('region', 'us-east-1')).client('s3')


def push(cfg, out, outlet):
    """Copy a VERIFIED snapshot to the snapshot bucket, under a timestamped prefix.

    Every snapshot is uploaded whole rather than diffed against the last one. At this
    size that costs pennies, and it buys the property a backup needs most: each prefix
    stands alone, so restoring never means reassembling one snapshot out of several.
    """
    bucket = snapshot_bucket(cfg)
    s3 = s3_client(cfg)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')
    prefix = f'{stamp}-{outlet}' if outlet else stamp

    n = size = 0
    for root, _dirs, files in os.walk(out):
        for name in files:
            if name == '.DS_Store':
                continue
            path = os.path.join(root, name)
            key = f'{prefix}/' + os.path.relpath(path, out).replace(os.sep, '/')
            s3.upload_file(path, bucket, key)
            n += 1
            size += os.path.getsize(path)
    print(f"pushed    s3://{bucket}/{prefix}/ — {n} file(s), {size / 1e6:.1f} MB")
    return 0


def list_snapshots(cfg):
    """What has been pushed. The snapshot bucket is private and has no CDN in front of
    it, so unlike the store it can simply be listed."""
    bucket = snapshot_bucket(cfg)
    s3 = s3_client(cfg)
    seen = {}
    token = None
    while True:
        kw = {'Bucket': bucket, 'Delimiter': '/'}
        if token:
            kw['ContinuationToken'] = token
        page = s3.list_objects_v2(**kw)
        for p in page.get('CommonPrefixes', []):
            seen[p['Prefix'].rstrip('/')] = [0, 0]
        if not page.get('IsTruncated'):
            break
        token = page.get('NextContinuationToken')
    if not seen:
        print(f's3://{bucket}/ — no snapshots yet')
        return 0
    for prefix in sorted(seen):
        token = None
        while True:
            kw = {'Bucket': bucket, 'Prefix': prefix + '/'}
            if token:
                kw['ContinuationToken'] = token
            page = s3.list_objects_v2(**kw)
            for obj in page.get('Contents', []):
                seen[prefix][0] += 1
                seen[prefix][1] += obj['Size']
            if not page.get('IsTruncated'):
                break
            token = page.get('NextContinuationToken')
    print(f's3://{bucket}/ — {len(seen)} snapshot(s)')
    for prefix in sorted(seen, reverse=True):
        n, size = seen[prefix]
        print(f'  {prefix}   {n} file(s)   {size / 1e6:.1f} MB')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('out', help='directory to write the snapshot into')
    ap.add_argument('--config', default='publishing/store.yaml')
    ap.add_argument('--outlet', help='only pieces published to this outlet')
    ap.add_argument('--verify-only', action='store_true',
                    help='re-check an existing snapshot without downloading')
    ap.add_argument('--push', action='store_true',
                    help='after verifying, copy the snapshot to the snapshot bucket')
    ap.add_argument('--list', action='store_true',
                    help='list the snapshots already pushed, newest first')
    a = ap.parse_args()

    if not os.path.exists(a.config):
        die(1, f'{a.config}: no such config')
    with open(a.config, encoding='utf-8') as fh:
        cfg = yaml.safe_load(fh) or {}
    base = ((cfg.get('store') or {}).get('base_url') or '').rstrip('/')
    if not base:
        die(1, f'{a.config}: store.base_url is required')

    if a.list:
        return list_snapshots(cfg)

    faults = []
    if a.verify_only:
        index_path = os.path.join(a.out, 'bundle.json')
        if not os.path.exists(index_path):
            die(1, f'{a.out}: not a snapshot (no bundle.json)')
        with open(index_path, encoding='utf-8') as fh:
            manifest = json.load(fh)
        entries = manifest.get('pieces', [])
        print(f"verifying {a.out} — {len(entries)} piece(s)")
    else:
        raw, err = fetch(f'{base}/index.json')
        if err:
            die(1, f'{base}/index.json — {err}')
        index = json.loads(raw)
        entries = index.get('pieces', [])
        if a.outlet:
            entries = [e for e in entries if a.outlet in (e.get('outlets') or [])]
        if not entries:
            die(1, 'index names no pieces' + (f' for {a.outlet}' if a.outlet else ''))
        print(f"store  {base}")
        print(f"index  {len(index.get('pieces', []))} piece(s)"
              + (f", {len(entries)} for {a.outlet}" if a.outlet else ''))
        for d in ('content', 'images', 'talks'):
            os.makedirs(os.path.join(a.out, d), exist_ok=True)

    n_img = n_talk = n_asset = 0
    manifest_pieces = []

    for entry in entries:
        slug = entry['slug']
        md_path = os.path.join(a.out, 'content', f'{slug}.md')

        if a.verify_only:
            if not os.path.exists(md_path):
                faults.append(f'{slug}: content/{slug}.md missing')
                continue
            with open(md_path, encoding='utf-8') as fh:
                text = fh.read()
            end = text.find('\n---', 3)
            meta = yaml.safe_load(text[3:end]) or {}
            piece = dict(meta)
            piece['body'] = text[end + 4:].lstrip('\n')
        else:
            raw, err = fetch(f'{base}/pieces/{slug}.json')
            if err:
                faults.append(f'{slug}: pieces/{slug}.json — {err}')
                continue
            try:
                piece = json.loads(raw)
            except json.JSONDecodeError as e:
                faults.append(f'{slug}: malformed JSON — {e}')
                continue
            write_piece_md(md_path, piece)

        # Two records of the same claim, written at different times. They must agree.
        if piece.get('digest') != entry.get('digest'):
            faults.append(f"{slug}: digest disagrees — index {entry.get('digest')} "
                          f"vs piece {piece.get('digest')}")

        for ref in image_refs(piece):
            dest = os.path.join(a.out, ref)
            if not a.verify_only:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                data, err = fetch(f'{base}/{ref}', binary=True)
                if err:
                    faults.append(f'{slug}: {ref} — {err}')
                    continue
                with open(dest, 'wb') as fh:
                    fh.write(data)
            bad = check_file(dest)
            if bad:
                faults.append(f'{slug}: {ref} — {bad}')
            else:
                n_img += 1

        if entry.get('kind') == 'talk' or piece.get('talk'):
            n_talk += 1
            tdir = os.path.join(a.out, 'talks', slug)
            if not a.verify_only:
                os.makedirs(os.path.join(tdir, 'assets'), exist_ok=True)
            deck_html = None
            for name in ('deck.html', 'notes.json', 'deck-stage.js'):
                dest = os.path.join(tdir, name)
                if not a.verify_only:
                    data, err = fetch(f'{base}/talks/{slug}/{name}', binary=True)
                    if err:
                        faults.append(f'{slug}: talks/{slug}/{name} — {err}')
                        continue
                    with open(dest, 'wb') as fh:
                        fh.write(data)
                bad = check_file(dest)
                if bad:
                    faults.append(f'{slug}: talks/{slug}/{name} — {bad}')
                if name == 'deck.html' and os.path.exists(dest):
                    with open(dest, encoding='utf-8') as fh:
                        deck_html = fh.read()
            # The store cannot be listed, so the deck itself says what it needs.
            for asset in sorted(set(re.findall(r'src="assets/([^"]+)"', deck_html or ''))):
                dest = os.path.join(tdir, 'assets', asset)
                if not a.verify_only:
                    data, err = fetch(f'{base}/talks/{slug}/assets/{asset}', binary=True)
                    if err:
                        faults.append(f'{slug}: talks/{slug}/assets/{asset} — {err}')
                        continue
                    with open(dest, 'wb') as fh:
                        fh.write(data)
                bad = check_file(dest)
                if bad:
                    faults.append(f'{slug}: assets/{asset} — {bad}')
                else:
                    n_asset += 1

        manifest_pieces.append({k: entry[k] for k in
                                ('slug', 'title', 'published_at', 'digest', 'outlets', 'kind')
                                if k in entry})

    if not a.verify_only:
        with open(os.path.join(a.out, 'bundle.json'), 'w', encoding='utf-8') as fh:
            json.dump({
                'bundle_spec': '2',
                'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'source': base,
                'outlet': a.outlet,
                'pieces': manifest_pieces,
            }, fh, indent=2, ensure_ascii=False)
            fh.write('\n')

    verb = 'verified' if a.verify_only else 'snapshot'
    print(f"{verb}  {len(entries)} piece(s), {n_img} image(s), "
          f"{n_talk} talk(s) with {n_asset} asset(s)")
    if faults:
        print(f"INCOMPLETE — {len(faults)} fault(s):", file=sys.stderr)
        for f in faults[:20]:
            print(f'  {f}', file=sys.stderr)
        if len(faults) > 20:
            print(f'  … and {len(faults) - 20} more', file=sys.stderr)
        return 1
    print("complete — every piece, image and asset the index names is present and intact")

    if a.push:
        return push(cfg, a.out, a.outlet)
    return 0


if __name__ == '__main__':
    sys.exit(main())
