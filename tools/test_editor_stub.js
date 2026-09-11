/*
 * test_editor_stub.js — the stubbed ProseMirror document both engine suites run against.
 *
 * Shared by test_substack_repatch.js (the surgical engine) and test_substack_structural.js
 * (the structural one), so the two can never be exercised against two different ideas of
 * what a document is. It models what the engines actually touch:
 *
 *   - top nodes with text runs that carry MARKS (em / strong / link) and inline footnote
 *     anchors, positioned the way ProseMirror numbers them;
 *   - deletions, text insertions, insertContentAt (a tiny HTML parser for <p>/<em>/<strong>/<a>),
 *     and addMark / removeMark, all mutating a real document model;
 *   - DOMParser and crypto.subtle, which a browser would not need stubbing.
 *
 * Marks are modelled because a formatting-only edit is invisible to reader-text and was
 * therefore invisible to every check on this desk (measured on `rising-after-falls`,
 * 2026-09-09). A stub with no marks cannot fail the test that catches that, which makes it
 * exactly as blind as the thing it is meant to be testing.
 */

// approximate Substack's smart-quote input rules
const curl = s => s.replace(/(^|[\s(\[{—–-])"/g, '$1“').replace(/"/g, '”')
                   .replace(/(^|[\s(\[{—–-])'/g, '$1‘').replace(/'/g, '’');
const decode = s => s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"');

// ---------------------------------------------------------------- tiny HTML -> kids
// kids: { isText, text, marks:[{name, attrs}] } | { anchor: true, name }
// Mark names are the ones Substack's own schema uses (`em`, `strong`, `link`) — measured
// 2026-09-09, when a mark was applied by hand through `schema.marks.em.create()`.
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
        if (name === 'em' || name === 'i') stack.push({ tag: name, name: 'em' });
        else if (name === 'strong' || name === 'b') stack.push({ tag: name, name: 'strong' });
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

// Build one top node from reader-text plus the marked runs the snippet baked in
// ({start,end,kind,text,href} offsets into that text). This is how a "live" document is
// built for the surgical suite: from the target's own marks, so an untouched document is
// a genuine no-op rather than a document that merely has no formatting at all.
function topFromRuns(name, text, runs) {
  const kids = [];
  for (let i = 0; i < text.length; ) {
    const here = (runs || []).filter(r => i >= r.start && i < r.end);
    let next = text.length;
    for (const r of (runs || [])) { if (r.start > i && r.start < next) next = r.start; if (r.end > i && r.end < next) next = r.end; }
    kids.push({ isText: true, text: text.slice(i, next),
                marks: here.map(r => ({ name: r.kind, attrs: r.kind === 'link' ? { href: r.href } : {} }))
                          .sort((a, b) => (a.name < b.name ? -1 : 1)) });
    i = next;
  }
  return { name, kids: kids.length ? kids : [{ isText: true, text: '', marks: [] }] };
}

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
  // explode a top into per-character tokens so deletions, insertions and mark changes are
  // trivial and exact
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
  const editMark = (from, to, m, on) => {
    const r = findTop(from); if (!r || to > r.pos + r.size - 1) throw new Error('stub: mark crosses a node boundary ' + from + '-' + to);
    const name = m.type ? m.type.name : m.name, attrs = (m.attrs || {});
    const a = explode(r.t);
    for (let p = from; p < to; p++) {
      const x = a[p - (r.pos + 1)];
      if (!x || x.anchor) continue;
      const without = x.marks.filter(q => q.name !== name);
      x.marks = on ? [...without, { name, attrs }].sort((u, v) => (u.name < v.name ? -1 : 1)) : without;
    }
    implode(r.t, a);
  };
  const mkTr = () => { const ops = []; const tr = {
    delete(f, t) { ops.push(() => del(f, t)); return tr; },
    replaceWith(f, t, textNode) { ops.push(() => { del(f, t); insertText(f, textNode.text, textNode.marks || []); }); return tr; },
    addMark(f, t, m) { ops.push(() => editMark(f, t, m, true)); return tr; },
    removeMark(f, t, m) { ops.push(() => editMark(f, t, m, false)); return tr; },
    _ops: ops }; return tr; };
  const markType = name => ({ name, create: attrs => ({ type: { name }, attrs: attrs || {} }) });
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
    get state() { return { doc: docNode(), tr: mkTr(),
      schema: { text: (text, marks) => ({ text, marks }),
                marks: { em: markType('em'), strong: markType('strong'), link: markType('link') } } }; },
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

// install the browser globals an engine snippet expects, and return a runner. Every generated
// snippet opens with an account guard (substack_account.py) that fetches the signed-in profile
// before touching the document: `handle` is who this stub is signed in as (null: signed out),
// and any other fetch is a test bug, so it throws.
function install(editor, fields, { handle = null, host = null } = {}) {
  global.document = { querySelector: sel => (sel === '.ProseMirror' ? { editor } : (fields[sel] || null)) };
  global.DOMParser = class { parseFromString(html) { return { body: { children: parseTops(html).map(tp => ({ textContent: topText(tp) })) } }; } };
  if (!global.crypto || !global.crypto.subtle) global.crypto = require('crypto').webcrypto;
  // The guard checks the publication before the account, so the page has to BE the outlet's host.
  const h = host || 'example.invalid';
  global.location = { origin: 'https://' + h, hostname: h, host: h,
                      href: 'https://' + h + '/publish/post/0', pathname: '/publish/post/0' };
  global.fetch = async path => {
    if (path !== '/api/v1/user/profile/self') throw new Error('stub: no network for ' + path);
    return handle ? { status: 200, json: async () => ({ handle, name: 'stub' }) }
                  : { status: 401, json: async () => ({}) };
  };
}

// The handle a snippet's account guard insists on (substack_account.guard_handle, in JS).
function guardHandle(src) {
  const m = src.match(/desk-account-guard v1 \*\/ \(async \(\) => \{\s*const WANT = ("[^"\\]*")/);
  return m ? JSON.parse(m[1]) : null;
}

// The publication host(s) it insists on — empty when the outlet records none.
function guardHosts(src) {
  const m = src.match(/desk-account-guard v1 \*\/[\s\S]{0,300}?HOSTS = (\[[^\]]*\])/);
  return m ? JSON.parse(m[1]) : [];
}

// The marked runs of a top node, the way the engines define one: coalesced across
// contiguous kids and trimmed at the edges. Kept here rather than in either suite because
// getting it wrong is easy in exactly the way that hides a real failure -- a naive walk
// splits an <em> in two wherever a <strong> is nested inside it, and then reports the
// engine as broken for producing the correct document.
function runsOf(top, { links = false } = {}) {
  const spans = [];
  let acc = 0;
  for (const k of top.kids) {
    if (k.anchor) continue;
    for (const m of k.marks) {
      if (!links && m.name === 'link') continue;
      const key = m.name + ' ' + (m.attrs && m.attrs.href ? m.attrs.href : '');
      const last = spans.find(sp => sp.key === key && sp.end === acc);
      if (last) last.end = acc + k.text.length;
      else spans.push({ key, kind: m.name, href: (m.attrs && m.attrs.href) || '', start: acc, end: acc + k.text.length });
    }
    acc += k.text.length;
  }
  const text = topText(top);
  const out = [];
  for (const sp of spans.sort((a, b) => a.start - b.start || b.end - a.end)) {
    let { start, end } = sp;
    while (start < end && /\s/.test(text[start])) start++;
    while (end > start && /\s/.test(text[end - 1])) end--;
    if (end > start) out.push({ kind: sp.kind, href: sp.href, text: text.slice(start, end) });
  }
  return out;
}

module.exports = { curl, decode, parseInline, parseTops, topText, topFromRuns, runsOf, makeEditor, install, guardHandle, guardHosts };
