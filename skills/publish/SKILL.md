---
name: publish
description: Compose a finished piece as a Substack DRAFT in one pass — verify the footnotes, strip internal notes, then set title, subtitle, formatted body, images, and native footnotes — by driving the browser. Use when the user says "publish X to Substack", "load X into Substack", "put X on Substack", or wants a ready-to-review draft. For a piece already live, it re-syncs the published post SURGICALLY — changing only what actually changed (a fixed word, a casing sweep, a reworded clause) and touching nothing else. A FRESH compose produces a private DRAFT that a human publishes. A RE-SYNC of an already-published post is LIVE the moment it is written — Substack has no staging step there, so verify before writing, not after. Never clicks Publish/Continue/Send, and never sends email.
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
- **Surface: a fresh compose needs REAL Chrome**, because the default body transport is the
  system clipboard and **the in-app browser pane cannot reach the pasteboard** (see Steps). A
  re-sync/republish is pure JS and runs on either surface. If only the pane is available, say so
  and use the fallback path — do not silently switch transports.
- **The Claude in Chrome extension is a framework requirement, not an optional extra** — see
  *Requirements* in the framework README for install and troubleshooting. In short: extension
  **v1.0.36+**, a **direct Anthropic plan**, a session signed in with **`/login`** (an API-key or
  `setup-token` session cannot use the extension at all), and `claude --chrome`. Verify with
  `/chrome` — **Status: Enabled**, **Extension: Installed**. If the user is missing it, **say so
  and stop**; do not quietly fall back to retyping the essay.
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

0b-images. **Images live with the piece, not only on Substack.**
   A piece keeps its pictures in `pieces/<name>/assets/`, referenced from `draft.md` the
   ordinary markdown way — `![alt](assets/hero.png)` — and `publish.yaml` records, under an
   `images:` block, which Substack URL each local file is already uploaded to.

   **Why the URL is recorded:** for a piece that is already live the converter emits
   `<img src="<that URL>">` instead of inlining the bytes, so a recompose **reuses the asset
   already in the post** rather than uploading a duplicate and orphaning the old one. It also
   keeps the snippet small — *For the Love of Dogs* converts to 9.7 KB this way instead of
   ~14 MB. A piece with no recorded URL still inlines, which is what performs the first upload.
   Delete a URL to force a fresh upload from the local file.

   **An image added in the Substack composer exists only on Substack**, and `draft.md` will
   not know about it, so a recompose would silently drop it. Pull it back down with
   `python3 framework/tools/sync_post_images.py pieces/<name> --apply`, which stores every
   image in the post under `assets/` and writes the `images:` block. It prefers **your original
   upload** when it can find one (Substack stores PNGs byte-for-byte, so the md5 match is
   proven rather than guessed), searching `~/Downloads` by default; failing that it keeps
   Substack's copy. Run it dry first — it changes nothing without `--apply`.

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

## Steps — clipboard transport (the default; use this)

> **Never retype the essay.** The older JS-snippet path bakes the whole piece into a string
> literal, so driving it means the agent reproducing every byte of the author's prose into a
> `javascript_exec` call — ~37KB for a 5,700-word essay. **That makes the agent's transcription
> the weakest link in the chain:** one wrong character diffs as a real edit and can publish a
> typo in the author's voice, and no downstream guard can see it, because to a guard a typo is
> just another edit. The clipboard removes the agent from the transport: the bytes go
> **disk → system pasteboard → Chrome → ProseMirror** and are never retyped.

**Surface matters, and this is the part that is easy to get wrong.** Measured 2026-09-01:

| surface | result |
|---|---|
| in-app browser pane + `navigator.clipboard.read()` | ❌ `NotAllowedError: Document is not focused` |
| in-app browser pane + synthetic `cmd+v` | ❌ no-op, editor stays empty |
| **real Chrome + real click + real `cmd+v`** | ✅ **works** — `h2`, `em`, `strong`, links, blockquotes all survive |

So compose in **real Chrome** (`claude-in-chrome`), not the in-app pane. A programmatic
`.focus()` does **not** satisfy the Clipboard API — the click has to be a real one.

1. **Load the clipboard:** `python3 framework/tools/md_to_clipboard.py pieces/<name> --fn-out <fn.js>`
   Runs the same converter and therefore the **same refusals** (a stray "verify", nested
   footnote refs, undefined/duplicated markers) — a different transport is never a lower bar.
   Prints the block counts, the **SHA-256 of the HTML actually placed on the pasteboard**, and
   the title/subtitle from the manifest. It writes the footnote snippet separately, because
   **footnotes cannot travel by clipboard** — a paste cannot create native ones.
2. **Open the composer in real Chrome** and set Title + Subtitle by JS (small, no prose in it),
   then `clearContent(true)` so a retry can't append to a half-paste.
