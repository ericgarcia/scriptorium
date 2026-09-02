#!/usr/bin/env node
/*
 * test_substack_repatch.js — run the surgical patch engine against a STUBBED ProseMirror
 * doc, so its guards can be exercised without staging edits on a live public essay.
 *
 *   python3 tools/substack_repatch.py <piece-dir> /tmp/p.js
 *   node tools/test_substack_repatch.js /tmp/p.js
 *
 * It builds the "live" doc out of the snippet's own target text, curls the quotes the way
 * Substack does on paste, and then perturbs it three ways:
 *
 *   A  one word changed          -> exactly that block is patched, nothing else, failed[] empty
 *   B  footnotes reordered       -> REFUSES, stages nothing (the count-only guard could not
 *                                   see a permutation; this is the case that once aligned 30
 *                                   footnotes against the wrong 30 live nodes)
 *   C  typography differs only   -> no-op (straight-vs-curly quotes are not content)
 *
 * This file exists because it has already paid for itself: on its first run it caught the
 * patcher reading `raw` off the wrong object, which would have thrown on every insertion.
 */
const fs = require('fs');

const snippetPath = process.argv[2];
if (!snippetPath) {
  console.error('usage: node test_substack_repatch.js <repatch-snippet.js>');
  process.exit(2);
}
const src = fs.readFileSync(snippetPath, 'utf8');

