#!/usr/bin/env python3
"""
substack_repatch.py — surgically re-sync an ALREADY-PUBLISHED Substack post to the
current draft.md, changing only what actually changed and touching nothing else.

Where md_to_substack.py composes a fresh post from scratch, this emits a self-contained
JS snippet that, run once in the OPEN editor of the *live* post, will:

  1. read the current draft's reader-text (body blocks + native footnotes) — baked in
     here by this tool, after the SAME verify-and-strip preflight as a fresh publish;
  2. scrape the live post's reader-text straight out of its ProseMirror doc;
  3. align them (non-empty body top-nodes 1:1, footnote nodes 1:1) and REFUSE if the
     structure differs — a block or footnote added / removed / reordered — because that
     is a rewrite, not a touch-up, and wants a full recompose or a human, not a blind
     nuke-and-repave of a live public essay;
  4. otherwise replace only the changed run inside each changed node — preserving the
     surrounding text, the node, and the marks (bold/italic/links) across the edit —
     plus the title/subtitle if they changed;
  5. return a JSON report (applied / unchanged / footnoteChanges / structural / failed).

It never clicks anything. After it stages the edits, the "Continue" button lights up and
a HUMAN reviews and clicks Continue -> Publish (choosing not to resend email). Same
draft-only guarantee as md_to_substack.py.

Usage:  python3 substack_repatch.py <piece-dir> [out.js]
        python3 substack_repatch.py --structural <piece-dir> [out.js]

--structural is the second engine, for the case the first one REFUSES: a block added,
removed, merged or split, or a footnote retired — a rewrite of a live post whose embeds
and images a full recompose would destroy. It aligns draft blocks against the live doc by
text (LCS), and then:

  * pairs every ANCHOR-BEARING block 1:1 by order inside each changed range and edits
    those by text hunk only, so the native footnote anchors are never touched by HTML;
  * replaces everything else whole, from the converter's own HTML (italics, links), with
    quotes smartened OUTSIDE tags only — an href with curled quotes is a dead link;
  * drops the anchor of a footnote the draft has retired, and the orphaned footnote node
    if the editor does not remove it itself;
  * REFUSES, before touching anything, when: a block's HTML does not hash to its own text
    (a transcription error, if the snippet was retyped into an eval); anchor-bearing blocks
    do not pair 1:1; the draft ADDS a footnote (insertFootnote is not automated here);
    footnote order differs; or a hunk would span an inline node or a mark boundary.

Every op is checked against the draft's own sha256/16 after it lands, and the whole
document is re-read at the end: block count, every block's text, footnote count, anchor
count, and a link mark on every block whose HTML carried one. It grew out of three
hand-built syncs of `The Hollow Flute` (2026-09-04 → 07), each of which needed one more
guard than the last; the guards are the point.

The caller (the `publish` skill in republish mode) runs the emitted JS once against the
live post's editor at  https://<pub>.substack.com/publish/post/<id> .

Baseline: this diffs the current draft against the LIVE POST ITSELF (scraped at run time),
not a stored snapshot — so it is stateless and self-correcting: whatever is deployed is
the baseline, and only the delta to the current draft is applied.
"""
import sys, os, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from md_to_substack import render_reader, read_manifest, flatten_quotes


def main():
    structural = '--structural' in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print("usage: substack_repatch.py <piece-dir> [out.js]")
        sys.exit(1)
    piece_dir = args[0].rstrip('/')
    out_js = args[1] if len(args) > 1 else 'repatch.js'
    man = read_manifest(os.path.join(piece_dir, 'publish.yaml'))
    post_url = man.get('post_url', '')
    body, fns, residual, fn_issues = render_reader(piece_dir)

    if residual:
        print(f"WARNING: {len(residual)} footnote(s) still carry verify or clearance language (an ISO date, 'consulted …') after cleaning: "
              f"{residual}. Resolve the note (verify -> move behind a †, or delete) before republishing.")
        print("Refusing to write output.")
        sys.exit(2)

    if fn_issues['undefined'] or fn_issues['duplicated'] or fn_issues['nested']:
        print(f"Refusing: footnote refs and definitions do not pair up "
              f"({ {k: v for k, v in fn_issues.items() if v} }). Each of these shifts the "
              f"footnote indexing the surgical diff aligns on.")
        sys.exit(4)

    print(f"target body-blocks~{len(body)}  footnotes~{len(fns)}  "
          f"post_url~{post_url or '(none — set it in publish.yaml before republishing)'}")
    if not post_url:
        print("NOTE: publish.yaml has no post_url. Republish mode targets the editor of an existing "
              "post; open https://<pub>.substack.com/publish/post/<id> for the live post, and record "
              "that post_url in publish.yaml so future runs are unambiguous.")

    if structural:
        js = build_structural(piece_dir, man, body, fns)
        open(out_js, 'w').write(js)
        print(f"wrote {out_js} ({len(js)} bytes) — STRUCTURAL engine: run once in the live editor; "
              f"read `refused` and `ok` in the report; nothing is applied on a refusal")
        return

    js = (REPATCH_JS
          .replace('%HELPERS%', JS_HELPERS)
          .replace('%TITLE%', json.dumps(man.get('title', '')))
          .replace('%SUBTITLE%', json.dumps(man.get('subtitle', '')))
          .replace('%BODY%', json.dumps(body))
          .replace('%FNS%', json.dumps(fns)))
    open(out_js, 'w').write(js)
    print(f"wrote {out_js} ({len(js)} bytes)")


