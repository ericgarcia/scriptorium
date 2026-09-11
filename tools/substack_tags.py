#!/usr/bin/env python3
"""substack_tags.py — put a piece's tags on its Substack post.

WHY THIS EXISTS (2026-09-11).  Tags live on the desk (tags.py) and reach the web outlets
through the content bundle. Substack has no write API, so a post's tags were a composer-UI
action nobody would repeat forty times by hand. Measured on post 214607357 (a private
draft) by watching the editor add one tag, then reading the calls it made:

    GET  /api/v1/publication/post-tag               -> [{id, name, slug, hidden, publication_id}]
    POST /api/v1/publication/post-tag   {"name"}    -> {id, name, slug, hidden, publication_id}
    GET  /api/v1/post/<id>/tag                      -> [{id, post_id, post_tag_id, publication_id}]
    POST /api/v1/post/<id>/tag/<post_tag_id>        -> {id, post_id, post_tag_id, publication_id}

A tag is a PUBLICATION object (created once, then reused) and a post carries join records
to it. None of it is in the draft document — GET /api/v1/drafts/<id> carries no tags — so
setting them never touches the body. Substack derives the slug from the name: "Idolatry"
became `idolatry`, the same id the desk uses.

The create call's request body was read off its response and CONFIRMED by the first automated
run, the same day on the same draft: `{"name": "Discernment"}` and `{"name": "Other
Traditions"}` came back as tags with slugs `discernment` and `other-traditions` — the desk's ids.
The snippet still checks the name that comes back and stops if it ever differs.

WHAT THIS EMITS
    A self-contained JS snippet that reads the publication's tags and the post's, creates only
    the names the publication lacks, attaches only the tags the post lacks, reads the post back,
    and returns {wanted, created, attached, now, missing, extra, ok}. Run it twice and the
    second run does nothing.

    RUN IT ON THE PUBLICATION'S ORIGIN, BUT NOT IN THAT POST'S EDITOR — the dashboard
    (/publish/home) is right. The publish skill's guardrail is that nothing writes behind a
    composer that holds the post; the tag calls are not the draft document, but the rule is
    kept rather than argued with. The snippet refuses to run on /publish/post/<this id>.

    ADDITIVE ONLY. A tag on the post that the desk does not list is REPORTED as `extra` and
    left alone: how a tag is detached was not measured, and a tool that removes what it does
    not understand is how a hand-made choice gets wiped.

WHAT GOES
    The piece's tags, named by their vocabulary LABELS (the name Substack shows), in vocabulary
    order. A vocabulary entry with `substack: false` stays on the desk and the sites and is
    never sent — a membership tag such as a founding canon, which says where a piece belongs
    rather than what it is about.

A LIVE POST IS A PUBLIC EDIT. Tags show on the post. When publish.yaml records `published_at`
the tool refuses without --live, which is the author's word, not a default.

USAGE
    python3 framework/tools/substack_tags.py pieces/<slug> [--out tags.js] [--live]
    python3 framework/tools/substack_tags.py pieces/<slug> --verify
        (a LIVE post only: fetch the public post and compare its postTags to the desk)

EXIT  0 ok | 1 --verify found a difference | 3 refused
"""
import os, re, sys, json, argparse, urllib.request

import publications as pb
import tags as tg

POST_ID = re.compile(r'/publish/post/(\d+)')
UA = 'Mozilla/5.0 (desk substack_tags)'


def plan(pdir):
    """-> dict(post, host, labels, skipped, live, public_url). Raises pb.Refused."""
    root = pb.instance_root(pdir)
    pubs, probs = pb.load(root)
    if probs:
        raise pb.Refused('fix the publication registry first: ' + '; '.join(probs))
    man = pb.read_manifest(pdir)
    slug = os.path.basename(os.path.normpath(pdir))
    if man is None:
        raise pb.Refused(f'{slug} has no publish.yaml')
    names, problem = tg.tags_of(man)
    if problem:
        raise pb.Refused(f'{slug}: {problem}')
    if not names:
        raise pb.Refused(f'{slug} carries no tags — nothing to send (tags.py add, or the tags skill)')
    pid, pprobs = pb.of_piece(man, pubs)
    if pprobs:
        raise pb.Refused(f'{slug}: ' + '; '.join(pprobs))
    vocab, vprobs = tg.Vocabularies(root, None, pubs).get(pid)
    if vprobs or vocab is None:
        raise pb.Refused(f'{slug}: its tag vocabulary is missing or malformed ' + '; '.join(vprobs))
    unknown = [t for t in names if t not in vocab]
    if unknown:
        raise pb.Refused(f"{slug}: not in its vocabulary: {', '.join(unknown)} — run tags.py check")
    m = POST_ID.search(str(man.get('post_url') or ''))
    if not m:
        raise pb.Refused(f'{slug}: no post_url (…/publish/post/<id>) in publish.yaml — compose the '
                         f'post first; a tag needs a post to go on')
    ordered = tg.ordered(names, vocab)
    return {'slug': slug, 'post': int(m.group(1)),
            'host': re.match(r'(https?://[^/]+)', man['post_url']).group(1),
            'labels': [vocab[t]['label'] for t in ordered if vocab[t]['substack']],
            'skipped': [t for t in ordered if not vocab[t]['substack']],
            'live': bool(man.get('published_at')), 'public_url': man.get('public_url')}


