#!/usr/bin/env python3
"""substack_tags.py — put pieces' tags on their Substack posts.

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
    A self-contained JS snippet for ONE OR MANY pieces. It carries a PLAN — [{slug, post,
    want}] — and the SHA-256 of that plan, and before writing anything it hashes the plan it
    is holding and refuses on a mismatch. The plan is what gets carried into a page by hand or
    by tool, and a label altered in transit would otherwise be CREATED as a new publication tag
    — a typo made public — so the checksum is the gate, the way the publish skill hashes a
    carried payload before executing it.

    Then, per post: create only the names the publication lacks, attach only the tags the post
    lacks; finally read every post back and return {ok, posts, created, results[]}, each result
    {slug, post, created, attached, now, missing, extra, ok}. Run it twice and the second run
    does nothing.

    RUN IT ON THE PUBLICATION'S ORIGIN, BUT NOT IN ANY LISTED POST'S EDITOR — the dashboard
    (/publish/home) is right. The publish skill's guardrail is that nothing writes behind a
    composer that holds the post; the tag calls are not the draft document, but the rule is
    kept rather than argued with. The snippet refuses to run on /publish/post/<a listed id>.

    ADDITIVE ONLY. A tag on a post that the desk does not list is REPORTED as `extra` and left
    alone: how a tag is detached was not measured, and a tool that removes what it does not
    understand is how a hand-made choice gets wiped.

WHAT GOES
    Each piece's tags, named by their vocabulary LABELS (the name Substack shows), in vocabulary
    order. A vocabulary entry with `substack: false` stays on the desk and the sites and is
    never sent — a membership tag such as a founding canon, which says where a piece belongs
    rather than what it is about.

A LIVE POST IS A PUBLIC EDIT: the public post JSON carries `postTags`. When publish.yaml records
`published_at` the tool refuses without --live, which is the author's word, not a default.

USAGE
    python3 framework/tools/substack_tags.py pieces/<slug>... [--out tags.js] [--live]
    python3 framework/tools/substack_tags.py pieces/<slug>... --verify
        (LIVE posts only: fetch each public post and compare its postTags to the desk)

EXIT  0 ok | 1 --verify found a difference | 3 refused
"""
import os, re, sys, json, hashlib, argparse, urllib.request

import publications as pb
import tags as tg

POST_ID = re.compile(r'/publish/post/(\d+)')
UA = 'Mozilla/5.0 (desk substack_tags)'


def plan(pdir):
    """-> dict(slug, post, host, labels, skipped, live, public_url). Raises pb.Refused."""
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


def plan_json(plans):
    """The plan as the snippet carries it — and the exact bytes its checksum is taken over.
    JSON.stringify of the parsed literal reproduces this string, so the page can re-hash it."""
    return json.dumps([{'slug': p['slug'], 'post': p['post'], 'want': p['labels']} for p in plans],
                      ensure_ascii=False, separators=(',', ':'))


SNIPPET = r'''// substack_tags.py — tags for __N__ post(s). Run on the publication's origin, NOT in a listed
// post's editor. Additive: creates missing tags, attaches missing ones, removes nothing.
const PLAN = __PLAN__;
const PLAN_SHA256 = '__SHA__';
const sha = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',
  new TextEncoder().encode(JSON.stringify(PLAN))))).map((b) => b.toString(16).padStart(2, '0')).join('');
if (sha !== PLAN_SHA256) throw new Error('refusing: the plan does not match its checksum (' + sha + ') — altered in transit; nothing written');
if (PLAN.some((p) => location.pathname.startsWith('/publish/post/' + p.post)))
  throw new Error('refusing: this is the editor holding a listed post — run from /publish/home');
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
const results = [];
for (const { slug, post, want } of PLAN) {
  const created = [], attached = [];
  for (const name of want) {
    if (byName.has(norm(name))) continue;
    const t = await api('POST', '/api/v1/publication/post-tag', { name });
    if (!t || norm(t.name) !== norm(name)) throw new Error('created tag came back as ' + JSON.stringify(t) + ', not ' + name);
    byName.set(norm(name), t); created.push(t.name);
  }
  const has = new Set((await api('GET', '/api/v1/post/' + post + '/tag')).map((x) => x.post_tag_id));
  for (const name of want) {
    const t = byName.get(norm(name));
    if (has.has(t.id)) continue;
    await api('POST', '/api/v1/post/' + post + '/tag/' + t.id);
    attached.push(t.name);
  }
  results.push({ slug, post, want, created, attached });
}
const idName = new Map((await api('GET', '/api/v1/publication/post-tag')).map((t) => [t.id, t.name]));
for (const r of results) {
  r.now = (await api('GET', '/api/v1/post/' + r.post + '/tag')).map((x) => idName.get(x.post_tag_id) || x.post_tag_id);
  r.missing = r.want.filter((n) => !r.now.map(norm).includes(norm(n)));
  r.extra = r.now.filter((n) => !r.want.map(norm).includes(norm(n)));
  r.ok = r.missing.length === 0;
  delete r.want;
}
const result = { ok: results.every((r) => r.ok), posts: results.length,
  created: results.flatMap((r) => r.created), results };
JSON.stringify(result);
'''


def snippet(plans):
    if isinstance(plans, dict):
        plans = [plans]
    pj = plan_json(plans)
    return (SNIPPET.replace('__PLAN__', pj).replace('__N__', str(len(plans)))
                   .replace('__SHA__', hashlib.sha256(pj.encode('utf-8')).hexdigest()))


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
    ap.add_argument('pieces', nargs='+')
    ap.add_argument('--out')
    ap.add_argument('--live', action='store_true', help="the author's word: tag already-live posts")
    ap.add_argument('--verify', action='store_true')
    a = ap.parse_args(argv)
    try:
        plans = [plan(d) for d in a.pieces]
        if a.verify:
            bad = 0
            for p in plans:
                if not p['live']:
                    raise pb.Refused(f"{p['slug']}: --verify reads the PUBLIC post, and this one is not live. "
                                     f"Read a draft back in the page — the snippet returns its tags itself.")
                now = public_tags(p['host'], p['public_url'])
                missing = [n for n in p['labels'] if n.lower() not in {x.lower() for x in now}]
                extra = [n for n in now if n.lower() not in {x.lower() for x in p['labels']}]
                bad += bool(missing)
                print(f"{'ok  ' if not missing else 'FAIL'}  {p['slug']:36} {', '.join(now) or '(none)'}"
                      + (f"   MISSING {', '.join(missing)}" if missing else '')
                      + (f"   extra {', '.join(extra)}" if extra else ''))
            return 1 if bad else 0
        live = [p['slug'] for p in plans if p['live']]
        if live and not a.live:
            raise pb.Refused(f"LIVE: {', '.join(live)}. Tags on a live post are a public edit; pass --live "
                             f"on the author's word.")
        js = snippet(plans)
        if a.out:
            open(a.out, 'w').write(js)
        else:
            print(js)
        for p in plans:
            print(f"{p['slug']}: post {p['post']} <- {', '.join(p['labels'])}"
                  + (f"   (not sent: {', '.join(p['skipped'])})" if p['skipped'] else '')
                  + ('   [LIVE]' if p['live'] else ''), file=sys.stderr)
        print(f"plan sha256 {hashlib.sha256(plan_json(plans).encode()).hexdigest()}", file=sys.stderr)
        return 0
    except pb.Refused as e:
        print(f'refused: {e}', file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main())
