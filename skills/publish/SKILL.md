---
name: publish
description: Compose a finished piece as a Substack DRAFT in one pass — verify the footnotes, strip internal notes, then set title, subtitle, formatted body, images, and native footnotes — by driving the browser. Use when the user says "publish X to Substack", "load X into Substack", "put X on Substack", or wants a ready-to-review draft. For a piece already live, it re-syncs the published post SURGICALLY — staging only what actually changed (a fixed word, a casing sweep, a reworded clause) and touching nothing else. Produces a DRAFT / staged edit only; the human reviews and clicks Publish/Update. Never auto-publishes or sends email.
---

# Publish (to Substack)

Turn a finished piece into a faithful, ready-to-review Substack **draft** in one pass.
Automation composes the draft; a human reviews and clicks Publish. This replaces the slow,
glitchy char-by-char editor typing with one paste + one footnote pass.

## Preconditions

- The piece is finished (`pieces/<name>/draft.md`) and has a **manifest**
  `pieces/<name>/publish.yaml` — `title`, `subtitle`, `footnotes` (native|endnotes|none),
  `send_email` (default false), optional `cover`, optional **`post_url`** (record it once the
  piece is live; its presence switches this skill into **republish mode** — see below), and
  optional **`public_url`**.
- **`post_url` and `public_url` are different URLs and both are needed.** `post_url` is the
  **editor** address (`/publish/post/<id>`) that republish drives. `public_url` is the
  **canonical reader** address (`/p/<slug>`) — the only one that may appear in another essay's
  body under the in-text cross-link convention. Record both when a piece goes live: a piece that
  carried only the editor URL left a sibling essay with no correct link to reach for. Take the
  slug from the publication's archive rather than guessing it from the title.
- **Which mode:** no `post_url` → **fresh compose** (the default flow below), browser open on a
  **fresh empty** composer (`https://<pub>.substack.com/publish/post?type=newsletter`).
  `post_url` present → **republish** (surgical re-sync), browser open on that **live post's
  editor** (`https://<pub>.substack.com/publish/post/<id>`). Either way the user is **logged
  in** — automation cannot enter credentials.
- Publication specifics and defaults live in the **instance** (e.g. `publishing/substack.md`),
  never in this framework skill.

## Preflight — critique gate, verify & strip editorial notes (DO THIS FIRST)

A published draft must be **critiqued**, carry **verified** claims, and carry **zero** internal
notes. The converter enforces the last; you enforce the first two.

0a. **Critique gate — a piece is critiqued before it publishes.** Publishing is the end of the
   quality loop, not a shortcut around it. Before composing a **fresh** draft (or a
   **substantive** republish — a reworded passage, a new or changed section), confirm the piece's
   `log/` records a `critique` (or `style-audit`) pass covering the **current** draft. If none —
   or if the draft has changed materially since the last recorded pass — run `critique` first and
   fold its accepted fixes into `draft.md` before continuing. Skip only on the user's **explicit**
   say-so, and note the skip in the log. (A trivial re-sync — a casing sweep, a one-word fix, a
   fixed typo — is exactly what republish mode is for and does **not** need a fresh critique.)

0b-links. **Status-check the in-body cross-links:**
   `python3 framework/tools/check_links.py pieces/<name>` — exits non-zero and names any link
   that does not resolve. A cross-link URL copied out of the scaffold is **unverified by
   default**; a dead sibling slug once sat in a piece's README and DASHBOARD as its canonical
   address from the day it published, because that URL had only ever been copied and never
   followed. Fix a dead link here **and** in every scaffold file that repeats it.

0b. **Verify the footnotes.** Every footnote that quotes or characterizes a real person,
   cites a work, or pins a scriptural/textual locus must be fact-checked before composing —
   misquoting a real person in a public post is the failure to prevent. If the piece's
   anchor ledger (`README.md` / `notes.md`) isn't already closed, run a verification pass
   now (a fact-check sub-agent over the footnote claims is the fast path) and fold the
   corrections into `draft.md`. Quote only what's confirmed.