SNIPPET = r'''// substack_tags.py — tags for post __POST__ (__SLUG__). Run on the publication's origin,
// NOT in this post's editor. Additive: creates missing tags, attaches missing ones, removes nothing.
const WANT = __WANT__;
const POST = __POST__;
if (location.pathname.startsWith('/publish/post/' + POST))
  throw new Error('refusing: this is the editor holding post ' + POST + ' — run from /publish/home');
const api = async (method, path, body) => {
  const r = await fetch(path, { method, credentials: 'include',
    headers: body ? { 'content-type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined });
  const text = await r.text();
  let data; try { data = JSON.parse(text); } catch (e) { data = text; }
  if (!r.ok) throw new Error(method + ' ' + path + ' -> ' + r.status + ' ' + String(text).slice(0, 200));
  return data;
};
const norm = (s) => String(s).trim().toLowerCase();
const byName = new Map((await api('GET', '/api/v1/publication/post-tag')).map((t) => [norm(t.name), t]));
const created = [];
for (const name of WANT) {
  if (byName.has(norm(name))) continue;
  const t = await api('POST', '/api/v1/publication/post-tag', { name });
  if (!t || norm(t.name) !== norm(name)) throw new Error('created tag came back as ' + JSON.stringify(t) + ', not ' + name);
  byName.set(norm(name), t); created.push(t.name);
}
const has = new Set((await api('GET', '/api/v1/post/' + POST + '/tag')).map((x) => x.post_tag_id));
const attached = [];
for (const name of WANT) {
  const t = byName.get(norm(name));
  if (has.has(t.id)) continue;
  await api('POST', '/api/v1/post/' + POST + '/tag/' + t.id);
  attached.push(t.name);
}
const idName = new Map((await api('GET', '/api/v1/publication/post-tag')).map((t) => [t.id, t.name]));
const now = (await api('GET', '/api/v1/post/' + POST + '/tag')).map((x) => idName.get(x.post_tag_id) || x.post_tag_id);
const missing = WANT.filter((n) => !now.map(norm).includes(norm(n)));
const extra = now.filter((n) => !WANT.map(norm).includes(norm(n)));
const result = { post: POST, wanted: WANT, created, attached, now, missing, extra, ok: missing.length === 0 };
JSON.stringify(result);
'''


def snippet(p):
    return (SNIPPET.replace('__WANT__', json.dumps(p['labels'], ensure_ascii=False))
                   .replace('__POST__', str(p['post'])).replace('__SLUG__', p['slug']))


def public_tags(host, public_url):
    """Names on a LIVE post, from the public post JSON (no sign-in needed)."""
    m = re.search(r'/p/([^/?#]+)', str(public_url or ''))
    if not m:
        raise pb.Refused('no public_url (…/p/<slug>) to verify against')
    req = urllib.request.Request(f'{host}/api/v1/posts/{m.group(1)}?cb={os.urandom(3).hex()}',
                                 headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    return [t.get('name') if isinstance(t, dict) else str(t) for t in data.get('postTags') or []]


def main(argv=None):
    ap = argparse.ArgumentParser(prog='substack_tags.py', description=__doc__.split('\n')[0])
    ap.add_argument('piece')
    ap.add_argument('--out')
    ap.add_argument('--live', action='store_true', help="the author's word: tag an already-live post")
    ap.add_argument('--verify', action='store_true')
    a = ap.parse_args(argv)
    try:
        p = plan(a.piece)
        if a.verify:
            if not p['live']:
                raise pb.Refused('--verify reads the PUBLIC post; this one is not live. Read a draft '
                                 'back in the page — the snippet returns the post\'s tags itself.')
            now = public_tags(p['host'], p['public_url'])
            missing = [n for n in p['labels'] if n.lower() not in {x.lower() for x in now}]
            print(f"{p['slug']}: live post carries {now or '(none)'}")
            if missing:
                print(f"  MISSING on Substack: {', '.join(missing)}")
            return 1 if missing else 0
        if p['live'] and not a.live:
            raise pb.Refused(f"{p['slug']} is LIVE: tags show on the post, so this is a public edit. "
                             f"Pass --live on the author's word.")
        js = snippet(p)
        if a.out:
            open(a.out, 'w').write(js)
        else:
            print(js)
        print(f"{p['slug']}: post {p['post']} <- {', '.join(p['labels'])}"
              + (f"   (not sent: {', '.join(p['skipped'])})" if p['skipped'] else '')
              + ('   [LIVE]' if p['live'] else ''), file=sys.stderr)
        return 0
    except pb.Refused as e:
        print(f'refused: {e}', file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main())
