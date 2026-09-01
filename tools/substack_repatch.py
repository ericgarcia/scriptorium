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
        print(f"WARNING: {len(residual)} footnote(s) still contain 'verify' after cleaning: "
              f"{residual}. Resolve the note (verify -> move behind a †, or delete) before republishing.")
        print("Refusing to write output.")
        sys.exit(2)

    if fn_issues['undefined'] or fn_issues['duplicated']:
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

    js = (REPATCH_JS
          .replace('%TITLE%', json.dumps(man.get('title', '')))
          .replace('%SUBTITLE%', json.dumps(man.get('subtitle', '')))
          .replace('%BODY%', json.dumps(body))
          .replace('%FNS%', json.dumps(fns)))
    open(out_js, 'w').write(js)
    print(f"wrote {out_js} ({len(js)} bytes)")


# The engine. Runs in the live post's editor. Stages edits only; never publishes.
REPATCH_JS = r"""(() => {
  const TITLE = %TITLE%, SUBTITLE = %SUBTITLE%, BODY = %BODY%, FNS = %FNS%;
  const root = document.querySelector('.ProseMirror');
  if (!root || !root.editor) return JSON.stringify({ error: 'no editor found — open the live post at /publish/post/<id>' });
  const ed = root.editor;

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
  const flat = s => s.replace(/[\u2018\u2019]/g, "'").replace(/[\u201c\u201d]/g, '"');
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

  const liveBody = [], liveFns = [];
  ed.state.doc.forEach((node, pos) => {
    const raw = node.textContent;
    const rec = { pos, node, raw, text: flat(raw) };
    if (node.type.name === 'footnote') liveFns.push(rec);
    else if (raw.trim() !== '') liveBody.push(rec);
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
    live.forEach((l, i) => { if (!at.has(l.text)) at.set(l.text, i); });
    const out = [];
    for (let i = 0; i < targets.length; i++) {
      if (targets[i] === live[i].text) continue;
      const j = at.get(targets[i]);
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
      if (targets[i] === live[i].text) continue;
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
    let acc = 0, out = null;
    node.descendants((child, relPos) => {
      if (out !== null) return false;
      if (child.isText) {
        const len = child.text.length;
        if (charOffset <= acc + len) { out = nodeStartPos + 1 + relPos + (charOffset - acc); return false; }
        acc += len;
      }
      return true;
    });
    if (out === null) out = nodeStartPos + node.nodeSize - 1;
    return out;
  };

  // one task per hunk, across body then footnotes
  const tasks = [];
  const plan = (targets, live, kind) => {
    for (let idx = 0; idx < targets.length; idx++) {
      if (targets[idx] === live[idx].text) { report.unchanged++; continue; }
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

if __name__ == '__main__':
    main()