# JS helpers shared by the full-document patcher below and by substack_sync's
# minimal push, so the two can never drift on typography, diffing or offsets.
JS_HELPERS = r"""  // Substack owns some blocks in its own document: a subscribe prompt it injects into
  // published posts, and its relatives. They carry text, they are NOT authored content, and
  // they exist in no draft.md — so counting them as body blocks makes a piece look
  // structurally divergent forever and shifts every index after the first one. `They/Them`
  // carried two subscribeWidgets (one after the opening beat, one at the tail) and so read as
  // live=85 vs draft=83, which the count guard could only report as "refusing to patch."
  // Anything unrecognized is deliberately NOT excluded: an unknown block changes the count and
  // surfaces as a structural refusal, which is the safe direction to be wrong in.
  const SUBSTACK_FURNITURE = new Set(['subscribeWidget', 'subscribeWithCaption', 'button',
    'paywall', 'latestPosts', 'embeddedPublication', 'share', 'poll', 'digestPostEmbed']);
  // Media nodes carry TEXT (a caption) but can never come from draft.md: a markdown image
  // renders to <figure><img alt=...> whose alt lives in an attribute, so render_reader's body
  // never contains it. Counting a captioned image as a body block therefore makes the live doc
  // permanently one block longer than its own draft — `Flow` read 34 against 33 and looked
  // structurally divergent when it was in sync, and every index after the image was shifted by
  // one, which is the condition under which a "surgical" patch writes into the wrong paragraph.
  const MEDIA = new Set(['captionedImage', 'image', 'video', 'nativeVideo', 'audio',
    'embeddedPost', 'tweet', 'youtube2']);
  const isBodyNode = n => n.type.name !== 'footnote'
    && !SUBSTACK_FURNITURE.has(n.type.name)
    && !MEDIA.has(n.type.name)
    && n.textContent.trim() !== '';

  const flat = s => s.replace(/[\u2018\u2019]/g, "'").replace(/[\u201c\u201d]/g, '"');

  // TWO normalizations, and keeping them apart is the point.
  //
  //   flat()     — quotes only. LENGTH-PRESERVING, so a char offset computed on it is a valid
  //                offset into the real text. Everything positional uses this.
  //   sameText() — flat() plus collapsed whitespace. NOT length-preserving, so it must never
  //                touch an offset. Used only to answer "is this block different?"
  //
  // A run of whitespace is not content: HTML collapses it, so `it.  The` and `it. The` render
  // identically and no reader can tell them apart. But `strip_to_reader` collapses runs on the
  // draft side, so a live post holding a double space describes a block NO DRAFT CAN EVER
  // PRODUCE — a difference that can never converge, reported on every future sync.
  //
  // `Both Ends of the Leash` (2026-09-01) is why this exists. Chasing exactly that phantom, a
  // one-space push was aimed between two adjacent footnote anchors and deleted one of them off
  // a live post. The edit was cosmetically invisible to readers; it was made only to quiet a
  // report. Comparing whitespace-insensitively means the report is quiet on its own and the
  // post never has to be touched.
  const sameText = s => flat(s).replace(/\s+/g, ' ').trim();
  const OPENS = new Set([...' \t\n(\u3010[{\u2014\u2013-\u201c\u2018']);
  const smarten = (s, prevCh) => {
    let out = '';
    for (let i = 0; i < s.length; i++) {
      const ch = s[i], prev = i ? s[i-1] : (prevCh || ' ');
      if (ch === '"') out += OPENS.has(prev) ? '\u201c' : '\u201d';
      else if (ch === "'") out += OPENS.has(prev) ? '\u2018' : '\u2019';
      else out += ch;
    }
    return out;
  };

  // minimal char-level diff of one block into hunks [{aStart,aEnd,text}], grouping each
  // contiguous run of edits between matched text into ONE hunk. Two separate edits in a
  // paragraph stay two hunks, so each is applied with its own marks — a casing flip inside
  // an italic run keeps the italic, a plain-text fix stays plain.
  const diffHunks = (a, b) => {
    if (a === b) return [];
    const n = a.length, m = b.length;
    let p = 0; while (p < n && p < m && a[p] === b[p]) p++;
    let s = 0; while (s < n - p && s < m - p && a[n-1-s] === b[m-1-s]) s++;
    const ac = a.slice(p, n - s), bc = b.slice(p, m - s);
    const A = ac.length, B = bc.length;
    // guard the DP: fall back to one span for pathologically large cores
    if (A * B > 4000000 || A > 60000 || B > 60000) return [{ aStart: p, aEnd: n - s, text: bc, big: true }];
    const dp = Array.from({ length: A + 1 }, () => new Uint16Array(B + 1));
    for (let i = A - 1; i >= 0; i--) for (let j = B - 1; j >= 0; j--)
      dp[i][j] = ac[i] === bc[j] ? dp[i+1][j+1] + 1 : Math.max(dp[i+1][j], dp[i][j+1]);
    const hunks = []; let i = 0, j = 0, ds = null, de = null, ins = '';
    const flush = () => { if (ds !== null || ins.length) hunks.push({ aStart: p + (ds !== null ? ds : i), aEnd: p + (de !== null ? de : i), text: ins }); ds = de = null; ins = ''; };
    while (i < A && j < B) {
      if (ac[i] === bc[j]) { flush(); i++; j++; }
      else if (dp[i+1][j] >= dp[i][j+1]) { if (ds === null) ds = i; de = i + 1; i++; }
      else { if (ds === null) { ds = i; de = i; } ins += bc[j]; j++; }
    }
    if (i < A) { if (ds === null) ds = i; de = A; }
    if (j < B) ins += bc.slice(j);
    flush();
    return hunks;
  };

  // map a character offset within a top node's textContent to an absolute doc position,
  // walking real text descendants so it is correct whether the node is a bare textblock
  // (paragraph/heading) or wraps a paragraph (footnote).
  const offsetToPos = (node, nodeStartPos, charOffset) => {
    // Map a char offset in the node's reader-text to a document position.
    //
    // The comparison is STRICT (`<`, not `<=`) and that is the whole point. An offset landing
    // exactly on a text-node boundary must resolve to the START OF THE NEXT TEXT RUN, not to
    // the end of the current one — because between two text runs there can be an inline node,
    // and the "end of the current run" is that node's position. With `<=`, a delete whose
    // boundary fell there removed the inline node instead of the character.
    //
    // Found the hard way on `Both Ends of the Leash` (2026-09-01): the paragraph reads
    // "...delivering it.[anchor 10] [anchor 11] The behavior...", and deleting one space
    // deleted footnote 11 off a LIVE post. Undo restored it; the public page never lost it.
    // Any inline node is exposed to this — a footnote anchor is simply the one this desk has.
    let acc = 0, out = null;
    node.descendants((child, relPos) => {
      if (out !== null) return false;
      if (child.isText) {
        const len = child.text.length;
        if (charOffset < acc + len) { out = nodeStartPos + 1 + relPos + (charOffset - acc); return false; }
        acc += len;
      }
      return true;
    });
    if (out === null) out = nodeStartPos + node.nodeSize - 1;   // offset at the very end
    return out;
  };"""

