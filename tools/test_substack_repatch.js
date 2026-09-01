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

process.exit(failures ? 1 : 0);
