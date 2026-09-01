#!/usr/bin/env python3
"""
substack_sync.py — two-way sync between a piece's draft.md and its LIVE Substack post,
with real conflict detection.

WHY THIS EXISTS (and why it is not just "repatch, but both ways")

  substack_repatch.py pushes draft -> live and is deliberately stateless: it diffs the
  draft against the live post scraped at run time. That is sound for a one-way push, and
  unsound the moment edits can originate on BOTH sides. A bare two-way difference cannot
  tell you WHICH side moved: draft-changed and live-changed look identical.

  Real case (2026-09-01). `Nothing to Get` read "is this for us" in the draft and "is this
  for me" live — the phrase entered at the compose commit and was never touched since, so
  the edit was made in Substack. `I Believe in You` had its subtitle capitalized in
  Substack, while publish.yaml still held the lowercase form. A stateless push would have
  silently reverted both, and reported success.

  So sync is THREE-way. Baseline B (what was last known synced), draft D, live L:

      D == B, L != B     -> PULL   (only Substack moved; bring it into draft.md)
      D != B, L == B     -> PUSH   (only the draft moved; the ordinary re-sync)
      D != B, L != B, D == L -> CONVERGED (both made the same edit; nothing to do)
      D != B, L != B, D != L -> CONFLICT (stop; a human decides)
      D == B, L == B     -> unchanged

  Conflicts should be exceedingly rare — they need the same block edited on both sides
  between syncs. Rare is not never, and the whole point of the baseline is that when one
  does happen it is reported instead of silently resolved in whichever direction the tool
  happened to run.

THE BASELINE

  `<piece>/sync-baseline.json` — HASHES ONLY (sha256/16 of the flattened reader-text),
  never the text itself. Two reasons: the file stays a couple of KB next to a 40 KB draft,
  and the text is already in draft.md, which is the point. Hashes are enough to CLASSIFY
  every block; the text needed to RESOLVE a pull is fetched from the live post, and only
  for the handful of blocks that actually need it.

  It is a committed file. It records what was last synced, so it belongs in history beside
  the draft it describes.

PHASES (each browser step is one JS eval in the live post's editor)

  1. scan   <piece> <out.js>                   -> JS returning title/subtitle + hashes
  2. plan   <piece> <live.json>                -> classify every block; write plan.json
  3. fetch  <piece> <plan.json> <out.js>       -> JS returning live TEXT for pull rows only
  4. pull   <piece> <plan.json> <live-text.json>  -> write those edits into draft.md
  5. (push) python3 substack_repatch.py <piece> push.js  -> the ordinary hardened push
  6. seal   <piece> <live.json>                -> record the new baseline once both agree

  seed <piece> --from-git REV | --from-draft | --from-live <live.json>
       establishes a first baseline for a piece published before sync existed.
       --from-git is the honest one: render draft.md as it stood at the commit the piece
       was composed from, which IS what was pushed.

SCOPE LIMIT (deliberate)

  Structural divergence — a block or footnote added, removed or reordered on either side —
  is DESCRIBED precisely and never auto-merged. Same guardrail as substack_repatch.py: a
  live public essay is not the place for a machine to guess at a paragraph it invented or
  dropped. `plan` names the block and the side; a human resolves it.

Never publishes, never clicks. Every phase leaves the decision with a person.
"""
import sys, os, re, json, hashlib, subprocess, tempfile, shutil, difflib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from md_to_substack import (render_reader, read_manifest, flatten_quotes,
                            render_block, render_footnote_block, strip_to_reader)
from substack_repatch import JS_HELPERS

BASELINE = 'sync-baseline.json'


def H(s):
    """Hash of the comparison domain: flattened (straight-quoted) reader-text."""
    return hashlib.sha256(flatten_quotes(s).encode('utf-8')).hexdigest()[:16]


def draft_state(piece_dir):
    body, fns, residual, fn_issues = render_reader(piece_dir)
    man = read_manifest(os.path.join(piece_dir, 'publish.yaml'))
    return {
        'title': man.get('title', ''), 'subtitle': man.get('subtitle', ''),
        'body': body, 'fns': fns, 'residual': residual, 'fn_issues': fn_issues,
        'post_url': man.get('post_url', ''),
    }


def load_baseline(piece_dir):
    p = os.path.join(piece_dir, BASELINE)
    return json.load(open(p)) if os.path.exists(p) else None


def write_baseline(piece_dir, title, subtitle, body_h, fns_h, note):
    p = os.path.join(piece_dir, BASELINE)
    json.dump({
        'note': note,
        'title': H(title), 'subtitle': H(subtitle),
        'body': body_h, 'fns': fns_h,
    }, open(p, 'w'), indent=1)
    return p


# ---------------------------------------------------------------- alignment