3. **Body:** a **real click** into the body, then a **real `cmd+v`**. Formatting, links and
   dividers arrive intact; footnote refs remain as `[[FNn]]` markers.
4. **Footnotes:** run the `--fn-out` snippet (a few KB — small enough to run directly). It turns
   every `[[FNn]]` marker into a **native** Substack footnote via Tiptap's `insertFootnote` and
   fills each note's rich content. Returns `{inserted, missing}` — **`missing` must be empty.**
5. **Post-check (JS):** title/subtitle set · block counts match · **0 empty paragraphs** ·
   heading/divider/image counts · footnotes == manifest count · **0 `[[FN` markers left** ·
   in-body sibling links present. Report the numbers; don't say "done" without them.
6. **Fidelity check — do this, it is the whole point.** Hash every live block's flattened text,
   digest the list, and compare against the same digest computed from `draft.md` via
   `render_reader`. **The two digests must be identical.** A clipboard paste cannot introduce a
   transcription error, so this is cheap and should pass first time; if it does *not*, something
   else moved (a concurrent edit to the draft, a Substack-side input rule) and that is worth
   knowing before a human publishes.
7. **Hand off:** the draft is composed. Tell the user to review it in Substack and click
   **Publish** themselves. **Do not click Publish / Continue / Send.**

### Fallback — the JS-snippet path

`md_to_substack.py` still exists and still works; use it only where the clipboard cannot be
reached (not macOS, no real-Chrome surface, a headless run). If you fall back, **say so**, and
be aware you are accepting the transcription risk the clipboard exists to remove — verify with
step 6 without exception.

1. **Convert:** `python3 framework/tools/md_to_substack.py pieces/<name> <out.js>`
2. **Focus** the composer body (click into it).
3. **Call A — body:** run the whole snippet via the browser's JS eval (sets Title + Subtitle,
   pastes the body as one synthetic ProseMirror paste; images inlined as `data:` URIs →
   Substack uploads them to its CDN).
4. **Call B — footnotes:** `window.__sbInsertFootnotes()`; `missing` must be empty.
5-7. As above.

## Republish — surgically re-sync a live post