// approximate Substack's smart-quote input rules
const curl = s => s.replace(/(^|[\s(\[{—–-])"/g, '$1“').replace(/"/g, '”')
                   .replace(/(^|[\s(\[{—–-])'/g, '$1‘').replace(/'/g, '’');

function run(bodyTexts, fnTexts, title, subtitle) {
  const nodes = [];
  let pos = 0;
  const mk = (name, text) => {
    const n = {
      type: { name }, textContent: text, nodeSize: text.length + 2,
      descendants(cb) { cb({ isText: true, text }, 0); },
    };
    nodes.push({ node: n, pos });
    pos += n.nodeSize;
  };
  bodyTexts.forEach(t => mk('paragraph', t));
  fnTexts.forEach(t => mk('footnote', t));

  let dispatches = 0;
  const tr = { replaceWith() { return tr; }, delete() { return tr; } };
  const editor = {
    state: {
      tr,
      schema: { text: (t, m) => ({ t, m }) },
      doc: {
        forEach(cb) { nodes.forEach(({ node, pos }) => cb(node, pos)); },
        resolve() { return { marks: () => [] }; },
      },
    },
    view: { dispatch() { dispatches++; } },
  };
  const fields = {
    'textarea[placeholder="Title"]': { value: title },
    'textarea[placeholder="Add a subtitle…"]': { value: subtitle },
  };
  global.document = {
    querySelector: sel => (sel === '.ProseMirror' ? { editor } : (fields[sel] || null)),
  };
  return { report: JSON.parse(eval(src)), dispatches };
}

// recover the snippet's own baked-in target text
const BODY = JSON.parse(src.match(/BODY = (\[[\s\S]*?\]), FNS/)[1]);
const FNS = JSON.parse(src.match(/FNS = (\[[\s\S]*?\]);\n/)[1]);
const TITLE = JSON.parse(src.match(/TITLE = ("(?:[^"\\]|\\.)*")/)[1]);
const SUBTITLE = JSON.parse(src.match(/SUBTITLE = ("(?:[^"\\]|\\.)*")/)[1]);

let failures = 0;
const check = (name, ok, detail) => {
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${name}${detail ? '   ' + detail : ''}`);
  if (!ok) failures++;
};

// --- A: a single real edit is applied, and only there -----------------------
const liveA = BODY.map(curl);
const victim = liveA.findIndex(t => t.length > 200);
// a guaranteed, in-the-middle change: not every essay contains any given word
liveA[victim] = liveA[victim].slice(0, 50) + 'ZQX ' + liveA[victim].slice(50);
const a = run(liveA, FNS.map(curl), TITLE, SUBTITLE);
check('A one changed block is patched',
  !a.report.structural && a.report.stagedEdits > 0 && a.report.failed.length === 0
  && a.report.applied.every(x => x.block === victim),
  `staged=${a.report.stagedEdits} unchanged=${a.report.unchanged} failed=${a.report.failed.length}`);

// --- B: a permutation is refused, and stages nothing ------------------------
const b = run(BODY.map(curl), FNS.map(curl).slice().reverse(), TITLE, SUBTITLE);
check('B reordered footnotes refuse',
  b.report.structural && b.report.reordered.length > 0 && b.dispatches === 0,
  `reordered=${b.report.reordered.length} dispatches=${b.dispatches}`);

// --- C: curly-vs-straight quotes are not a content difference ---------------
const c = run(BODY.map(curl), FNS.map(curl), TITLE, SUBTITLE);
check('C typography-only diff is a no-op',
  !c.report.structural && c.report.stagedEdits === 0 && c.dispatches === 0,
  `unchanged=${c.report.unchanged}/${BODY.length + FNS.length}`);

// --- D: an edit whose boundary sits on an inline node must not delete it ----
// `Both Ends of the Leash` (2026-09-01): a paragraph reading
//   "...it.[anchor 10] [anchor 11] The behavior..."
// and a one-space delete removed footnote 11 from a LIVE post, because an offset landing on a
// text-node boundary resolved to the END of that run — which is the inline node's position.
// This rebuilds that shape in miniature and asserts the anchor survives.
{
  const nodes = [];
  let pos = 0;
  // children: text "A." | anchor | text " " | anchor | text " B"   => reader-text "A.  B"
  const parts = [
    { text: 'A.' }, { anchor: 1 }, { text: ' ' }, { anchor: 2 }, { text: ' B' },
  ];
  let rel = 0;
  const kids = parts.map(p => {
    const k = p.anchor
      ? { type: { name: 'footnoteAnchor' }, isText: false, nodeSize: 1, rel }
      : { type: { name: 'text' }, isText: true, text: p.text, nodeSize: p.text.length, rel };
    rel += k.nodeSize;
    return k;
  });
  const anchorPositions = kids.filter(k => !k.isText).map(k => 1 + k.rel);
  const para = {
    type: { name: 'paragraph' },
    textContent: parts.map(p => p.text || '').join(''),
    nodeSize: rel + 2,
    descendants(cb) { kids.forEach(k => cb(k, k.rel)); },
  };
  nodes.push({ node: para, pos });

  const ranges = [];
  const tr = { replaceWith(f, t) { ranges.push([f, t]); return tr; },
               delete(f, t) { ranges.push([f, t]); return tr; } };
  const editor = { state: { tr, schema: { text: (t, m) => ({ t, m }) },
    doc: { forEach(cb) { nodes.forEach(({ node, pos }) => cb(node, pos)); },
           resolve() { return { marks: () => [] }; } } },
    view: { dispatch() {} } };
  // title/subtitle must already equal the snippet's, so setField short-circuits before
  // touching a DOM prototype this stub does not have.
  const dFields = { 'textarea[placeholder="Title"]': { value: TITLE },
                    'textarea[placeholder="Add a subtitle…"]': { value: SUBTITLE } };
  global.document = { querySelector: sel => (sel === '.ProseMirror' ? { editor } : (dFields[sel] || null)) };
  // target: one space removed -> "A. B"
  const patched = src.replace(/BODY = \[[\s\S]*?\], FNS = \[[\s\S]*?\];/,
    'BODY = ["A. B"], FNS = [];');
  JSON.parse(eval(patched));
  const hitsAnchor = ranges.some(([f, t]) => anchorPositions.some(a => f <= a && a < t));
  check('D boundary edit spares an inline anchor',
    ranges.length > 0 && !hitsAnchor,
    `ranges=${JSON.stringify(ranges)} anchors@${JSON.stringify(anchorPositions)}`);
}

process.exit(failures ? 1 : 0);