def align(base, side):
    """LCS-align a side's hash list against the baseline's.
    Returns (pairs, added, removed): pairs are (base_idx, side_idx) for matched rows,
    added are side indices with no baseline counterpart, removed are the converse."""
    sm = difflib.SequenceMatcher(a=base, b=side, autojunk=False)
    pairs, added, removed = [], [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            pairs += [(i1 + k, j1 + k) for k in range(i2 - i1)]
        elif tag == 'replace':
            # a same-length replace is an EDIT of those rows, not a structural change:
            # pair them up so the three-way can classify each one.
            if (i2 - i1) == (j2 - j1):
                pairs += [(i1 + k, j1 + k) for k in range(i2 - i1)]
            else:
                removed += list(range(i1, i2))
                added += list(range(j1, j2))
        elif tag == 'delete':
            removed += list(range(i1, i2))
        elif tag == 'insert':
            added += list(range(j1, j2))
    return pairs, added, removed


def three_way(kind, base_h, draft_h, live_h, draft_texts=None):
    """Classify every row of one list (body or footnotes) against the baseline.
    Takes HASH lists for all three sides — at plan time the live side is hashes only,
    which is the whole point: classification never needs the live text, and the text
    for the few rows that do need it is fetched afterwards.
    Returns (rows, structural)."""
    d_pairs, d_added, d_removed = align(base_h, draft_h)
    l_pairs, l_added, l_removed = align(base_h, live_h)
    d_of = dict(d_pairs)
    l_of = dict(l_pairs)

    rows, structural = [], []
    for bi in range(len(base_h)):
        di, li = d_of.get(bi), l_of.get(bi)
        if di is None or li is None:
            structural.append({'kind': kind, 'baseIdx': bi,
                               'side': 'draft' if di is None else 'live',
                               'what': 'block present at last sync is gone'})
            continue
        b, d, l = base_h[bi], draft_h[di], live_h[li]
        if d == b and l == b:
            state = 'unchanged'
        elif d != b and l == b:
            state = 'push'
        elif d == b and l != b:
            state = 'pull'
        elif d == l:
            state = 'converged'
        else:
            state = 'conflict'
        rows.append({'kind': kind, 'baseIdx': bi, 'draftIdx': di, 'liveIdx': li, 'state': state})

    for j in d_added:
        structural.append({'kind': kind, 'side': 'draft', 'draftIdx': j,
                           'what': 'block added since last sync',
                           'text': (draft_texts[j][:110] if draft_texts else '')})
    for j in l_added:
        # live text is not in hand at plan time; the index is enough to go look
        structural.append({'kind': kind, 'side': 'live', 'liveIdx': j,
                           'what': 'block added since last sync', 'text': ''})
    return rows, structural


# ---------------------------------------------------------------- pull into draft.md

def reader_to_source_map(block_src, reader_text):
    """reader-offset -> source-offset, for one block.

    The reader-text is the block with markdown deleted and whitespace collapsed, so it is
    very nearly a subsequence of the source. difflib's matching blocks give the alignment
    directly, which beats trying to re-derive it by parsing: it needs no knowledge of which
    syntax produced which character, and it degrades into "unmapped" rather than into a
    wrong offset."""
    # Newlines are the one systematic difference: strip_to_reader turns each into a space.
    # Swapping them 1:1 (same length, so offsets stay valid against the real source) lets
    # whitespace align exactly instead of showing up as a gap in every wrapped line.
    flat_src = block_src.replace('\n', ' ')
    m = [None] * (len(reader_text) + 1)
    for i, j, n in difflib.SequenceMatcher(a=flat_src, b=reader_text,
                                           autojunk=False).get_matching_blocks():
        for k in range(n):
            m[j + k] = i + k
    m[len(reader_text)] = len(block_src)
    # fill gaps (reader chars with no source counterpart) by taking the next known anchor
    nxt = len(block_src)
    for j in range(len(reader_text), -1, -1):
        if m[j] is None:
            m[j] = nxt
        else:
            nxt = m[j]
    return m


def edit_block_source(block_src, old_reader, new_reader, piece_dir, kind='body'):
    """Rewrite one block's markdown so its reader-text becomes `new_reader`, changing only
    the runs that differ and leaving emphasis, links and footnote markers alone.

    Verified end-to-end rather than trusted: the edited source is re-rendered and its
    reader-text compared to what was asked for. An offset map that slipped — the run
    straddled a `*`, a link, a footnote marker — fails this check and the caller is told to
    do it by hand. Returns (new_src, note) with new_src None on refusal."""
    hunks = [(j1, j2, new_reader[k1:k2])
             for tag, j1, j2, k1, k2 in _opcodes(old_reader, new_reader) if tag != 'equal']
    if not hunks:
        return block_src, 'no change'
    m = reader_to_source_map(block_src, old_reader)
    out = block_src
    for j1, j2, repl in sorted(hunks, key=lambda h: -h[0]):        # latest-first keeps offsets valid
        # End of the span is one past the LAST reader char being replaced — not the source
        # position of the next one, which would swallow any markdown sitting between them
        # (`for us*` instead of `for us`, eating the closing emphasis marker).
        a = m[j1]
        b = (m[j2 - 1] + 1) if j2 > j1 else a
        if a is None or b is None or a > b:
            return None, 'offsets could not be mapped into the markdown'
        out = out[:a] + repl + out[b:]
    rendered = (render_footnote_block(out, piece_dir) if kind == 'footnote'
                else render_block(out, piece_dir))
    if rendered is None:
        return None, 'block no longer parses as a footnote definition'
    got = flatten_quotes(strip_to_reader(rendered))
    want = flatten_quotes(new_reader)
    if got != want:
        return None, 'edited block did not re-render to the expected text'
    return out, 'verified'


def _opcodes(a, b):
    return difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()


# ---------------------------------------------------------------- browser JS

SCAN_JS = """await (async () => {
  const root = document.querySelector('.ProseMirror');
  if (!root || !root.editor) return JSON.stringify({ error: 'no editor — open the live post at /publish/post/<id>' });
%HELPERS%
  const sha = async s => {
    const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
    return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('').slice(0, 16);
  };
  const body = [], fns = [];
  root.editor.state.doc.forEach(n => {
    if (n.type.name === 'footnote') fns.push(n.textContent);
    else if (isBodyNode(n)) body.push(n.textContent);
  });
  const hash = async a => Promise.all(a.map(t => sha(flat(t))));
  const T = document.querySelector('textarea[placeholder="Title"]');
  const S = document.querySelector('textarea[placeholder="Add a subtitle\\u2026"]');
  return JSON.stringify({
    url: location.href,
    title: T ? T.value : '', subtitle: S ? S.value : '',
    counts: { body: body.length, fns: fns.length },
    body: await hash(body), fns: await hash(fns)
  });
})()"""

FETCH_JS = """(() => {
  const WANT_BODY = %BODY_IDX%, WANT_FNS = %FN_IDX%;
  const root = document.querySelector('.ProseMirror');
  if (!root || !root.editor) return JSON.stringify({ error: 'no editor found' });
%HELPERS%
  const body = [], fns = [];
  root.editor.state.doc.forEach(n => {
    if (n.type.name === 'footnote') fns.push(n.textContent);
    else if (isBodyNode(n)) body.push(n.textContent);
  });
  const pick = (a, idx) => Object.fromEntries(idx.map(i => [i, a[i]]));
  return JSON.stringify({ body: pick(body, WANT_BODY), fns: pick(fns, WANT_FNS) });
})()"""


# ---------------------------------------------------------------- commands

def cmd_scan(piece_dir, out_js):
    open(out_js, 'w').write(SCAN_JS.replace('%HELPERS%', JS_HELPERS))
    d = draft_state(piece_dir)
    print(f"wrote {out_js}")
    print(f"draft: body={len(d['body'])} fns={len(d['fns'])}  post_url~{d['post_url'] or '(none)'}")
    print("Run it in the live post's editor; save the JSON it returns, then: plan <piece> <live.json>")


def cmd_plan(piece_dir, live_json, out_plan):
    live = json.load(open(live_json))
    if live.get('error'):
        print(f"scan failed: {live['error']}")
        sys.exit(1)
    d = draft_state(piece_dir)

    if d['residual']:
        print(f"Refusing: {len(d['residual'])} footnote(s) still contain 'verify': {d['residual']}")
        sys.exit(2)
    iss = {k: v for k, v in d['fn_issues'].items() if v}
    if d['fn_issues']['undefined'] or d['fn_issues']['duplicated'] or d['fn_issues']['nested']:
        print(f"Refusing: footnote refs/definitions do not pair up ({iss}).")
        sys.exit(4)

    base = load_baseline(piece_dir)
    if base is None:
        print("NO BASELINE for this piece — a two-way diff cannot tell which side moved.")
        print("Establish one first:")
        print("  seed <piece> --from-git <rev>   (render draft.md as at the commit it was composed from)")
        print("  seed <piece> --from-draft       (assert the draft is what is live)")
        print("  seed <piece> --from-live <live.json>")
        print("\nFor reference, the current raw divergence:")
        print(f"  body  draft={len(d['body'])}  live={live['counts']['body']}")
        print(f"  fns   draft={len(d['fns'])}   live={live['counts']['fns']}")
        sys.exit(3)

    b_rows, b_struct = three_way('body', base['body'],
                                 [H(t) for t in d['body']], live['body'], d['body'])
    f_rows, f_struct = three_way('footnote', base['fns'],
                                 [H(t) for t in d['fns']], live['fns'], d['fns'])
    rows = b_rows + f_rows
    structural = b_struct + f_struct

    title_state = ('unchanged' if H(d['title']) == base['title'] == H(live['title']) else
                   'push' if H(live['title']) == base['title'] else
                   'pull' if H(d['title']) == base['title'] else
                   'converged' if H(d['title']) == H(live['title']) else 'conflict')
    sub_state = ('unchanged' if H(d['subtitle']) == base['subtitle'] == H(live['subtitle']) else
                 'push' if H(live['subtitle']) == base['subtitle'] else
                 'pull' if H(d['subtitle']) == base['subtitle'] else
                 'converged' if H(d['subtitle']) == H(live['subtitle']) else 'conflict')

    plan = {
        'piece': os.path.basename(piece_dir), 'post_url': d['post_url'],
        'title': {'state': title_state, 'draft': d['title'], 'live': live['title']},
        'subtitle': {'state': sub_state, 'draft': d['subtitle'], 'live': live['subtitle']},
        'rows': rows, 'structural': structural,
    }
    json.dump(plan, open(out_plan, 'w'), indent=1)

    tally = {}
    for r in rows:
        tally[r['state']] = tally.get(r['state'], 0) + 1
    print(f"=== {plan['piece']} ===")
    print(f"  title    {title_state}" + ('' if title_state in ('unchanged', 'converged')
                                          else f"   draft={d['title']!r} live={live['title']!r}"))
    print(f"  subtitle {sub_state}" + ('' if sub_state in ('unchanged', 'converged')
                                        else f"   draft={d['subtitle']!r} live={live['subtitle']!r}"))
    print(f"  blocks   " + '  '.join(f"{k}={v}" for k, v in sorted(tally.items())))
    for r in rows:
        if r['state'] in ('pull', 'conflict', 'push'):
            print(f"    {r['state']:9} {r['kind']:8} draft#{r['draftIdx']} live#{r['liveIdx']}")
    if structural:
        print(f"  STRUCTURAL ({len(structural)}) — not auto-merged, resolve by hand:")
        for s in structural:
            print(f"    {s['side']:5} {s['kind']:8} {s.get('what')}"
                  + (f"  {s['text']!r}" if s.get('text') else ''))
    need = [r for r in rows if r['state'] in ('pull', 'conflict')]
    print(f"\nwrote {out_plan}")
    if need:
        print(f"{len(need)} row(s) need live text: fetch <piece> {out_plan} <out.js>")
    elif any(r['state'] == 'push' for r in rows) or title_state == 'push' or sub_state == 'push':
        print("push-only: run substack_repatch.py to stage the edits.")
    else:
        print("nothing to do.")


def cmd_fetch(piece_dir, plan_json, out_js):
    plan = json.load(open(plan_json))
    need = [r for r in plan['rows'] if r['state'] in ('pull', 'conflict')]
    bidx = sorted({r['liveIdx'] for r in need if r['kind'] == 'body'})
    fidx = sorted({r['liveIdx'] for r in need if r['kind'] == 'footnote'})
    js = (FETCH_JS.replace('%HELPERS%', JS_HELPERS)
                  .replace('%BODY_IDX%', json.dumps(bidx)).replace('%FN_IDX%', json.dumps(fidx)))
    open(out_js, 'w').write(js)
    print(f"wrote {out_js} — fetches {len(bidx)} body + {len(fidx)} footnote block(s) of live text")


def _summarize(old, new):
    d = [(old[j1:j2], new[k1:k2]) for tag, j1, j2, k1, k2 in _opcodes(old, new) if tag != 'equal']
    return '; '.join(f'{o[:40]!r} -> {n[:40]!r}' for o, n in d[:3]) + (' …' if len(d) > 3 else '')


def cmd_pull(piece_dir, plan_json, livetext_json):
    plan = json.load(open(plan_json))
    lt = json.load(open(livetext_json))
    d = draft_state(piece_dir)
    conflicts = [r for r in plan['rows'] if r['state'] == 'conflict']
    if conflicts:
        print(f"REFUSING: {len(conflicts)} conflict(s) — the same block moved on both sides.")
        for r in conflicts:
            src = lt['fns' if r['kind'] == 'footnote' else 'body'].get(str(r['liveIdx']), '')
            mine = (d['fns'] if r['kind'] == 'footnote' else d['body'])[r['draftIdx']]
            print(f"\n  {r['kind']} draft#{r['draftIdx']} / live#{r['liveIdx']}")
            print(f"    draft: {mine[:200]}")
            print(f"    live : {src[:200]}")
        print("\nResolve each by hand in draft.md (or in Substack), then re-run scan/plan.")
        sys.exit(5)

    pulls = [r for r in plan['rows'] if r['state'] == 'pull']
    if not pulls and plan['title']['state'] != 'pull' and plan['subtitle']['state'] != 'pull':
        print("no pulls to apply.")
        return

    path = os.path.join(piece_dir, 'draft.md')
    src = open(path).read()
    sources = render_reader.sources
    applied, manual = [], []
    for r in pulls:
        kind = 'fns' if r['kind'] == 'footnote' else 'body'
        texts = d['fns'] if kind == 'fns' else d['body']
        new = lt[kind].get(str(r['liveIdx']))
        if new is None:
            manual.append((r, 'live text not in the fetch result'))
            continue
        old_reader = texts[r['draftIdx']]
        block_src = sources[kind][r['draftIdx']]
        if src.count(block_src) != 1:
            manual.append((r, 'block source is not uniquely locatable in draft.md'))
            continue
        # keep draft.md straight-quoted: the curly quotes are Substack's rendering, not content
        new_src, note = edit_block_source(block_src, old_reader, flatten_quotes(new),
                                          piece_dir, r['kind'])
        if new_src is None:
            manual.append((r, note))
            continue
        src = src.replace(block_src, new_src, 1)
        applied.append((r, f'{note}: {_summarize(old_reader, flatten_quotes(new))}'))

    if applied:
        open(path, 'w').write(src)
    print(f"applied {len(applied)} pull edit(s) to {path}")
    for r, msg in applied:
        print(f"  {r['kind']:8} draft#{r['draftIdx']}  {msg}")
    if plan['title']['state'] == 'pull' or plan['subtitle']['state'] == 'pull':
        print("\npublish.yaml needs the live value (edit by hand — it is the manifest, not prose):")
        if plan['title']['state'] == 'pull':
            print(f"  title:    {plan['title']['live']}")
        if plan['subtitle']['state'] == 'pull':
            print(f"  subtitle: {plan['subtitle']['live']}")
    if manual:
        print(f"\n{len(manual)} edit(s) could NOT be placed safely — apply by hand:")
        for r, msg in manual:
            print(f"  {r['kind']:8} draft#{r['draftIdx']}  {msg}")
        sys.exit(6)



# The minimal push. Where substack_repatch ships the WHOLE document and rediscovers what
# differs, sync already knows — the plan says exactly which blocks moved and in which
# direction — so this carries only those blocks. A 6,000-word essay with a one-word fix
# becomes a few hundred bytes instead of ~24 KB.
#
# It also buys a real guarantee the full-document patcher cannot give: each row carries the
# hash the block had AT SCAN TIME, and every row is checked BEFORE anything is applied. If
# the post changed in between — someone editing in Substack while this ran — the whole push
# aborts having staged nothing, instead of writing over an edit it never saw.
PUSH_JS = """await (async () => {
  const PATCH = %PATCH%, TITLE = %TITLE%, SUBTITLE = %SUBTITLE%;
  const SET_TITLE = %SET_TITLE%, SET_SUB = %SET_SUB%;
  const root = document.querySelector('.ProseMirror');
  if (!root || !root.editor) return JSON.stringify({ error: 'no editor — open the live post at /publish/post/<id>' });
  const ed = root.editor;
%HELPERS%
  const sha = async s => {
    const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
    return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('').slice(0, 16);
  };
  const body = [], fns = [];
  ed.state.doc.forEach((node, pos) => {
    const raw = node.textContent;
    const rec = { pos, node, raw, text: flat(raw) };
    if (node.type.name === 'footnote') fns.push(rec);
    else if (isBodyNode(node)) body.push(rec);
  });
  const list = k => (k === 'footnote' ? fns : body);
  const report = { stale: [], applied: [], failed: [], reviewMarks: [],
                   titleChanged: false, subtitleChanged: false, aborted: false };

  // pre-image check across EVERY row before a single edit is applied
  for (const r of PATCH) {
    const L = list(r.kind)[r.liveIdx];
    if (!L) { report.stale.push({ kind: r.kind, liveIdx: r.liveIdx, why: 'no block at that index' }); continue; }
    if (await sha(L.text) !== r.expect)
      report.stale.push({ kind: r.kind, liveIdx: r.liveIdx,
                          why: 'live text changed since the scan', live: L.text.slice(0, 90) });
  }
  if (report.stale.length) {
    report.aborted = true;
    report.note = 'live post moved since the scan — nothing was staged. Re-run scan/plan.';
    return JSON.stringify(report);
  }

  const tasks = [];
  for (const r of PATCH) {
    const L = list(r.kind)[r.liveIdx];
    for (const h of diffHunks(L.text, flat(r.text))) tasks.push({ r, L, hunk: h });
  }
  tasks.sort((a, b) => (b.L.pos - a.L.pos) || (b.hunk.aStart - a.hunk.aStart));
  for (const t of tasks) {
    try {
      const from = offsetToPos(t.L.node, t.L.pos, t.hunk.aStart);
      const to = offsetToPos(t.L.node, t.L.pos, t.hunk.aEnd);
      const st = ed.state;
      const marks = st.doc.resolve(from).marks();
      const endMarks = st.doc.resolve(Math.max(from, to)).marks();
      const uniform = marks.length === endMarks.length && marks.every(m => endMarks.some(e => e.eq(m)));
      const prevCh = t.hunk.aStart > 0 ? t.L.raw[t.hunk.aStart - 1] : ' ';
      const ins = smarten(t.hunk.text, prevCh);
      let tr = st.tr;
      if (ins.length) tr = tr.replaceWith(from, to, st.schema.text(ins, marks));
      else tr = tr.delete(from, to);
      ed.view.dispatch(tr);
      const e = { kind: t.r.kind, liveIdx: t.r.liveIdx, insert: ins || '(deleted)' };
      report.applied.push(e);
      if (!uniform || t.hunk.big) report.reviewMarks.push(e);
    } catch (err) {
      report.failed.push({ kind: t.r.kind, liveIdx: t.r.liveIdx, error: String(err) });
    }
  }
  const setField = (sel, v) => {
    const el = document.querySelector(sel);
    if (!el || el.value === v) return false;
    const d = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
    d.set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  };
  if (SET_TITLE) report.titleChanged = setField('textarea[placeholder="Title"]', TITLE);
  if (SET_SUB) report.subtitleChanged = setField('textarea[placeholder="Add a subtitle\\u2026"]', SUBTITLE);
  report.stagedEdits = report.applied.length;
  return JSON.stringify(report);
})()"""


def cmd_push(piece_dir, plan_json, live_json, out_js):
    plan = json.load(open(plan_json))
    live = json.load(open(live_json))
    d = draft_state(piece_dir)
    if any(r['state'] == 'conflict' for r in plan['rows']):
        print("REFUSING: the plan has conflicts. Resolve them first (see `pull`).")
        sys.exit(5)
    patch = []
    for r in plan['rows']:
        if r['state'] != 'push':
            continue
        kind = r['kind']
        texts = d['fns'] if kind == 'footnote' else d['body']
        expect = (live['fns'] if kind == 'footnote' else live['body'])[r['liveIdx']]
        patch.append({'kind': kind, 'liveIdx': r['liveIdx'],
                      'expect': expect, 'text': texts[r['draftIdx']]})
    set_title = plan['title']['state'] == 'push'
    set_sub = plan['subtitle']['state'] == 'push'
    if not patch and not set_title and not set_sub:
        print("nothing to push.")
        return
    js = (PUSH_JS.replace('%HELPERS%', JS_HELPERS)
                 .replace('%PATCH%', json.dumps(patch))
                 .replace('%TITLE%', json.dumps(d['title']))
                 .replace('%SUBTITLE%', json.dumps(d['subtitle']))
                 .replace('%SET_TITLE%', 'true' if set_title else 'false')
                 .replace('%SET_SUB%', 'true' if set_sub else 'false'))
    open(out_js, 'w').write(js)
    print(f"wrote {out_js} ({len(js)} bytes) — {len(patch)} block(s)"
          + (", title" if set_title else "") + (", subtitle" if set_sub else ""))
    for p_ in patch:
        print(f"  {p_['kind']:8} live#{p_['liveIdx']}")


def _render_at(piece_dir, rev, top):
    """Render draft.md as it stood at `rev`, in a temp copy of the piece."""
    rel = os.path.relpath(os.path.abspath(os.path.join(piece_dir, 'draft.md')), top)
    blob = subprocess.run(['git', '-C', top, 'show', f'{rev}:{rel}'],
                          capture_output=True, text=True, check=True).stdout
    tmp = tempfile.mkdtemp()
    try:
        for f in os.listdir(piece_dir):
            src = os.path.join(piece_dir, f)
            if os.path.isfile(src):
                shutil.copy2(src, tmp)
        open(os.path.join(tmp, 'draft.md'), 'w').write(blob)
        body, fns, _res, _iss = render_reader(tmp)
        return [H(t) for t in body], [H(t) for t in fns]
    finally:
        shutil.rmtree(tmp)


def cmd_detect(piece_dir, live_json):
    """Find which revision the LIVE POST still matches — that one IS the baseline.

    Do not reach for "the newest commit." A commit can carry an editorial pass that was
    never published, and seeding from it inverts every row that pass touched: the tool
    reports a PULL and dutifully reverts the change in draft.md, reporting success.

    That is not hypothetical. `e37d5f3` bundled a corpus-wide deity-pronoun capitalization
    sweep into an unrelated compose commit, and the sweep never reached Substack. Seeding
    `The Way Home Is Down` from it wanted to revert ten capitals — caught, because this
    comparison was run by hand. Seeding `They/Them` and `I Believe in You` from it was NOT
    checked, and ten more capitals were quietly pulled out of two live essays before the
    author noticed. Hence this command: the check is the tool's job, not the operator's
    memory.
    """
    live = json.load(open(live_json))
    top = subprocess.run(['git', '-C', piece_dir, 'rev-parse', '--show-toplevel'],
                         capture_output=True, text=True, check=True).stdout.strip()
    rel = os.path.relpath(os.path.abspath(os.path.join(piece_dir, 'draft.md')), top)
    revs = subprocess.run(['git', '-C', top, 'log', '--format=%h', '--', rel],
                          capture_output=True, text=True, check=True).stdout.split()
    if not revs:
        print("no commits touch this draft — nothing to detect.")
        sys.exit(1)
    print(f"{'rev':10} {'body':>14} {'footnotes':>14}   subject")
    best, best_score = None, -1
    for rev in revs:
        try:
            bh, fh = _render_at(piece_dir, rev, top)
        except Exception as e:
            print(f"{rev:10} (render failed: {e})")
            continue
        bm = sum(1 for x, y in zip(bh, live['body']) if x == y)
        fm = sum(1 for x, y in zip(fh, live['fns']) if x == y)
        exact = (len(bh) == len(live['body']) and len(fh) == len(live['fns']))
        score = bm + fm + (10000 if exact and bm == len(bh) else 0)
        subj = subprocess.run(['git', '-C', top, 'log', '-1', '--format=%s', rev],
                              capture_output=True, text=True).stdout.strip()[:54]
        print(f"{rev:10} {bm:>6}/{len(bh):<7} {fm:>6}/{len(fh):<7}   {subj}")
        if score > best_score:
            best, best_score = rev, score
    print(f"\nbest match: {best}")
    print(f"  seed {piece_dir} --from-git {best}")
    print("A revision matching the live post on EVERY body block is the state that was last\n"
          "pushed. If the newest commit is not that revision, it carries work that never\n"
          "shipped — seeding from it would revert that work instead of publishing it.")


def cmd_resolve(piece_dir, live_json, args):
    """Record a HUMAN's decision on a conflicted row, by moving the baseline for that row.

    A conflict means both sides moved and disagree, and no rule can settle it — which is why
    `pull` and `push` both refuse to touch one. Resolving is therefore not a flag that forces
    past a guard; it is the decision the guard exists to ask for, written down.

    --take-draft <kind>:<idx>  the draft is right: baseline := live, so the row becomes a PUSH
    --take-live  <kind>:<idx>  live is right:      baseline := draft, so the row becomes a PULL

    Take-draft after editing the draft by hand is the normal shape: incorporate whatever live
    had that you want, put the finished text in draft.md, then say so here.
    """
    live = json.load(open(live_json))
    base = load_baseline(piece_dir)
    if base is None:
        print("no baseline to resolve against.")
        sys.exit(3)
    d = draft_state(piece_dir)
    draft_h = {'body': [H(t) for t in d['body']], 'footnote': [H(t) for t in d['fns']]}
    live_h = {'body': live['body'], 'footnote': live['fns']}
    key = {'body': 'body', 'footnote': 'fns'}
    done = []
    i = 0
    while i < len(args):
        mode = args[i]
        if mode not in ('--take-draft', '--take-live'):
            print(f"unknown option {mode!r}")
            sys.exit(1)
        kind, _, idx = args[i + 1].partition(':')
        idx = int(idx)
        if kind not in ('body', 'footnote'):
            print(f"kind must be body or footnote, got {kind!r}")
            sys.exit(1)
        base[key[kind]][idx] = (live_h[kind][idx] if mode == '--take-draft'
                                else draft_h[kind][idx])
        done.append(f"{mode[7:]:5} {kind}#{idx}")
        i += 2
    base['note'] = base.get('note', '') + f" | resolved by hand: {', '.join(done)}"
    json.dump(base, open(os.path.join(piece_dir, BASELINE), 'w'), indent=1)
    print(f"resolved {len(done)} row(s) in {os.path.join(piece_dir, BASELINE)}:")
    for x in done:
        print(f"  {x}")



def cmd_seed(piece_dir, mode, arg):
    if mode == '--from-draft':
        d = draft_state(piece_dir)
        title, subtitle = d['title'], d['subtitle']
        body_h, fns_h = [H(t) for t in d['body']], [H(t) for t in d['fns']]
        note = 'seeded from draft.md as it stands'
    elif mode == '--from-live':
        live = json.load(open(arg))
        title, subtitle = live['title'], live['subtitle']
        body_h, fns_h = live['body'], live['fns']
        note = 'seeded from the live post'
    elif mode == '--from-git':
        # git must run in the PIECE's repo, not the framework submodule this file lives in
        top = subprocess.run(['git', '-C', piece_dir, 'rev-parse', '--show-toplevel'],
                             capture_output=True, text=True, check=True).stdout.strip()
        rel = os.path.relpath(os.path.abspath(os.path.join(piece_dir, 'draft.md')), top)
        blob = subprocess.run(['git', '-C', top, 'show', f'{arg}:{rel}'],
                              capture_output=True, text=True, check=True).stdout
        tmp = tempfile.mkdtemp()
        try:
            for f in os.listdir(piece_dir):
                s = os.path.join(piece_dir, f)
                if os.path.isfile(s):
                    shutil.copy2(s, tmp)
            open(os.path.join(tmp, 'draft.md'), 'w').write(blob)
            body, fns, _res, _iss = render_reader(tmp)
        finally:
            shutil.rmtree(tmp)
        # publish.yaml AS AT THAT REV too: the title/subtitle pushed then are the baseline,
        # and reading today's manifest would bake a later hand-edit into the baseline and so
        # hide the very pull it exists to detect.
        relman = os.path.relpath(os.path.abspath(os.path.join(piece_dir, 'publish.yaml')), top)
        old_man = subprocess.run(['git', '-C', top, 'show', f'{arg}:{relman}'],
                                 capture_output=True, text=True)
        if old_man.returncode == 0:
            mtmp = tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False)
            mtmp.write(old_man.stdout); mtmp.close()
            man = read_manifest(mtmp.name)
            os.unlink(mtmp.name)
        else:
            man = read_manifest(os.path.join(piece_dir, 'publish.yaml'))
        title, subtitle = man.get('title', ''), man.get('subtitle', '')
        body_h, fns_h = [H(t) for t in body], [H(t) for t in fns]
        note = f'seeded from draft.md + publish.yaml at {arg}'
    else:
        print("seed needs --from-git <rev> | --from-draft | --from-live <live.json>")
        sys.exit(1)
    p = write_baseline(piece_dir, title, subtitle, body_h, fns_h, note)
    print(f"wrote {p} — {note} (body={len(body_h)} fns={len(fns_h)})")


