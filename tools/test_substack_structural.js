#!/usr/bin/env node
/*
 * test_substack_structural.js — run the STRUCTURAL engine (substack_repatch.py --structural)
 * against a stubbed ProseMirror doc, so its guards can be exercised without staging edits on
 * a live public essay.
 *
 *   python3 tools/substack_repatch.py --structural <piece-dir> /tmp/s.js
 *   node tools/test_substack_structural.js /tmp/s.js
 *
 * The stub is richer than test_substack_repatch.js needs to be, because this engine moves
 * whole blocks: nodes carry text runs with marks and inline footnote anchors; deletions,
 * text insertions and insertContentAt (a tiny HTML parser for <p>/<em>/<strong>/<a>) mutate a
 * real document model; positions are recomputed the way ProseMirror numbers them; DOMParser
 * and crypto.subtle are the stubs a browser would not need.
 *
 * It builds the "live" doc from the snippet's own target (with Substack's curled quotes), then
 * perturbs it:
 *
 *   S1 identical                    -> ok, nothing dispatched
 *   S2 live has an extra paragraph  -> deleted, ok
 *   S3 live lacks a paragraph       -> inserted on the right side of any divider, ok
 *   S4 live split one block in two  -> replaced 2 -> 1, ok
 *   S5 anchor block text changed    -> a text hunk; the anchor survives; ok
 *   S6 live has a retired footnote  -> its anchor dropped and the orphan removed; ok
 *   S7 draft adds a footnote        -> REFUSED before anything is dispatched
 *   S8 a baked hash was altered     -> REFUSED (transcription guard), nothing dispatched
 *   S9 a linked block changed       -> replaced whole; the link mark is back; ok
 *
 * Cases that need a footnote, an anchor or a link the piece does not have are SKIPPED and say
 * so — a green tick for a check that could not run is the kind of coverage that lies.
 */