# The engine. Runs in the live post's editor. Stages edits only; never publishes.
REPATCH_JS = r"""(() => {
  const TITLE = %TITLE%, SUBTITLE = %SUBTITLE%, BODY = %BODY%, FNS = %FNS%;
  const root = document.querySelector('.ProseMirror');
  if (!root || !root.editor) return JSON.stringify({ error: 'no editor found — open the live post at /publish/post/<id>' });
  const ed = root.editor;
%HELPERS%

  // --- title / subtitle: set only if changed (a no-op set would still dirty the doc) ---
  const setField = (sel, v) => {
    const el = document.querySelector(sel);
    if (!el || el.value === v) return false;
    const d = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
    d.set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  };
  const titleChanged = setField('textarea[placeholder="Title"]', TITLE);
  const subtitleChanged = setField('textarea[placeholder="Add a subtitle…"]', SUBTITLE);

  // --- scrape live: ordered top nodes, split body vs footnote, keep positions + node refs ---
  // Typography: Substack curls straight quotes as the body is pasted, so the live doc
  // and the draft's reader-text disagree on every quote mark. Compare FLATTENED text
  // (curly -> straight, a 1:1 substitution that preserves length, so offsets computed
  // on it are valid against the real doc), and SMARTEN anything actually inserted so
  // it matches the typography of the document it lands in.
  // (typography helpers come from JS_HELPERS)

  const liveBody = [], liveFns = [];
  ed.state.doc.forEach((node, pos) => {
    const raw = node.textContent;
    const rec = { pos, node, raw, text: flat(raw) };
    if (node.type.name === 'footnote') liveFns.push(rec);
    else if (isBodyNode(node)) liveBody.push(rec);
  });

  const report = {
    titleChanged, subtitleChanged, structural: false,
    bodyBlocks: { live: liveBody.length, target: BODY.length },
    footnotes: { live: liveFns.length, target: FNS.length },
    applied: [], unchanged: 0, footnoteChanges: [], failed: [], reviewMarks: []
  };

  // structural guard: counts must match 1:1, else this is a rewrite — refuse.
  if (liveBody.length !== BODY.length || liveFns.length !== FNS.length) {
    report.structural = true;
    report.note = 'block/footnote count differs — structural change, not a touch-up. Refusing to patch; use a full recompose or edit by hand.';
    return JSON.stringify(report);
  }

  // GUARD: a permutation preserves the count, so the count check above cannot see one.
  // Before 2026-09-01 that was the only structural check, and a piece whose footnotes
  // were emitted in label order against a live doc in reference order passed it 30 == 30
  // with all thirty mismatched — the re-sync would have overwritten every note of a live
  // essay with another note's text. If a target block's exact text lives at a DIFFERENT
  // live index, the two lists are misaligned, not edited: refuse and say so.
  const findReorder = (targets, live, kind) => {
    const at = new Map();
    live.forEach((l, i) => { if (!at.has(sameText(l.text))) at.set(sameText(l.text), i); });
    const out = [];
    for (let i = 0; i < targets.length; i++) {
      if (sameText(targets[i]) === sameText(live[i].text)) continue;
      const j = at.get(sameText(targets[i]));
      if (j !== undefined && j !== i) out.push({ kind, targetIdx: i, livesAtIdx: j });
    }
    return out;
  };
  // GUARD: and a pair that is neither equal nor plausibly the same node (a one-word fix
  // leaves a long block ~99% intact) means the lists are misaligned some other way.
  const similarity = (a, b) => {
    if (!a.length && !b.length) return 1;
    let p = 0; while (p < a.length && p < b.length && a[p] === b[p]) p++;
    let q = 0; while (q < a.length - p && q < b.length - p && a[a.length-1-q] === b[b.length-1-q]) q++;
    return (p + q) / Math.max(a.length, b.length);
  };
  const findSuspect = (targets, live, kind) => {
    const out = [];
    for (let i = 0; i < targets.length; i++) {
      if (sameText(targets[i]) === sameText(live[i].text)) continue;
      const sim = similarity(live[i].text, targets[i]);
      if (sim < 0.5) out.push({ kind, idx: i, similarity: +sim.toFixed(3),
                                live: live[i].text.slice(0, 90), target: targets[i].slice(0, 90) });
    }
    return out;
  };

  report.reordered = [...findReorder(BODY, liveBody, 'body'), ...findReorder(FNS, liveFns, 'footnote')];
  report.suspect   = [...findSuspect(BODY, liveBody, 'body'), ...findSuspect(FNS, liveFns, 'footnote')];
  if (report.reordered.length || report.suspect.length) {
    report.structural = true;
    report.note = report.reordered.length
      ? 'target text found at a DIFFERENT live index — the two lists are misaligned, not edited. Refusing to patch; nothing was changed.'
      : 'a changed pair is too dissimilar to be the same node — likely misalignment. Refusing to patch; nothing was changed.';
    return JSON.stringify(report);
  }

  // (diff + offset helpers come from JS_HELPERS)

  // one task per hunk, across body then footnotes
  const tasks = [];
  const plan = (targets, live, kind) => {
    for (let idx = 0; idx < targets.length; idx++) {
      if (sameText(targets[idx]) === sameText(live[idx].text)) { report.unchanged++; continue; }
      const hunks = diffHunks(live[idx].text, targets[idx]);
      if (!hunks.length) { report.unchanged++; continue; }
      for (const h of hunks) tasks.push({ kind, idx, node: live[idx].node, raw: live[idx].raw,
                                          nodePos: live[idx].pos, hunk: h });
    }
  };
  plan(BODY, liveBody, 'body');
  plan(FNS, liveFns, 'footnote');

  // apply latest-position-first (node then offset, both descending) so every not-yet-applied
  // position stays valid across edits.
  tasks.sort((a, b) => (b.nodePos - a.nodePos) || (b.hunk.aStart - a.hunk.aStart));
  for (const t of tasks) {
    try {
      const from = offsetToPos(t.node, t.nodePos, t.hunk.aStart);
      const to = offsetToPos(t.node, t.nodePos, t.hunk.aEnd);
      const state = ed.state;
      const marks = state.doc.resolve(from).marks();
      const endMarks = state.doc.resolve(Math.max(from, to)).marks();
      const uniform = marks.length === endMarks.length && marks.every(m => endMarks.some(e => e.eq(m)));
      let tr = state.tr;
      const prevCh = t.hunk.aStart > 0 ? t.raw[t.hunk.aStart - 1] : ' ';
      const insert = smarten(t.hunk.text, prevCh);
      if (insert.length) tr = tr.replaceWith(from, to, state.schema.text(insert, marks));
      else tr = tr.delete(from, to);
      ed.view.dispatch(tr);
      const entry = { kind: t.kind, block: t.idx, insert: insert || '(deleted)' };
      report.applied.push(entry);
      if (t.kind === 'footnote') report.footnoteChanges.push(entry);
      if (!uniform || t.hunk.big) report.reviewMarks.push(entry);
    } catch (e) {
      report.failed.push({ kind: t.kind, block: t.idx, error: String(e) });
    }
  }
  report.stagedEdits = report.applied.length;
  return JSON.stringify(report);
})()
"""

