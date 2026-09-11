#!/usr/bin/env node
/*
 * test_substack_scan.js — run substack_sync's SCAN_JS against a stubbed ProseMirror doc and
 * print the JSON it would return from a live post.
 *
 *   python3 tools/substack_sync.py scan <piece-dir> /tmp/scan.js
 *   python3 tools/substack_repatch.py --structural <piece-dir> /tmp/target.js
 *   node tools/test_substack_scan.js /tmp/scan.js /tmp/target.js
 *
 * It exists for ONE assertion, and it is the assertion the whole sync baseline rests on:
 * the mark signature computed in the browser must equal the one computed in Python, byte
 * for byte. They are the same string derived on the two sides of a wire, and a hash of two
 * strings that can disagree is not a baseline, it is a coin flip. test_suite.py runs this
 * and compares the digests against HM() on the draft side.
 *
 * The live document is built from the structural target — the converter's own HTML, marks
 * and all, with Substack's curled quotes — so the two sides are genuinely independent
 * computations over the same piece rather than one echoed back.
 */
const fs = require('fs');
const { curl, parseTops, parseInline, topFromRuns, makeEditor, install, guardHandle, guardHosts } = require('./test_editor_stub.js');

const [scanPath, targetPath] = process.argv.slice(2);
if (!scanPath || !targetPath) {
  console.error('usage: node test_substack_scan.js <scan.js> <structural-target.js>');
  process.exit(2);
}
const scanSrc = fs.readFileSync(scanPath, 'utf8');
const TARGET = JSON.parse(fs.readFileSync(targetPath, 'utf8').match(/\/\*T\*\/([\s\S]*?)\/\*T\*\//)[1]);

const tops = [];
for (const b of TARGET.body) {
  if (b.hrBefore) tops.push({ name: 'horizontalRule', kids: [] });
  const parsed = parseTops(b.html);
  const top = parsed.length === 1 ? parsed[0] : { name: 'paragraph', kids: parseInline(b.html) };
  top.kids = top.kids.map(k => (k.anchor ? k : { ...k, text: curl(k.text) }));
  tops.push(top);
}
for (const f of TARGET.fns) {
  const top = topFromRuns('footnote', f.text, f.marks);
  top.kids = top.kids.map(k => ({ ...k, text: curl(k.text) }));
  tops.push(top);
}

(async () => {
  const { editor } = makeEditor(tops);
  install(editor, {
    'textarea[placeholder="Title"]': { value: TARGET.title },
    'textarea[placeholder="Add a subtitle…"]': { value: TARGET.subtitle },
  }, { handle: guardHandle(scanSrc), host: guardHosts(scanSrc)[0] || null });
  // The shipped snippet is one promise-valued expression (substack_account.wrap: the account
  // guard, then the scan), so it is evaluated as-is and its promise awaited.
  console.log(await eval(scanSrc));
})().catch(e => { console.error('runner crashed: ' + (e.stack || e)); process.exit(1); });