> **⚠️ Republish is not a draft operation. It edits the public page.** Substack applies an
> edit to an already-published post on autosave, so every change this section makes is visible to
> readers immediately — there is no staged revision waiting for a human, and **Continue** is
> normally **disabled** afterwards because nothing is left to publish. The name is a
> misnomer inherited from the fresh-compose flow. Read "republish" as **"edit the live post."**
>
> **Prefer the `substack-sync` skill for any piece that is already live.** What follows
> pushes draft → live and is **stateless**: it diffs the draft against the live post, which
> cannot tell a draft-side edit from a Substack-side one, and so silently reverts anything
> edited in Substack since the last push. That is not hypothetical — it was caught on
> 2026-09-01 about to revert a reworded line in `Nothing to Get` and a subtitle in
> `I Believe in You`. `substack-sync` is three-way against a stored baseline: it pulls
> Substack's edits into `draft.md` first, reports conflicts instead of picking a side, and
> then calls the push below. Use this section directly only for a piece with **no**
> Substack-side edits possible — in practice, one you just composed.

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
   reviewMarks[], failed[], structural, reordered[], suspect[]}`. **`failed` must be empty**;
   `structural:true` means stop and either recompose or edit by hand; `reviewMarks` flags any
   hunk that crossed a formatting boundary or was a large fallback — eyeball those in the
   editor. **`reordered`** means a target block's exact text was found at a *different* live
   index: the two lists are misaligned, not edited — the count guard alone could not see this,
   and a piece once aligned 30 footnotes against the wrong 30 live nodes while passing it.
5. **Hand off — and understand what already happened.** **On an already-published post there is
   no hand-off to give: the edit is already live.** Substack writes an edit to a *published* post
   through to the public page on autosave; **Continue** governs the *first* publish and the email,
   not later edits, and on a published post it is typically **disabled** because there is nothing
   unpublished left to ship. Observed 2026-09-01: eight live posts read the new text on their
   public URLs, and `Continue` was `disabled` on returning to the editor. So do not tell the user
   a staged edit is waiting for their click — **tell them it is live**, and give them the list of
   what changed so they can check it. Still never click **Continue / Publish / Send** yourself: on
   an *unpublished* draft that click is the real publication, and on any post it is the control
   that can **send email**.

## How it works (re-probe here if Substack changes)

- Substack's editor is **Tiptap** over ProseMirror, reachable at
  `document.querySelector('.ProseMirror').editor` (`editor.commands`, `editor.chain()`).
- **Body, the default:** put `text/html` on the **system pasteboard** and send a **real ⌘V** in
  **real Chrome**. Tiptap's paste converter builds the blocks from the HTML flavor.
  **Correction, 2026-09-01 — the old note here said "⌘V and keyboard modifiers are unreliable in
  the browser tool," and that was true of the wrong noun.** It is true of the **in-app browser
  pane**, where a synthetic ⌘V is a no-op and `navigator.clipboard.read()` throws
  `NotAllowedError: Document is not focused` (a programmatic `.focus()` does not satisfy the
  Clipboard API). It is **false of real Chrome**, where a real click plus a real ⌘V pastes
  correctly with `h2`/`em`/`strong`/links/blockquotes intact. Reading that note as surface-neutral
  is what kept this skill on the transcription path for months.
  **The pasteboard needs the HTML flavor specifically:** `pbcopy` sets only
  `public.utf8-plain-text`, which pastes as flat text and loses every heading and italic. Use
  AppleScript's `«data HTML<hex>»` (what `md_to_clipboard.py` does), and pass the script on
  **stdin** — a 32KB essay overruns the argv length limit.
- **Body, fallback:** dispatch a synthetic `paste` `ClipboardEvent` carrying `text/html` on
  `.ProseMirror`. Works on either surface, but requires the agent to reproduce the whole essay
  into the eval — see the transcription warning above.
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

## Recompose: check the images first

A recompose (a full re-paste, as opposed to the surgical re-sync above) **destroys any image
the live post holds that `draft.md` does not reference.** Images are URL-only on this desk —
the repo stores no bytes — so there is nothing to restore one from.

Run the check before any recompose, and treat it as a gate rather than advice:

```
python3 framework/tools/substack_sync.py images pieces/<name> images.js      # run in the editor
python3 framework/tools/substack_sync.py check-images pieces/<name> images.json
```

Non-zero exit names every live image the draft does not know about. Fix a gap by pasting the
URL into `draft.md` where the image belongs — **never** by deleting the image from the post.

## Guardrails

- **Never leave two editors open on the same post.** The sync tooling compares `draft.md` against
  **one** live post; it has no concept of two editors racing, and the newer save silently wins.
  On 2026-09-01 the in-app pane and real Chrome both held the same post — the pane still carrying
  the **empty pre-paste state** while Chrome held the finished essay — which put a 5,700-word
  published piece one autosave away from being overwritten with 38 characters of leftover test
  content, and swallowed edits the author made in the wrong window. **Before composing, navigate
  away or close every surface except the one you are composing on**, and say which surface you are
  using so the author edits the same one.
- **Never retype the essay to get it into Substack.** If a step requires the agent to reproduce
  the author's prose character by character, that step is wrong — reach for the clipboard
  transport. The author's words should travel **disk → pasteboard → browser**, never through the
  agent's fingers. This is not a performance preference: a transcription slip publishes a typo in
  the author's voice, and every guard downstream reads it as an intended edit.
- **Never click Publish/Continue/Send — the human publishes.** (Safety rule + editorial
  correctness.) But **do not mistake that for a safety net on a live post.** The old wording here
  claimed the opposite of the truth — that republish "only stages" and "holds doubly" on a live
  post. **It does not. On an already-published post, writing to the editor *is* publishing:** the
  text reaches readers on autosave, with no click and no further gate. The human-in-the-loop
  protection is real for an **unpublished** draft and **absent** for a live one.
  **What this changes in practice:** treat every republish edit as **already public the moment it
  lands**. Verify *before* writing, not after — the pre-image hash check is the only gate there
  is. What the no-click rule still buys you on a live post is narrow but real: **no email is
  sent.** A body edit does not notify subscribers; **Continue → Publish can.**
- **Republish is surgical, and touch-ups only.** It changes the smallest span that differs and
  nothing else. If the diff is structural — a block or footnote added, removed, or reordered —
  the tool **refuses** (`structural:true`, zero edits); recompose the piece or edit by hand
  instead of nuking-and-repaving a live essay. Never pass a flag to force past a refusal.
- **Framework stays generic.** No publication specifics, no secrets, no personal writing here.
- **Never recompose without the image check.** A re-paste silently drops any live image the
  draft does not reference, and nothing in the repo can rebuild it.
- **Verified + clean before it ships.** Preflight is not optional: footnote claims are
  fact-checked, and internal notes are stripped (the converter refuses output otherwise).
  Misquoting a real person or leaking a "Verify X" note into a public draft is the failure
  this step exists to prevent.
- **Verify before hand-off.** Always run the post-check; a paste that silently half-lands is
  the failure mode to catch (paragraph/footnote/marker counts).
- **Footnotes are coupled to Substack internals** (`.editor`, `insertFootnote`). If Substack
  changes them, call B's `missing` list or the leftover-marker count will surface it — fall
  back to endnotes (a trailing `<hr>` + numbered list) and flag for a re-probe.