def build_structural(piece_dir, man, body, fns):
    """Bake the draft as a TARGET the structural engine can align against a live doc:
    per body block its reader-text, its HTML (quotes smartened outside tags), the names of
    the footnote anchors it carries, whether a divider precedes it, and a sha256/16 of the
    reader-text — the hash is computed HERE so that a snippet retyped into a browser eval
    fails closed on any transcription slip. Footnotes carry name, text and hash in
    first-reference order, which is the order the live doc holds them."""
    import re, hashlib
    from md_to_substack import parse_blocks, strip_to_reader, smarten_quotes
    blocks, ordered, *_rest = parse_blocks(piece_dir)
    H = lambda t: hashlib.sha256(flatten_quotes(re.sub(r'\s+', ' ', t).strip()).encode()).hexdigest()[:16]
    def smart(h):   # smarten the text, never the tags: a curled quote inside href="…" is a dead link
        return ''.join(x if x.startswith('<') else smarten_quotes(x) for x in re.split(r'(<[^>]+>)', h))
    tbody, hr_before = [], False
    for b in blocks:
        if b.strip() == '<hr>':
            hr_before = True
            continue
        txt = strip_to_reader(b)
        if not txt:
            continue
        tbody.append({'text': txt, 'html': smart(b), 'anchors': re.findall(r'\[\[FN(\w+)\]\]', b),
                      'hrBefore': hr_before, 'hash': H(txt)})
        hr_before = False
    if [t['text'] for t in tbody] != list(body):
        print("Refusing: the structural builder's block list does not match render_reader's — "
              "the two walk the draft differently; fix that before trusting either.")
        sys.exit(5)
    tfns = [{'name': str(n), 'text': t, 'hash': H(t)} for (n, _c), t in zip(ordered, fns)]
    target = {'title': man.get('title', ''), 'subtitle': man.get('subtitle', ''),
              'body': tbody, 'fns': tfns}
    print(f"structural target: {len(tbody)} body block(s), {len(tfns)} footnote(s), "
          f"{sum(len(t['anchors']) for t in tbody)} anchor(s), "
          f"{sum(1 for t in tbody if '<a ' in t['html'])} block(s) with links")
    return (STRUCTURAL_JS.replace('%HELPERS%', JS_HELPERS)
                         .replace('%TARGET%', json.dumps(target, ensure_ascii=False)))