0c. **Move editorial notes out of the reader's way.** Internal "Verify X", "attribute
   carefully", "todo" notes must not publish. The convention (auto-stripped by the
   converter): put them **after a dagger `†`** inside the footnote, or inside an HTML
   comment `<!-- … -->`. Both are dropped at convert time.

   **The converter enforces this two ways, and the second is the one that matters.** It refuses
   if a footnote still contains "verify" *after* cleaning (a note someone forgot to put behind a
   dagger), **and it refuses if a `†` note it stripped reads like an unverified-claim marker** —
   `verify/todo/tk/check/confirm/pin/source/cite` — naming each one. That second guard was added
   2026-08-29 after the first was found to be structurally inert: the convention is to put verify
   notes behind a `†`, which strips them *before* the first guard looks, so a well-formed note
   always passed. **A draft carrying 17 unverified anchors converted clean and exited 0.** Four
   of those anchors were later found to be factually wrong, three of them misquotations of named
   translators.

   **A `†` marker means the claim is unverified.** Clear it by verifying the claim, not by
   deleting the marker, and never reach for `--allow-verify` / `--allow-unverified` to silence a
   real one.

## Steps

1. **Convert:** `python3 framework/tools/md_to_substack.py pieces/<name> <out.js>`
   Reads `draft.md` + `publish.yaml`, writes a self-contained JS snippet, and prints
   paragraph/heading/divider/image/footnote counts **plus `editorial-notes-stripped~N`** —
   sanity-check them against the piece. A non-zero exit + WARNING means an unresolved
   verify-note remains (see Preflight 0b); fix it, don't override.
2. **Focus** the composer body (click into it).
3. **Call A — body:** run the whole snippet via the browser's JS eval. It sets Title +
   Subtitle and pastes the entire formatted body in one synthetic ProseMirror paste
   (paragraphs, headings, blockquotes, dividers, lists, bold/italic/links, images inlined as
   `data:` URIs → Substack uploads them to its CDN). Footnote refs remain as `[[FNn]]` markers.
4. **Call B — footnotes:** run `window.__sbInsertFootnotes()`. It turns every `[[FNn]]`
   marker into a **native** Substack footnote (the editor's own Tiptap `insertFootnote`
   command) and fills each note's rich content. It returns `{inserted, missing}` — **`missing`
   must be empty.**
5. **Post-check (JS):** title/subtitle set · paragraph count matches · **0 empty paragraphs**
   · heading/divider/image counts · footnote anchors == blocks == manifest count · **0
   `[[FN` markers left**. Report the numbers; don't say "done" without them.
6. **Hand off:** the draft is composed. Tell the user to review it in Substack and click
   **Publish** (and send an email if they want) themselves. **Do not click Publish / Continue
   / Send.**

## Republish — surgically re-sync a live post

When a piece is **already published** and `draft.md` has since changed (a fixed quote, a
pronoun-casing sweep, a reworded clause), don't recompose it from scratch — that would
re-upload every image and wipe any Substack-side state. Instead stage a **minimal** edit that
touches only what changed. This is the tool for **touch-ups**; a structural rewrite (blocks or
footnotes added / removed / reordered) is out of scope and the tool **refuses** it (see below).

Preconditions: `publish.yaml` has a **`post_url`**, and the browser is open and logged in on
that post's **editor** at `https://<pub>.substack.com/publish/post/<id>`. (Find the id from the
post's dashboard row / the README; record `post_url` in the manifest the first time.)

1. **Preflight is identical** — verify the footnotes (0b) and keep internal notes behind `†` /
   in comments (0c). The repatch tool runs the same converter, so it **refuses on a stray
   "verify"** exactly as a fresh publish does. The **critique gate (0a)** applies to a
   *substantive* re-sync (a reworded passage); a trivial touch-up (casing, a typo) is exempt.
2. **Generate the patch:** `python3 framework/tools/substack_repatch.py pieces/<name> <out.js>`
   It renders the current draft's **reader-text** (body blocks + native footnotes, the same
   domain the live editor holds) and bakes it into a self-contained snippet. No baseline file:
   it diffs against the **live post itself**, scraped at run time, so it is stateless and
   self-correcting.
