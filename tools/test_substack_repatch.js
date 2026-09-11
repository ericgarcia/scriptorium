#!/usr/bin/env node
/*
 * test_substack_repatch.js — run the surgical patch engine against a STUBBED ProseMirror
 * doc, so its guards can be exercised without staging edits on a live public essay.
 *
 *   python3 tools/substack_repatch.py <piece-dir> /tmp/p.js
 *   node tools/test_substack_repatch.js /tmp/p.js
 *
 * It builds the "live" doc out of the snippet's own baked target — text AND marks, so an
 * untouched document is a genuine no-op rather than a document that merely has no
 * formatting at all — curls the quotes the way Substack does on paste, and perturbs it:
 *
 *   A  one word changed          -> exactly that block is patched, nothing else, failed[] empty
 *   B  footnotes reordered       -> REFUSES, stages nothing (the count-only guard could not
 *                                   see a permutation; this is the case that once aligned 30
 *                                   footnotes against the wrong 30 live nodes)
 *   C  typography differs only   -> no-op (straight-vs-curly quotes are not content)
 *   D  edit beside an anchor     -> the inline node is spared
 *   E  whitespace differs only   -> no-op
 *   F  ONE MARK REMOVED          -> the text matches everywhere, and the mark is put back
 *   G  two edits, far apart      -> patched, NOT flagged suspect (son-of-joseph [^almah])
 *   H  a footnote misaligned     -> REFUSES as suspect, stages nothing
 *
 * F is the case the whole chain used to pass. Measured on `rising-after-falls` 2026-09-09:
 * italicising two words produced a regenerated patch byte-identical in size to the previous
 * one, which reported `unchanged` and applied nothing, after which a digest check reported
 * MATCH with the italic absent from the live post. Every check above F compares reader-text
 * and none of them can see it.
 *
 * The document model lives in test_editor_stub.js, shared with test_substack_structural.js.
 *
 * This file exists because it has already paid for itself: on its first run it caught the
 * patcher reading `raw` off the wrong object, which would have thrown on every insertion.
 */
const fs = require('fs');
const { curl, parseInline, topFromRuns, runsOf, makeEditor, install } = require('./test_editor_stub.js');

const snippetPath = process.argv[2];
if (!snippetPath) {
  console.error('usage: node test_substack_repatch.js <repatch-snippet.js>');
  process.exit(2);
}
const src = fs.readFileSync(snippetPath, 'utf8');

