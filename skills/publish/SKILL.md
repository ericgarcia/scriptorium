---
name: publish
description: Compose a finished piece as a Substack DRAFT in one pass — title, subtitle, formatted body, images, and native footnotes — by driving the browser. Use when the user says "publish X to Substack", "load X into Substack", "put X on Substack", or wants a ready-to-review draft. Produces a DRAFT only; the human reviews and clicks Publish. Never auto-publishes or sends email.
---

# Publish (to Substack)

Turn a finished piece into a faithful, ready-to-review Substack **draft** in one pass.
Automation composes the draft; a human reviews and clicks Publish. This replaces the slow,
glitchy char-by-char editor typing with one paste + one footnote pass.

## Preconditions

- The piece is finished (`pieces/<name>/draft.md`) and has a **manifest**
  `pieces/<name>/publish.yaml` — `title`, `subtitle`, `footnotes` (native|endnotes|none),
  `send_email` (default false), optional `cover`.
- The browser is open on the target publication, **logged in**, at a **fresh empty** post
  composer (`https://<pub>.substack.com/publish/post?type=newsletter`). The user logs in —
  automation cannot enter credentials.
- Publication specifics and defaults live in the **instance** (e.g. `publishing/substack.md`),
  never in this framework skill.

## Steps

1. **Convert:** `python3 framework/tools/md_to_substack.py pieces/<name> <out.js>`
   Reads `draft.md` + `publish.yaml`, writes a self-contained JS snippet, and prints
   paragraph/heading/divider/image/footnote counts — sanity-check them against the piece.
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

## Guardrails

- **Draft-only.** Never click Publish/Continue/Send — the human publishes. (Safety rule +
  editorial correctness.)
- **Framework stays generic.** No publication specifics, no secrets, no personal writing here.
- **Verify before hand-off.** Always run the post-check; a paste that silently half-lands is
  the failure mode to catch (paragraph/footnote/marker counts).
- **Footnotes are coupled to Substack internals** (`.editor`, `insertFootnote`). If Substack
  changes them, call B's `missing` list or the leftover-marker count will surface it — fall
  back to endnotes (a trailing `<hr>` + numbered list) and flag for a re-probe.