const fs = require('fs');
const snippetPath = process.argv[2];
if (!snippetPath) { console.error('usage: node test_substack_structural.js <structural-snippet.js>'); process.exit(2); }
const src = fs.readFileSync(snippetPath, 'utf8');
const TARGET = JSON.parse(src.match(/\/\*T\*\/([\s\S]*?)\/\*T\*\//)[1]);

// approximate Substack's smart-quote input rules
const curl = s => s.replace(/(^|[\s(\[{—–-])"/g, '$1“').replace(/"/g, '”')
                   .replace(/(^|[\s(\[{—–-])'/g, '$1‘').replace(/'/g, '’');
const decode = s => s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"');

// ---------------------------------------------------------------- tiny HTML -> kids
// kids: { isText, text, marks:[{name, attrs}] } | { anchor: true, name }
function parseInline(html) {
  const kids = [], stack = [];
  const re = /(<\/?[a-zA-Z][a-zA-Z0-9]*[^>]*>)|(\[\[FN(\w+)\]\])|([^<\[]+|\[)/g;
  let m;
  while ((m = re.exec(html))) {
    if (m[1]) {
      const tag = m[1], close = tag.startsWith('</');
      const name = tag.match(/^<\/?([a-zA-Z][a-zA-Z0-9]*)/)[1].toLowerCase();
      if (close) { const i = stack.map(s => s.tag).lastIndexOf(name); if (i >= 0) stack.splice(i, 1); }
      else if (!tag.endsWith('/>')) {
        const href = (tag.match(/href="([^"]*)"/) || [])[1];
        if (name === 'em' || name === 'i') stack.push({ tag: name, name: 'italic' });
        else if (name === 'strong' || name === 'b') stack.push({ tag: name, name: 'bold' });
        else if (name === 'a') stack.push({ tag: name, name: 'link', attrs: { href } });
        else stack.push({ tag: name });
      }
    } else if (m[2]) kids.push({ anchor: true, name: m[3] });
    else {
      const text = decode(m[4]);
      if (text) kids.push({ isText: true, text, marks: stack.filter(s => s.name).map(s => ({ name: s.name, attrs: s.attrs || {} })) });
    }
  }
  return kids;
}
function parseTops(html) {
  const tops = []; const re = /<(p|h1|h2|h3|h4|blockquote|ul|ol|pre)\b[^>]*>([\s\S]*?)<\/\1>/g; let m;
  while ((m = re.exec(html))) tops.push({ name: m[1] === 'p' ? 'paragraph' : m[1], kids: parseInline(m[2]) });
  return tops;
}
const topText = t => t.kids.filter(k => !k.anchor).map(k => k.text).join('');

// ---------------------------------------------------------------- the document model
function makeEditor(tops) {
  const kidSize = k => k.anchor ? 1 : k.text.length;
  const sizeOf = t => t.kids.reduce((n, k) => n + kidSize(k), 0) + 2;
  const mark = m => ({ type: { name: m.name }, attrs: m.attrs || {},
                       eq(o) { return o.type.name === m.name && JSON.stringify(o.attrs || {}) === JSON.stringify(m.attrs || {}); } });
  const kidNode = k => k.anchor
    ? { type: { name: 'footnoteAnchor' }, isText: false, isInline: true, nodeSize: 1, marks: [] }
    : { type: { name: 'text' }, isText: true, isInline: true, text: k.text, nodeSize: k.text.length, marks: k.marks.map(mark) };
  const wrap = t => ({
    type: { name: t.name }, isText: false, isInline: false,
    get textContent() { return topText(t); },
    get nodeSize() { return sizeOf(t); },
    descendants(cb) { let rel = 0; for (const k of t.kids) { cb(kidNode(k), rel); rel += kidSize(k); } },
  });
  const layout = () => { let pos = 0; return tops.map(t => { const r = { t, pos, size: sizeOf(t) }; pos += r.size; return r; }); };
  // explode a top into per-character tokens so deletions and insertions are trivial and exact
  const explode = t => { const a = []; for (const k of t.kids) { if (k.anchor) a.push({ anchor: true, name: k.name }); else for (const ch of k.text) a.push({ ch, marks: k.marks }); } return a; };
  const implode = (t, a) => { const kids = []; for (const x of a) { if (x.anchor) { kids.push({ anchor: true, name: x.name }); continue; } const last = kids[kids.length - 1]; if (last && !last.anchor && JSON.stringify(last.marks) === JSON.stringify(x.marks)) last.text += x.ch; else kids.push({ isText: true, text: x.ch, marks: x.marks }); } t.kids = kids; };
  const findTop = pos => layout().find(r => pos >= r.pos + 1 && pos <= r.pos + r.size - 1);
  let dispatches = 0;
  const del = (from, to) => {
    const L = layout();
    const covered = L.filter(r => from <= r.pos && r.pos + r.size <= to);
    if (covered.length) { for (const r of covered) tops.splice(tops.indexOf(r.t), 1); return; }
    const r = findTop(from); if (!r || to > r.pos + r.size - 1) throw new Error('stub: delete crosses a node boundary ' + from + '-' + to);
    const a = explode(r.t); a.splice(from - (r.pos + 1), to - from); implode(r.t, a);
  };
  const insertText = (pos, text, marks) => {
    const r = findTop(pos); if (!r) throw new Error('stub: insert outside a node ' + pos);
    const a = explode(r.t); a.splice(pos - (r.pos + 1), 0, ...[...text].map(ch => ({ ch, marks: marks.map(m => ({ name: m.type.name, attrs: m.attrs })) }))); implode(r.t, a);
  };
  const mkTr = () => { const ops = []; const tr = {
    delete(f, t) { ops.push(() => del(f, t)); return tr; },
    replaceWith(f, t, textNode) { ops.push(() => { del(f, t); insertText(f, textNode.text, textNode.marks || []); }); return tr; },
    _ops: ops }; return tr; };
  const docNode = () => {
    const L = layout();
    return {
      forEach(cb) { for (const r of L) cb(wrap(r.t), r.pos); },
      get firstChild() { return tops.length ? wrap(tops[0]) : null; },
      get content() { return { size: L.length ? L[L.length - 1].pos + L[L.length - 1].size : 0 }; },
      descendants(cb) { for (const r of L) { const w = wrap(r.t); cb(w, r.pos); w.descendants((c, rel) => cb(c, r.pos + 1 + rel)); } },
      resolve(pos) { return { marks() { const r = findTop(pos); if (!r) return []; let rel = 0; for (const k of r.t.kids) { const s = r.pos + 1 + rel, e = s + kidSize(k); if (pos >= s && pos < e) return k.anchor ? [] : k.marks.map(mark); rel += kidSize(k); } const last = r.t.kids[r.t.kids.length - 1]; return last && !last.anchor && pos === r.pos + r.size - 1 ? last.marks.map(mark) : []; } }; },
      textBetween(from, to) { let out = ''; for (const r of L) { let rel = 0; for (const k of r.t.kids) { const s = r.pos + 1 + rel; if (!k.anchor) for (let i = 0; i < k.text.length; i++) { const p = s + i; if (p >= from && p < to) out += k.text[i]; } rel += kidSize(k); } } return out; },
      nodesBetween(from, to, cb) { for (const r of L) { let rel = 0; for (const k of r.t.kids) { const s = r.pos + 1 + rel, e = s + kidSize(k); if (e > from && s < to) cb(kidNode(k), s); rel += kidSize(k); } } },
    };
  };
  const editor = {
    get state() { return { doc: docNode(), tr: mkTr(), schema: { text: (text, marks) => ({ text, marks }) } }; },
    view: { dispatch(tr) { dispatches++; for (const f of tr._ops) f(); } },
    commands: { insertContentAt(range, html) {
      dispatches++;
      const { from, to } = range; const L = layout();
      const newTops = parseTops(html);
      if (from === to) {
        const idx = L.findIndex(r => r.pos === from); const at = idx >= 0 ? idx : (from >= (L.length ? L[L.length - 1].pos + L[L.length - 1].size : 0) ? tops.length : -1);
        if (at < 0) throw new Error('stub: insert position is not a node boundary ' + from);
        tops.splice(at, 0, ...newTops); return true;
      }
      const first = L.findIndex(r => r.pos === from), last = L.findIndex(r => r.pos + r.size === to);
      if (first < 0 || last < first) throw new Error('stub: replace range is not node-aligned ' + from + '-' + to);
      tops.splice(first, last - first + 1, ...newTops); return true;
    } },
  };
  return { editor, tops, dispatches: () => dispatches };
}

// ---------------------------------------------------------------- build a live doc from the target
// anchors are placed where the draft's [[FN]] markers sit; text is curled the way Substack does
function liveFromTarget(t, opts = {}) {
  const tops = [{ name: 'youtube2', kids: [] }];
  (opts.body || t.body).forEach(b => {
    if (b.hrBefore) tops.push({ name: 'horizontalRule', kids: [] });
    const parsed = parseTops(b.html);
    const top = parsed.length === 1 ? parsed[0] : { name: 'paragraph', kids: parseInline(b.html) };
    top.kids = top.kids.map(k => k.anchor ? k : { ...k, text: curl(k.text) });
    tops.push(top);
  });
  (opts.fns || t.fns).forEach(f => tops.push({ name: 'footnote', kids: [{ isText: true, text: curl(f.text), marks: [] }] }));
  return tops;
}

async function run(tops, source, fields) {
  const { editor, dispatches } = makeEditor(tops);
  const f = fields || { 'textarea[placeholder="Title"]': { value: TARGET.title }, 'textarea[placeholder="Add a subtitle…"]': { value: TARGET.subtitle } };
  global.document = { querySelector: sel => (sel === '.ProseMirror' ? { editor } : (f[sel] || null)) };
  global.DOMParser = class { parseFromString(html) { return { body: { children: parseTops(html).map(tp => ({ textContent: topText(tp) })) } }; } };
  if (!global.crypto || !global.crypto.subtle) global.crypto = require('crypto').webcrypto;
  const report = JSON.parse(await eval(source || src));
  return { report, dispatches: dispatches(), tops };
}

let failures = 0;
const check = (name, ok, detail) => { console.log(`${ok ? 'ok  ' : 'FAIL'}  ${name}${detail ? '   ' + detail : ''}`); if (!ok) failures++; };
const skip = (name, why) => console.log(`skip  ${name}   (${why})`);
const summary = r => `ok=${r.report.ok} refused=${r.report.refused} applied=${JSON.stringify(r.report.applied)} failed=${JSON.stringify(r.report.failed)} final=${JSON.stringify(r.report.final)} dispatches=${r.dispatches}`;
const bodyOf = tops => tops.filter(t => !['footnote', 'horizontalRule', 'youtube2'].includes(t.name)).map(topText);
// the engine's own comparison domain: straight quotes, collapsed whitespace
const norm = s => s.replace(/[\u2018\u2019]/g, "'").replace(/[\u201c\u201d]/g, '"').replace(/\s+/g, ' ').trim();
const anchorsIn = tops => tops.reduce((n, t) => n + t.kids.filter(k => k.anchor).length, 0);
const wantAnchors = TARGET.body.reduce((n, b) => n + b.anchors.length, 0);
const plainIdx = (pred = () => true) => TARGET.body.findIndex((b, i) => !b.anchors.length && !/<a /.test(b.html) && b.text.length > 40 && pred(b, i));

(async () => {
  // --- S1 identical -> ok, nothing dispatched ---
  { const r = await run(liveFromTarget(TARGET));
    check('S1 identical doc is a no-op', r.report.ok && r.report.applied.length === 0 && r.dispatches === 0, summary(r)); }

  // --- S2 live has an extra paragraph -> deleted ---
  { const body = TARGET.body.slice(); body.splice(1, 0, { text: 'An extra paragraph nobody wrote.', html: '<p>An extra paragraph nobody wrote.</p>', anchors: [], hrBefore: false });
    const r = await run(liveFromTarget(TARGET, { body }));
    check('S2 extra live paragraph is deleted', r.report.ok && r.report.applied.some(a => a.kind === 'delete') && JSON.stringify(bodyOf(r.tops).map(norm)) === JSON.stringify(TARGET.body.map(b => norm(b.text))), summary(r)); }

  // --- S3 live lacks a paragraph -> inserted (on the draft's side of a divider) ---
  { const k = plainIdx((b, i) => i > 0);
    if (k < 0) skip('S3 missing paragraph is inserted', 'no plain block to remove');
    else { const body = TARGET.body.slice(); body.splice(k, 1);
      const r = await run(liveFromTarget(TARGET, { body }));
      const hrs = r.tops.map(t => t.name === 'horizontalRule' ? '-' : (['footnote', 'youtube2'].includes(t.name) ? '' : 'p')).join('');
      const want = TARGET.body.map(b => (b.hrBefore ? '-' : '') + 'p').join('');
      check('S3 missing paragraph is inserted', r.report.ok && r.report.applied.some(a => a.kind === 'insert') && hrs === want, summary(r) + ` layout=${hrs}`); } }

  // --- S4 live split one block into two -> replaced 2 -> 1 ---
  { const k = plainIdx();
    if (k < 0) skip('S4 split block is re-merged', 'no plain block to split');
    else { const body = TARGET.body.slice(); const t = TARGET.body[k].text; const cut = t.indexOf(' ', 20);
      body.splice(k, 1, { text: t.slice(0, cut), html: '<p>' + t.slice(0, cut) + '</p>', anchors: [], hrBefore: TARGET.body[k].hrBefore }, { text: t.slice(cut + 1), html: '<p>' + t.slice(cut + 1) + '</p>', anchors: [], hrBefore: false });
      const r = await run(liveFromTarget(TARGET, { body }));
      check('S4 split block is re-merged', r.report.ok && r.report.applied.some(a => a.kind === 'replace' && a.blocks === 1), summary(r)); } }

  // --- S5 an anchor-bearing block changed -> hunk; the anchor survives ---
  { const k = TARGET.body.findIndex(b => b.anchors.length && b.text.length > 30);
    if (k < 0) skip('S5 anchor block goes by hunk', 'piece has no footnote anchors');
    else { const tops = liveFromTarget(TARGET); const bodyTops = tops.filter(t => !['footnote', 'horizontalRule', 'youtube2'].includes(t.name));
      const top = bodyTops[k]; const first = top.kids.find(x => !x.anchor && x.text.length > 8); first.text = first.text.slice(0, 4) + 'ZQX ' + first.text.slice(4);
      const r = await run(tops);
      check('S5 anchor block goes by hunk and keeps its anchor', r.report.ok && r.report.applied.some(a => a.kind === 'hunk') && anchorsIn(r.tops) === wantAnchors, summary(r)); } }

  // --- S6 live has a retired footnote -> anchor dropped, orphan removed ---
  { const k = plainIdx();
    if (k < 0) skip('S6 retired footnote is dropped', 'no plain block to hang an anchor on');
    else { const tops = liveFromTarget(TARGET); const bodyTops = tops.filter(t => !['footnote', 'horizontalRule', 'youtube2'].includes(t.name));
      // an extra anchor at the end of a plain block, numbered after every existing anchor before it
      let before = 0; for (let i = 0; i < k; i++) before += bodyTops[i].kids.filter(x => x.anchor).length;
      bodyTops[k].kids.push({ anchor: true, name: 'retired' });
      const fnIdx = tops.findIndex(t => t.name === 'footnote'); const at = (fnIdx < 0 ? tops.length : fnIdx) + before;
      tops.splice(at, 0, { name: 'footnote', kids: [{ isText: true, text: 'A footnote the draft has retired.', marks: [] }] });
      const r = await run(tops);
      const fnCount = r.tops.filter(t => t.name === 'footnote').length;
      check('S6 retired footnote: anchor dropped and orphan removed', r.report.ok && r.report.applied.some(a => a.kind === 'dropAnchor') && anchorsIn(r.tops) === wantAnchors && fnCount === TARGET.fns.length, summary(r) + ` fns=${fnCount}`); } }

  // --- S7 the draft adds a footnote -> refused, nothing dispatched ---
  { const k = TARGET.body.findIndex(b => b.anchors.length);
    if (k < 0) skip('S7 added footnote is refused', 'piece has no footnotes');
    else { const tops = liveFromTarget(TARGET); const bodyTops = tops.filter(t => !['footnote', 'horizontalRule', 'youtube2'].includes(t.name));
      const name = TARGET.body[k].anchors[0]; const fnPos = TARGET.fns.findIndex(f => f.name === name);
      bodyTops[k].kids = bodyTops[k].kids.filter(x => !(x.anchor && x.name === name));
      const fnTops = tops.filter(t => t.name === 'footnote'); tops.splice(tops.indexOf(fnTops[fnPos]), 1);
      const r = await run(tops);
      check('S7 added footnote is refused before any edit', !!r.report.refused && /adds footnote|cannot tell which to keep/.test(r.report.refused) && r.dispatches === 0, summary(r)); } }

  // --- S8 a baked hash was altered -> transcription refusal, nothing dispatched ---
  { const k = plainIdx();
    if (k < 0) skip('S8 transcription guard', 'no plain block');
    else { const tampered = src.replace(TARGET.body[k].hash, 'deadbeefdeadbeef');
      const r = await run(liveFromTarget(TARGET), tampered);
      check('S8 altered hash is refused before any edit', !!r.report.refused && /transcription/.test(r.report.refused) && r.dispatches === 0, summary(r)); } }

  // --- S9 a linked block changed -> replaced whole; the link mark is back ---
  { const k = TARGET.body.findIndex(b => !b.anchors.length && /<a /.test(b.html));
    if (k < 0) skip('S9 linked block keeps its link', 'piece has no link in an anchor-free block');
    else { const tops = liveFromTarget(TARGET); const bodyTops = tops.filter(t => !['footnote', 'horizontalRule', 'youtube2'].includes(t.name));
      bodyTops[k].kids.unshift({ isText: true, text: 'ZQX ', marks: [] });
      const r = await run(tops);
      const hasLink = r.tops.filter(t => !['footnote', 'horizontalRule', 'youtube2'].includes(t.name))[k].kids.some(x => !x.anchor && x.marks.some(m => m.name === 'link'));
      check('S9 linked block is replaced and keeps its link', r.report.ok && r.report.final.linksMissing.length === 0 && hasLink, summary(r)); } }

  process.exit(failures ? 1 : 0);
})().catch(e => { console.log('FAIL  runner crashed   ' + (e.stack || e)); process.exit(1); });