def cmd_seal(piece_dir, live_json):
    live = json.load(open(live_json))
    d = draft_state(piece_dir)
    db, df = [H(t) for t in d['body']], [H(t) for t in d['fns']]
    if db != live['body'] or df != live['fns']:
        print("REFUSING to seal: draft and live still differ — sync is not complete.")
        print(f"  body  draft={len(db)} live={len(live['body'])}  "
              f"matched={sum(1 for a, b in zip(db, live['body']) if a == b)}")
        print(f"  fns   draft={len(df)} live={len(live['fns'])}  "
              f"matched={sum(1 for a, b in zip(df, live['fns']) if a == b)}")
        sys.exit(7)
    if H(d['title']) != H(live['title']) or H(d['subtitle']) != H(live['subtitle']):
        print("REFUSING to seal: title/subtitle still differ between publish.yaml and live.")
        sys.exit(7)
    p = write_baseline(piece_dir, d['title'], d['subtitle'], db, df, 'sealed: draft and live agree')
    print(f"sealed {p} (body={len(db)} fns={len(df)})")


def main():
    if len(sys.argv) < 3:
        print("usage: substack_sync.py <scan|plan|fetch|pull|push|resolve|detect|seed|seal> <piece-dir> [args]")
        sys.exit(1)
    cmd, piece_dir = sys.argv[1], sys.argv[2].rstrip('/')
    rest = sys.argv[3:]
    if cmd == 'scan':
        cmd_scan(piece_dir, rest[0] if rest else 'scan.js')
    elif cmd == 'plan':
        cmd_plan(piece_dir, rest[0], rest[1] if len(rest) > 1 else 'sync-plan.json')
    elif cmd == 'fetch':
        cmd_fetch(piece_dir, rest[0], rest[1] if len(rest) > 1 else 'fetch.js')
    elif cmd == 'pull':
        cmd_pull(piece_dir, rest[0], rest[1])
    elif cmd == 'resolve':
        cmd_resolve(piece_dir, rest[0], rest[1:])
    elif cmd == 'push':
        cmd_push(piece_dir, rest[0], rest[1], rest[2] if len(rest) > 2 else 'push.js')
    elif cmd == 'detect':
        cmd_detect(piece_dir, rest[0])
    elif cmd == 'seed':
        cmd_seed(piece_dir, rest[0], rest[1] if len(rest) > 1 else None)
    elif cmd == 'seal':
        cmd_seal(piece_dir, rest[0])
    else:
        print(f"unknown command {cmd!r}")
        sys.exit(1)


if __name__ == '__main__':
    main()