# The structural engine. Runs once in the live post's editor. Applies nothing on a refusal;
# stages edits only; never publishes. Returns a JSON report with `refused`, `applied`,
# `failed`, `final` and `ok`.
STRUCTURAL_JS = r"""(async () => {
  const TARGET = /*T*/%TARGET%/*T*/;
  const root = document.querySelector('.ProseMirror');
  if (!root || !root.editor) return JSON.stringify({ error: 'no editor found — open the live post at /publish/post/<id>' });
  const ed = root.editor;
%HELPERS%
  const sha = async s => {
    const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
    return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('').slice(0, 16);
  };
  const T = TARGET;
  const report = { mode: 'structural', refused: null, ok: false, applied: [], failed: [],
                   titleChanged: false, subtitleChanged: false,
                   plan: { replace: 0, insert: 0, delete: 0, hunk: 0, fnHunk: 0, dropAnchor: 0 } };
  const refuse = (why, extra) => { report.refused = why; Object.assign(report, extra || {}); return JSON.stringify(report); };

  // --- scrape the live doc: body nodes with their anchors (numbered in document order, which
  //     is the order the footnote nodes hold), footnote nodes, and whether a divider precedes
  //     each body node ---
  const scrape = () => {
    const body = [], fns = []; let seq = 0, hrBefore = false;
    ed.state.doc.forEach((node, pos) => {
      if (node.type.name === 'footnote') { fns.push({ node, pos, text: node.textContent }); return; }
      if (node.type.name === 'horizontalRule' || node.type.name === 'hr') { hrBefore = true; return; }
      if (!isBodyNode(node)) return;
      const anchors = [];
      node.descendants((c, rel) => { if (c.type.name === 'footnoteAnchor') anchors.push({ pos: pos + 1 + rel, size: c.nodeSize, seq: seq++ }); });
      body.push({ node, pos, text: node.textContent, anchors, hrBefore });
      hrBefore = false;
    });
    return { body, fns };
  };

  // --- 0. transcription guard: every block that will travel as HTML must hash to its own text ---
  for (let j = 0; j < T.body.length; j++) {
    const b = T.body[j];
    if (b.anchors.length) continue;                       // anchor blocks never travel as HTML
    if (b.html.includes('[[FN')) return refuse('html block ' + j + ' carries a footnote marker but declares no anchor', { block: j });
    const kids = [...new DOMParser().parseFromString(b.html, 'text/html').body.children];
    if (kids.length !== 1) return refuse('html block ' + j + ' parses to ' + kids.length + ' elements, not 1', { block: j });
    if (await sha(sameText(kids[0].textContent)) !== b.hash)
      return refuse('transcription: html block ' + j + ' does not hash to its own reader-text — the snippet was altered between the generator and this eval', { block: j });
  }

  // --- 1. align live body against target body by text (LCS on normalized block text) ---
  const live = scrape();
  const eqL = live.body.map(b => sameText(b.text)), eqT = T.body.map(b => sameText(b.text));
  const lcsPairs = (A, B) => {
    const n = A.length, m = B.length;
    const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
      dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    const pairs = []; let i = 0, j = 0;
    while (i < n && j < m) { if (A[i] === B[j]) { pairs.push([i, j]); i++; j++; } else if (dp[i + 1][j] >= dp[i][j + 1]) i++; else j++; }
    return pairs;
  };
  const pairs = lcsPairs(eqL, eqT);
  const ranges = []; let pi = 0, pj = 0;
  for (const [i, j] of [...pairs, [live.body.length, T.body.length]]) {
    if (i > pi || j > pj) ranges.push({ i1: pi, i2: i, j1: pj, j2: j });
    pi = i + 1; pj = j + 1;
  }

  // --- 2. plan. Nothing is dispatched until every check below has passed. ---
  const ops = [], anchorPairs = [], dropAnchors = [];
  // equal blocks: the anchors must agree in count, or the draft has retired every one of them
  for (const [i, j] of pairs) {
    const la = live.body[i].anchors, ta = T.body[j].anchors;
    if (la.length === ta.length) la.forEach((a, k) => anchorPairs.push({ seq: a.seq, name: ta[k] }));
    else if (ta.length === 0) la.forEach(a => dropAnchors.push({ liveIdx: i, anchor: a }));
    else if (la.length === 0) return refuse('the draft adds footnote(s) to block ' + i + ' (' + ta.map(n => '[[FN' + n + ']]').join(' ') + ') that the live post lacks — insertFootnote is not automated here; add them by hand in the composer, or recompose', { liveIdx: i, targetIdx: j, added: ta });
    else return refuse('block ' + i + ' has ' + la.length + ' anchor(s) live and ' + ta.length + ' in the draft with identical text — cannot tell which to keep', { liveIdx: i, targetIdx: j });
  }
  // changed ranges: split at anchor-bearing blocks, which pair 1:1 by order and go by text hunk
  const emitReplace = (i1, i2, j1, j2) => {
    if (i1 === i2 && j1 === j2) return;
    ops.push({ kind: 'replace', i1, i2, j1, j2 });
    report.plan[i1 === i2 ? 'insert' : j1 === j2 ? 'delete' : 'replace']++;
  };
  for (const r of ranges) {
    const la = [], ta = [];
    for (let i = r.i1; i < r.i2; i++) if (live.body[i].anchors.length) la.push(i);
    for (let j = r.j1; j < r.j2; j++) if (T.body[j].anchors.length) ta.push(j);
    if (la.length !== ta.length)
      return refuse('anchor-bearing blocks do not pair 1:1 inside a changed range — un-merge or re-split the draft so each footnote-bearing paragraph has a live counterpart', { range: r, liveAnchorBlocks: la, targetAnchorBlocks: ta });
    let ci = r.i1, cj = r.j1;
    for (let k = 0; k < la.length; k++) {
      const i = la[k], j = ta[k];
      if (live.body[i].anchors.length !== T.body[j].anchors.length)
        return refuse('anchor count differs between paired blocks', { liveIdx: i, targetIdx: j });
      emitReplace(ci, i, cj, j);
      live.body[i].anchors.forEach((a, q) => anchorPairs.push({ seq: a.seq, name: T.body[j].anchors[q] }));
      if (eqL[i] !== eqT[j]) { ops.push({ kind: 'hunk', liveIdx: i, targetIdx: j }); report.plan.hunk++; }
      ci = i + 1; cj = j + 1;
    }
    emitReplace(ci, r.i2, cj, r.j2);
  }
  // footnotes follow their anchors
  const seqToName = new Map(anchorPairs.map(p => [p.seq, p.name]));
  const nameToTarget = new Map(T.fns.map((f, j) => [f.name, j]));
  const droppedSeqs = new Set(dropAnchors.map(d => d.anchor.seq));
  const totalLiveAnchors = anchorPairs.length + dropAnchors.length;
  if (live.fns.length !== totalLiveAnchors)
    return refuse('the live document has ' + live.fns.length + ' footnote node(s) but ' + totalLiveAnchors + ' anchor(s)', { footnotes: live.fns.length, anchors: totalLiveAnchors });
  const fnPairs = [];
  for (let k = 0; k < live.fns.length; k++) {
    if (droppedSeqs.has(k)) continue;
    const name = seqToName.get(k);
    const j = nameToTarget.get(name);
    if (j === undefined) return refuse('live footnote ' + k + ' pairs with anchor [[FN' + name + ']], which names no footnote in the draft', { fn: k, name });
    fnPairs.push({ k, j });
  }
  const covered = new Set(fnPairs.map(p => p.j));
  const added = T.fns.map((f, j) => j).filter(j => !covered.has(j)).map(j => T.fns[j].name);
  if (added.length) return refuse('the draft adds footnote(s) the live post lacks — insertFootnote is not automated here; add them by hand in the composer, or recompose', { added });
  for (let a = 1; a < fnPairs.length; a++) if (fnPairs[a].j <= fnPairs[a - 1].j)
    return refuse('footnote order differs between the draft and the live post', { fnPairs });
  for (const p of fnPairs) if (sameText(live.fns[p.k].text) !== sameText(T.fns[p.j].text)) { ops.push({ kind: 'fnHunk', k: p.k, j: p.j }); report.plan.fnHunk++; }
  for (const d of dropAnchors) { ops.push({ kind: 'dropAnchor', liveIdx: d.liveIdx, seq: d.anchor.seq }); report.plan.dropAnchor++; }

  // --- 3. apply, latest document position first, re-reading the doc before every op ---
  const keyOf = o => o.kind === 'fnHunk' ? 1e6 + o.k : o.kind === 'replace' ? (o.i1 === o.i2 ? o.i1 - 0.5 : o.i1) : o.liveIdx;
  ops.sort((a, b) => keyOf(b) - keyOf(a));
  const hunkNode = (rec, targetText, label) => {
    const hunks = diffHunks(flat(rec.text), targetText).sort((a, b) => b.aStart - a.aStart);
    for (const h of hunks) {
      const from = offsetToPos(rec.node, rec.pos, h.aStart), to = offsetToPos(rec.node, rec.pos, h.aEnd);
      const st = ed.state;
      let inl = 0; st.doc.nodesBetween(from, to, n => { if (!n.isText && n.isInline) inl++; });
      if (inl) throw new Error(label + ': a hunk spans an inline node (a footnote anchor) — refusing to edit across it');
      if (flat(st.doc.textBetween(from, to)) !== flat(rec.text).slice(h.aStart, h.aEnd)) throw new Error(label + ': position guard failed');
      const marks = st.doc.resolve(from).marks(), endMarks = st.doc.resolve(Math.max(from, to)).marks();
      const uniform = marks.length === endMarks.length && marks.every(m => endMarks.some(e => e.eq(m)));
      if (!uniform) throw new Error(label + ': a hunk crosses a formatting boundary — split the change so each run is uniform');
      const ins = smarten(h.text, h.aStart > 0 ? rec.text[h.aStart - 1] : ' ');
      ed.view.dispatch(ins.length ? st.tr.replaceWith(from, to, st.schema.text(ins, marks)) : st.tr.delete(from, to));
    }
  };
  const endOf = r => r.pos + r.node.nodeSize;
  try {
    for (const o of ops) {
      const L = scrape();
      if (o.kind === 'fnHunk') {
        hunkNode(L.fns[o.k], T.fns[o.j].text, 'footnote ' + o.k);
        if (await sha(sameText(scrape().fns[o.k].text)) !== T.fns[o.j].hash) throw new Error('footnote ' + o.k + ' did not land as the draft has it');
        report.applied.push({ kind: 'fnHunk', footnote: o.k });
      } else if (o.kind === 'hunk') {
        hunkNode(L.body[o.liveIdx], T.body[o.targetIdx].text, 'block ' + o.liveIdx);
        if (await sha(sameText(scrape().body[o.liveIdx].text)) !== T.body[o.targetIdx].hash) throw new Error('block ' + o.liveIdx + ' did not land as the draft has it');
        report.applied.push({ kind: 'hunk', block: o.liveIdx });
      } else if (o.kind === 'dropAnchor') {
        const rec = L.body[o.liveIdx]; const a = rec.anchors.find(x => x.seq === o.seq);
        if (!a) throw new Error('anchor ' + o.seq + ' not found in block ' + o.liveIdx);
        ed.view.dispatch(ed.state.tr.delete(a.pos, a.pos + a.size));
        const after = scrape();
        if (sameText(after.body[o.liveIdx].text) !== sameText(rec.text)) throw new Error('block ' + o.liveIdx + ' changed text when its anchor was dropped');
        if (after.fns.length === L.fns.length) {          // the editor did not remove the orphan itself
          const F = after.fns[o.seq];
          if (sameText(F.text) !== sameText(L.fns[o.seq].text)) throw new Error('orphaned footnote ' + o.seq + ' is not where it was');
          ed.view.dispatch(ed.state.tr.delete(F.pos, F.pos + F.node.nodeSize));
        }
        report.applied.push({ kind: 'dropAnchor', block: o.liveIdx, footnote: o.seq });
      } else {
        const html = T.body.slice(o.j1, o.j2).map(b => b.html).join('');
        let from, to;
        if (o.i1 < o.i2) { from = L.body[o.i1].pos; to = endOf(L.body[o.i2 - 1]); }
        else if (o.i1 >= L.body.length) { from = to = L.body.length ? endOf(L.body[L.body.length - 1]) : 0; }
        // an insert lands on the draft's side of any divider: after the divider if the draft
        // puts one before the new block, otherwise right after the preceding block
        else if (T.body[o.j1].hrBefore || o.i1 === 0) { from = to = L.body[o.i1].pos; }
        else { from = to = endOf(L.body[o.i1 - 1]); }
        if (o.j1 === o.j2) ed.view.dispatch(ed.state.tr.delete(from, to));
        else ed.commands.insertContentAt({ from, to }, html);
        const after = scrape();
        for (let q = 0; q < o.j2 - o.j1; q++)
          if (await sha(sameText(after.body[o.i1 + q].text)) !== T.body[o.j1 + q].hash) throw new Error('replaced block ' + (o.i1 + q) + ' did not land as the draft has it');
        report.applied.push({ kind: o.i1 === o.i2 ? 'insert' : o.j1 === o.j2 ? 'delete' : 'replace', at: o.i1, blocks: o.j2 - o.j1 });
      }
    }
  } catch (e) { report.failed.push(String(e)); }

  // --- 4. title / subtitle, only if changed ---
  const setField = (sel, v) => {
    const el = document.querySelector(sel);
    if (!el || el.value === v) return false;
    const d = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
    d.set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  };
  report.titleChanged = setField('textarea[placeholder="Title"]', T.title);
  report.subtitleChanged = setField('textarea[placeholder="Add a subtitle…"]', T.subtitle);

  // --- 5. read the whole document back; the report is evidence, not a claim ---
  const F = scrape();
  const bodyMismatch = []; for (let i = 0; i < Math.max(F.body.length, T.body.length); i++) if (!F.body[i] || !T.body[i] || sameText(F.body[i].text) !== eqT[i]) bodyMismatch.push(i);
  const fnMismatch = []; for (let k = 0; k < Math.max(F.fns.length, T.fns.length); k++) if (!F.fns[k] || !T.fns[k] || sameText(F.fns[k].text) !== sameText(T.fns[k].text)) fnMismatch.push(k);
  const anchors = F.body.reduce((n, b) => n + b.anchors.length, 0), wantAnchors = T.body.reduce((n, b) => n + b.anchors.length, 0);
  const linksMissing = [], dividersOff = [];
  F.body.forEach((b, i) => {
    const t = T.body[i]; if (!t) return;
    if ((t.html.match(/<a /g) || []).length) { let n = 0; b.node.descendants(c => { if (c.isText && c.marks && c.marks.some(m => m.type.name === 'link')) n++; }); if (!n) linksMissing.push(i); }
    if (!!b.hrBefore !== !!t.hrBefore) dividersOff.push(i);
  });
  report.final = { body: F.body.length + '/' + T.body.length, footnotes: F.fns.length + '/' + T.fns.length,
                   anchors: anchors + '/' + wantAnchors, bodyMismatch, fnMismatch, linksMissing, dividersOff,
                   firstNode: ed.state.doc.firstChild ? ed.state.doc.firstChild.type.name : null };
  report.ok = !report.failed.length && !bodyMismatch.length && !fnMismatch.length && anchors === wantAnchors && !linksMissing.length;
  return JSON.stringify(report);
})()
"""


if __name__ == '__main__':
    main()