// recover the snippet's own baked-in target
const BODY = JSON.parse(src.match(/BODY = (\[[\s\S]*?\]), FNS/)[1]);
const FNS = JSON.parse(src.match(/FNS = (\[[\s\S]*?\]);\n/)[1]);
const TITLE = JSON.parse(src.match(/TITLE = ("(?:[^"\\]|\\.)*")/)[1]);
const SUBTITLE = JSON.parse(src.match(/SUBTITLE = ("(?:[^"\\]|\\.)*")/)[1]);
const BODYMARKS = JSON.parse(src.match(/BODYMARKS = (\[[\s\S]*?\]), FNMARKS/)[1]);
const FNMARKS = JSON.parse(src.match(/FNMARKS = (\[[\s\S]*?\]);\n/)[1]);

// A "live" top node from reader-text plus the runs the snippet baked in, quotes curled the
// way Substack curls them on paste. `marks` defaults to the target's own, so cases that mean
// to change only the text leave the formatting alone.
const liveTop = (name, text, runs) => {
  const top = topFromRuns(name, text, runs || []);
  top.kids = top.kids.map(k => ({ ...k, text: curl(k.text) }));
  return top;
};

function run(bodyTexts, fnTexts, title, subtitle, bodyMarks, fnMarks) {
  const tops = [];
  bodyTexts.forEach((t, i) => tops.push(liveTop('paragraph', t, (bodyMarks || BODYMARKS)[i])));
  fnTexts.forEach((t, i) => tops.push(liveTop('footnote', t, (fnMarks || FNMARKS)[i])));
  const { editor, dispatches, tops: live } = makeEditor(tops);
  install(editor, { 'textarea[placeholder="Title"]': { value: title },
                    'textarea[placeholder="Add a subtitle…"]': { value: subtitle } });
  return { report: JSON.parse(eval(src)), dispatches: dispatches(), tops: live };
}

let failures = 0;
const check = (name, ok, detail) => {
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${name}${detail ? '   ' + detail : ''}`);
  if (!ok) failures++;
};
const skip = (name, why) => console.log(`skip  ${name}   (${why})`);
const norm = s => s.replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/\s+/g, ' ').trim();

// --- A: a single real edit is applied, and only there -----------------------
// The changed block's own marks are dropped from the live copy along with the text change,
// because inserting `ZQX ` mid-run shifts every offset after it; A is about the TEXT pass.
{
  const liveA = BODY.map(curl);
  const victim = liveA.findIndex(t => t.length > 200);
  liveA[victim] = liveA[victim].slice(0, 50) + 'ZQX ' + liveA[victim].slice(50);
  const marksA = BODYMARKS.map((m, i) => (i === victim ? [] : m));
  const a = run(liveA, FNS.map(curl), TITLE, SUBTITLE, marksA, FNMARKS);
  check('A one changed block is patched',
    !a.report.structural && a.report.applied.length > 0 && a.report.failed.length === 0
    && a.report.applied.every(x => x.block === victim),
    `staged=${a.report.stagedEdits} unchanged=${a.report.unchanged} failed=${a.report.failed.length}`);
}

// --- B: a permutation is refused, and stages nothing ------------------------
// Reversing fewer than two footnotes is the identity, so there is no permutation to detect and
// the case is INAPPLICABLE, not passing. Reported as a skip: a green tick for a check that
// could not have run is the kind of coverage that lies. (`Flow` has one footnote.)
if (FNS.length < 2) {
  skip('B reordered footnotes refuse', `needs >=2 footnotes, piece has ${FNS.length}`);
} else {
  const b = run(BODY.map(curl), FNS.map(curl).slice().reverse(), TITLE, SUBTITLE,
                BODYMARKS, FNMARKS.slice().reverse());
  check('B reordered footnotes refuse',
    b.report.structural && b.report.reordered.length > 0 && b.dispatches === 0,
    `reordered=${b.report.reordered.length} dispatches=${b.dispatches}`);
}

// --- C: curly-vs-straight quotes are not a content difference ---------------
{
  const c = run(BODY.map(curl), FNS.map(curl), TITLE, SUBTITLE);
  check('C typography-only diff is a no-op',
    !c.report.structural && c.report.stagedEdits === 0 && c.dispatches === 0,
    `unchanged=${c.report.unchanged}/${BODY.length + FNS.length} marksUnchanged=${c.report.marks.unchanged} review=${JSON.stringify(c.report.marks.review).slice(0, 120)}`);
}

// --- D: an edit whose boundary sits on an inline node must not consume it ----
// `Both Ends of the Leash` (2026-09-01): a paragraph reading
//   "...it.[anchor 10] [anchor 11] The behavior..."
// and an edit at the boundary removed footnote 11 from a LIVE post, because an offset landing
// on a text-node boundary resolved to the END of that run — which is the inline node's
// position. Uses a REAL character change, not whitespace: whitespace-only differences are no
// longer attempted at all (see sameText), so they can no longer exercise this path.
{
  const tops = [{ name: 'paragraph', kids: parseInline('abc[[FN1]]def') }];
  const { editor, tops: live } = makeEditor(tops);
  install(editor, { 'textarea[placeholder="Title"]': { value: TITLE },
                    'textarea[placeholder="Add a subtitle…"]': { value: SUBTITLE } });
  // change the character immediately AFTER the anchor: reader offset 3, 'd' -> 'X'
  const patched = src
    .replace(/BODY = \[[\s\S]*?\], FNS = \[[\s\S]*?\];/, 'BODY = ["abcXef"], FNS = [];')
    .replace(/BODYMARKS = \[[\s\S]*?\], FNMARKS = \[[\s\S]*?\];/, 'BODYMARKS = [[]], FNMARKS = [];');
  const report = JSON.parse(eval(patched));
  const survived = live[0].kids.filter(k => k.anchor).length;
  check('D boundary edit spares an inline anchor',
    report.applied.length > 0 && survived === 1 && live[0].kids.filter(k => !k.anchor).map(k => k.text).join('') === 'abcXef',
    `anchors=${survived} text=${JSON.stringify(live[0].kids.map(k => k.anchor ? '[FN]' : k.text).join(''))}`);
}

// --- E: a whitespace-only difference is not a difference --------------------
// HTML collapses runs, and `strip_to_reader` collapses them on the draft side, so a live post
// with a double space describes a block no draft can ever produce. Left comparable, it reports
// a phantom edit on every sync forever — and chasing that phantom is what cost a footnote.
{
  const idx = BODY.findIndex(t => t.includes('. '));
  const liveE = BODY.map(curl);
  liveE[idx] = liveE[idx].replace('. ', '.  ');            // inject a double space
  // that block's own offsets shift by one, so it goes in unmarked; E is about the text pass
  const marksE = BODYMARKS.map((m, i) => (i === idx ? [] : m));
  const e = run(liveE, FNS.map(curl), TITLE, SUBTITLE, marksE, FNMARKS);
  const textEdits = e.report.applied.length;
  check('E whitespace-only difference is ignored',
    !e.report.structural && textEdits === 0,
    `textEdits=${textEdits} staged=${e.report.stagedEdits}`);
}

// --- F: a formatting-only difference IS a difference ------------------------
// The one the text digests cannot see. Every character is identical on both sides; the live
// copy is simply missing an italic. Before this pass existed the engine reported the whole
// document `unchanged`, dispatched nothing, and a verify run then said MATCH.
{
  const k = BODYMARKS.findIndex(runs => runs.some(r => r.kind !== 'link'));
  if (k < 0) skip('F a missing italic is detected and applied', 'no emphasis in any body block');
  else {
    const want = BODYMARKS[k].filter(r => r.kind !== 'link');
    const marksF = BODYMARKS.map((m, i) => (i === k ? m.filter(r => r.kind === 'link') : m));
    const f = run(BODY.map(curl), FNS.map(curl), TITLE, SUBTITLE, marksF, FNMARKS);
    const block = f.tops[k];
    const gotKeys = runsOf(block).map(r => r.kind + ' ' + norm(r.text));
    const wantKeys = want.map(r => r.kind + ' ' + norm(r.text));
    check('F a missing italic is detected and applied',
      f.report.applied.length === 0                       // no TEXT edit: there was none to make
      && f.report.marks.applied.length > 0
      && f.report.marks.failed.length === 0
      && JSON.stringify(gotKeys) === JSON.stringify(wantKeys)
      && block.kids.map(x => x.text).join('') === curl(BODY[k]),
      `want=${JSON.stringify(wantKeys)} got=${JSON.stringify(gotKeys)} marks=${JSON.stringify(f.report.marks.applied).slice(0, 160)}`);
  }
}

// --- G: two small edits far apart in one node are an edit, not a misalignment -----
// son-of-joseph's [^almah], 2026-09-11: two one-character fixes (`almah -> ʿalmah), one near
// the start of a 573-char note and one deep in it. The misalignment guard scored the pair
// 0.309 — prefix+suffix counted everything between the two fixes as changed — and refused a
// correct patch. Substitutions keep every offset, so the node's marks stay valid as baked.
{
  const pick = arr => arr.reduce((best, t, i) => (t.length > (best < 0 ? -1 : arr[best].length) ? i : best), -1);
  const fi = pick(FNS), bi = pick(BODY);
  const useFn = fi >= 0 && FNS[fi].length >= 200;
  const kind = useFn ? 'footnote' : 'body', idx = useFn ? fi : bi, orig = useFn ? FNS[fi] : BODY[bi];
  if (!orig || orig.length < 200) skip('G two scattered edits are patched, not suspect', 'no node of 200+ chars');
  else {
    const letterAt = (from, dir) => { let k = from; while (k >= 0 && k < orig.length && !/[a-z]/.test(orig[k])) k += dir; return k; };
    const at = [letterAt(Math.floor(orig.length * 0.05), 1), letterAt(Math.floor(orig.length * 0.9), -1)];
    let typo = orig;
    for (const k of at) typo = typo.slice(0, k) + (typo[k] === 'q' ? 'x' : 'q') + typo.slice(k + 1);
    const liveB = BODY.map(curl), liveF = FNS.map(curl);
    (useFn ? liveF : liveB)[idx] = curl(typo);
    const g = run(liveB, liveF, TITLE, SUBTITLE, BODYMARKS, FNMARKS);
    const node = g.tops[(useFn ? BODY.length : 0) + idx];
    const got = node.kids.filter(k => !k.anchor).map(k => k.text).join('');
    check('G two scattered edits are patched, not suspect',
      !g.report.structural && !(g.report.suspect || []).length && g.report.failed.length === 0
      && g.report.applied.length === 2 && g.report.applied.every(x => x.kind === kind && x.block === idx)
      && norm(got) === norm(orig),
      `${kind} ${idx} (${orig.length} chars) edits@${at} suspect=${JSON.stringify(g.report.suspect)} applied=${g.report.applied.length}`);
  }
}

// --- H: a footnote paired with a different note's text is refused ------------------
// The guard G must not loosen. The live note is replaced by text that exists nowhere in the
// footnote list — so the reorder guard cannot see it and the count still matches — and it is
// chosen ADVERSARIALLY: the body block nearest the note in length, the pairing most likely to
// share common words by chance.
if (!FNS.length) {
  skip('H a misaligned footnote is refused as suspect', 'piece has no footnotes');
} else {
  const i = FNS.reduce((best, t, k) => (t.length > FNS[best].length ? k : best), 0);
  const fnSet = new Set(FNS.map(t => norm(t)));
  const pool = BODY.filter(t => !fnSet.has(norm(t)));
  const other = pool.reduce((best, t) => (best === null || Math.abs(t.length - FNS[i].length) < Math.abs(best.length - FNS[i].length) ? t : best), null);
  const liveF = FNS.map(curl); liveF[i] = curl(other);
  const marksH = FNMARKS.map((m, k) => (k === i ? [] : m));
  const h = run(BODY.map(curl), liveF, TITLE, SUBTITLE, BODYMARKS, marksH);
  check('H a misaligned footnote is refused as suspect',
    h.report.structural && (h.report.suspect || []).some(s => s.kind === 'footnote' && s.idx === i) && h.dispatches === 0,
    `footnote ${i} vs body text of ${other.length} chars suspect=${JSON.stringify((h.report.suspect || []).map(s => [s.idx, s.similarity]))} dispatches=${h.dispatches}`);
}

process.exit(failures ? 1 : 0);