3. **Run the snippet once** in the live editor's JS eval. It: sets title/subtitle iff changed;
   scrapes the live doc; **aligns** non-empty body top-nodes 1:1 and footnote nodes 1:1;
   **refuses** (returns `structural:true`, applies nothing) if the counts differ; else replaces
   only the changed run inside each changed node, **preserving surrounding text and marks**
   (bold/italic/links) across the edit.
4. **Read the report** it returns: `{stagedEdits, unchanged, applied[], footnoteChanges[],
   reviewMarks[], failed[], structural}`. **`failed` must be empty**; `structural:true` means
   stop and either recompose or edit by hand; `reviewMarks` flags any hunk that crossed a
   formatting boundary or was a large fallback — eyeball those in the editor.
5. **Hand off:** staging the edits lights up **Continue**. Tell the user to review the diff and
   click **Continue → Publish** (choosing **not** to resend email) themselves. **Do not click
   Continue / Publish / Send.**

## How it works (re-probe here if Substack changes)

- Substack's editor is **Tiptap** over ProseMirror, reachable at
  `document.querySelector('.ProseMirror').editor` (`editor.commands`, `editor.chain()`).
- **Body:** dispatch a synthetic `paste` `ClipboardEvent` carrying `text/html` on
  `.ProseMirror`; Tiptap's paste converter builds the blocks. (Instant; avoids char-by-char
  typing. ⌘V and keyboard modifiers are unreliable in the browser tool, so we dispatch the
  event directly.)
- The paste is applied **asynchronously**, so the footnote pass MUST be a separate call
  (B) after the body is in the doc model.
- **Images:** an `<img>` with a `data:` URI is uploaded to Substack's CDN on paste.
- **Footnotes:** paste cannot create native footnotes; `insertFootnote` (option 2) does —
  select the marker, delete it, insert the footnote, `insertContent(html)` fills it. Re-scan
  the doc for each marker so shifting positions don't matter; Substack renumbers by position.
- **Title/subtitle** are React-controlled `<textarea>`s — set via the native value setter
  plus an `input` event.
- **Republish (surgical):** the live post's editor is the same Tiptap/ProseMirror doc, opened
  at `/publish/post/<id>`. Its top nodes are `heading`/`paragraph`/`hr` (body) and `footnote`
  (native footnotes, at the tail, in order) — so body and footnotes separate cleanly and align
  1:1 with the converter's output. The patch diffs **reader-text** (tags/`[[FN]]` markers
  stripped, entities unescaped) so the diff domain equals the editor's text. Each changed run
  is replaced in place with `tr.replaceWith(from, to, schema.text(new, marks))`, carrying the
  marks resolved at the edit — casing flips inside an `<em>` keep the italic. Edits apply
  **latest-position-first** (node then offset, descending) so unapplied positions stay valid.
  Char-offset→doc-position uses `node.descendants` (correct whether a node is a bare textblock
  or wraps a paragraph). **`Continue` stays disabled until a real edit lands** — a good check
  that a no-op re-sync changed nothing.

## Guardrails

- **Draft-only.** Never click Publish/Continue/Send — the human publishes. (Safety rule +
  editorial correctness.) **This holds doubly for republish:** it stages edits on a **live,
  public** post; the skill only stages, the human clicks **Continue → Publish** and chooses
  **not to resend email**.
- **Republish is surgical, and touch-ups only.** It changes the smallest span that differs and
  nothing else. If the diff is structural — a block or footnote added, removed, or reordered —
  the tool **refuses** (`structural:true`, zero edits); recompose the piece or edit by hand
  instead of nuking-and-repaving a live essay. Never pass a flag to force past a refusal.
- **Framework stays generic.** No publication specifics, no secrets, no personal writing here.
- **Verified + clean before it ships.** Preflight is not optional: footnote claims are
  fact-checked, and internal notes are stripped (the converter refuses output otherwise).
  Misquoting a real person or leaking a "Verify X" note into a public draft is the failure
  this step exists to prevent.
- **Verify before hand-off.** Always run the post-check; a paste that silently half-lands is
  the failure mode to catch (paragraph/footnote/marker counts).
- **Footnotes are coupled to Substack internals** (`.editor`, `insertFootnote`). If Substack
  changes them, call B's `missing` list or the leftover-marker count will surface it — fall
  back to endnotes (a trailing `<hr>` + numbered list) and flag for a re-probe.
