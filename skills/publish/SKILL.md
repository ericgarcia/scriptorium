---
name: publish
description: Compose a finished piece as a Substack DRAFT in one pass — verify the footnotes, strip internal notes, then set title, subtitle, formatted body, images, and native footnotes — by driving the browser. Use when the user says "publish X to Substack", "load X into Substack", "put X on Substack", or wants a ready-to-review draft. For a piece already live, it re-syncs the published post SURGICALLY — changing only what actually changed (a fixed word, a casing sweep, a reworded clause) and touching nothing else. A FRESH compose produces a private DRAFT that a human publishes — that first click is never delegated. A RE-SYNC of an already-published post STAGES (measured three times: the editor says Saved while the public page still serves the old text), so verify before writing AND after, against the cache-busted reader URL. Shipping a staged edit is delegable: ask in chat, then click Update → Update now. NEVER sends email — the confirm dialog is read first and, if any email option is present, it stops and asks.
---

# Publish (to Substack)

Turn a finished piece into a faithful, ready-to-review Substack **draft** in one pass.
Automation composes the draft; a human reviews and clicks Publish. This replaces the slow,
glitchy char-by-char editor typing with one paste + one footnote pass.

## Preconditions

- The piece is finished (`pieces/<name>/draft.md`) and has a **manifest**
  `pieces/<name>/publish.yaml` — **`outlets`** (see below), `title`, `subtitle`, `footnotes`
  (native|endnotes|none), `send_email` (default false), optional `cover`, optional **`post_url`**
  (record it once the piece is live; its presence switches this skill into **republish mode** —
  see below), and optional **`public_url`**.
- **`outlets:` says where the piece goes, and this skill NEVER picks one.** It is a list of
  instance-defined outlet names (`publishing/outlets.md` in the instance):

  ```yaml
  outlets:
    - substack
    - <other outlet>
  ```

  **A missing or empty `outlets:` is a STOP, not a default.** Do not publish to "the obvious
  one"; ask the author which outlets this piece is for, write the answer into the manifest, then
  continue. The set is normally settled when the piece is created (the `draft` skill asks), so an
  absent list means the question was never put — which is exactly the case where guessing is
  worst. **Publish to every outlet named, and verify each one separately.** A piece that is live
  on one outlet and missing from another is *not* published; it is half-published, and nothing
  will tell you unless you look.

  *Measured 2026-09-09:* the desk ran for weeks publishing to Substack alone while a second live
  host stood unfed, because this skill named only one destination and nothing ever compared the
  two. The piece published that morning was HTTP 200 on one host and **404 on the other**, and it
  took a hand-run `curl` to notice. (Legacy manifests may still carry `site: true` instead of an
  outlets list; treat it as the site outlet and migrate it when you touch the piece.)
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
- **Surface: default to the BUILT-IN BROWSER PANE for a re-sync; a fresh compose still needs
  REAL Chrome.** Measured 2026-09-10 (Eric's preference: *"if we can publish using the built in
  browser instead of the plugin that would be preferable for the skill in general"*). A re-sync is
  pure JS, and the one thing that made it look Chrome-only — getting the 80–125 KB snippet into
  the page without the agent retyping it — is solved by the **`window.name` carrier** below. Two
  live posts were re-synced from the pane that day with no Chrome, no clipboard and no
  Accessibility permission. A **fresh compose** is still Chrome, because its body arrives by a real
  ⌘V and **the pane cannot reach the pasteboard**. Never switch transports silently: say which
  surface you are on.
- **The Claude in Chrome extension is a framework requirement, not an optional extra** — see
  *Requirements* in the framework README for install and troubleshooting. In short: extension
  **v1.0.36+**, a **direct Anthropic plan**, a session signed in with **`/login`** (an API-key or
  `setup-token` session cannot use the extension at all), and `claude --chrome`. Verify with
  `/chrome` — **Status: Enabled**, **Extension: Installed**. If the user is missing it, **say so
  and stop**; do not quietly fall back to retyping the essay.
- Publication specifics and defaults live in the **instance** (e.g. `publishing/substack.md`),
  never in this framework skill.

## Name the session after the piece

Once you know which piece you are working on, rename the session to that piece's title, by
calling `mcp__ccd_session_mgmt__set_session_title` with `session_id: "self"` and the title. The
app's session list then reads as a shelf of pieces instead of a row of identical entries.

- **Take the title from `pieces/<slug>/publish.yaml` (`title:`), falling back to the README's
  H1.** Titles on this desk move late and often — one was retitled on Substack at publication and
  pulled back into the manifest — and `publish.yaml` is what actually ships to a reader.
- **Re-title whenever the piece changes.** A session that opens on one piece and moves to another
  should carry the name of the one it is on *now*. That is where the value is; naming it once at
  the start is the part that goes stale.
- **Best-effort, and silent when it fails.** The tool lives in the Claude Code desktop app. A
  terminal session does not have it, and there is no way to test for it except by calling. If it
  is missing, carry on — do not retry, do not mention it, and never let it block the work.
- **It will not stomp a title the author chose.** The app asks them to approve a rename over a
  title they set themselves, and replaces its own generated titles without asking. So propose
  freely; the guard is on their side of it.

## Preflight — critique gate, verify & strip editorial notes (DO THIS FIRST)

A published draft must be **critiqued**, carry **verified** claims, and carry **zero** internal
notes. The converter enforces the last; `check_verified.py` enforces the second; you enforce the
first.

0. **Verification gate — run it, and do not argue with it.**

   ```
   python3 framework/tools/check_verified.py pieces/<name>        # fresh compose: blocks
   python3 framework/tools/check_verified.py --resync pieces/<name>   # surgical fix: warns
   ```

   **Why this is step zero and not a footnote.** *The Knowledge of Good and Evil* went live on
   2026-08-25 carrying ~20 verbatim quotations of a named living person — on abuse, addiction and
   belief — taken from a machine-generated transcript and never checked against the audio. The
   desk had written the doubt down **three times**, in `notes.md`, in the `log/`, and under a
   README heading that still read *Anchors to verify before print*. **The compose ran anyway,
   because every existing guard read the draft and nothing read the notes about the draft** — and
   the scaffold is exactly where a careful writer puts a doubt they have not resolved yet.

   The tool **fails closed**: no clearance recorded anywhere means blocked. There is deliberately
   **no `--force`**. To clear a piece you write the clearance into `publish.yaml`, where it is
   reviewable and survives:

   ```yaml
   verified:
     date: 2026-09-02
     by: Eric
     covers: >-
       All 42 interview quotes checked against the audio; scripture loci and wording against the KJV.
   ```

   **`--resync` allows a surgical fix to an already-live post** — it introduces no new claim, and a
   gate that also blocked the corrections would mean the corpus could not be repaired until every
   ledger in it was closed, which is how a gate gets switched off for good. It still prints the open
   doubts. **A re-sync is not a clearance.**

   **What it cannot do:** it checks whether anyone *said* they checked. It cannot tell you a citation
   is correct. A green result is not a warrant.

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

0b-embeds. **An embed is not an image, and the image checks were blind to it.**
   An image can be made recompose-safe by putting its URL in `draft.md`, because the converter
   emits `<img>`. **No markdown emits an embed.** A YouTube embed is a `youtube2` node carrying
   a `videoId` and nothing URL-shaped, so the media scrape — which collected only URL-ish
   attributes — walked straight past it, and every check reported a clean post.

   Measured on `hollow-flute`, 2026-09-03: a YouTube embed sat at the top of a live post,
   invisible to `check-images`, to the body scrape (which excludes media), and therefore to the
   fidelity digest. A full recompose would have dropped it silently with nothing in the repo to
   rebuild it from.

   The scrape now also returns `embeds`, and `check-images` **refuses (exit 9)** while any live
   embed is unrecorded. Record each one in `publish.yaml`:

   ```yaml
   embeds:
     xNHwumRin9c: youtube2 — https://www.youtube.com/watch?v=... — top of post
   ```

   **Recording is NOT protection, and the message says so.** It makes the loss visible in
   advance; a recompose still drops the embed and it must be **re-added by hand in the composer
   afterwards.** Never resolve the refusal by deleting the embed from the post.

0b-marks. **A formatting-only edit was invisible to the entire chain — the same shape as
   0b-embeds, one layer down.** `substack_verify` and both `substack_repatch` engines compared
   READER-TEXT: tags stripped, entities unescaped, whitespace collapsed. Wrapping a word that is
   already in the post in `<em>` changes none of that, so it produced **zero diff**.

   Measured on `rising-after-falls`, 2026-09-09: after italicising *satsang* and *kirtan*, the
   regenerated surgical patch was **byte-identical in size to the previous one (29,782 bytes)**.
   The failure mode was the dangerous one — a **false pass**: the patcher reported `unchanged`
   and applied nothing, and the digest then reported **MATCH** with the italic simply not there.

   The tools now enumerate the **marked runs** — `em`, `strong`, and `link` with its href — from
   both sides and compare them for count, string and order:

   * `substack_verify` reports a formatting-only difference as **`DRIFT-MARKS`**, distinct from
     text drift, and prints a `marks` column beside `body` and `fn`. Read the kind: DRIFT means a
     word changed, DRIFT-MARKS means the words are right and the formatting is not.
   * `substack_repatch` (both engines) **applies** a missing or stray `em`/`strong` as a real
     ProseMirror mark — the block located by text, its text nodes walked to map string offsets to
     absolute positions (a block is split into several runs by its footnote anchors), the range
     **read back and asserted** to equal the exact string before `addMark` is dispatched. The
     report carries `marks: {applied, review, failed, unchanged}`.
   * **Link marks are reported, never applied.** A link mark carries Substack's own attributes;
     the safe repair is the structural engine re-inserting that block from the converter's HTML.
   * A run is a **span of formatting, not an element**: Substack serves `**a _b_ c**` back as
     three `<strong>` elements around the `<em>`, so contiguous spans of the same kind are
     coalesced before anything is compared. Skipping that reported drift on every
     bold-containing-an-italic in the corpus — 8 pieces of 34, none of them real.

   The first full sweep after this landed (2026-09-09, 34 live posts) found **7 pieces with real
   formatting drift** that every previous run had passed. The lesson is 0b-embeds' lesson again:
   **the scrape defines what can be checked, and what it does not collect cannot be verified.**

0b-links. **Status-check the in-body cross-links:**
   `python3 framework/tools/check_links.py pieces/<name>` — exits non-zero and names any link
   that does not resolve. A cross-link URL copied out of the scaffold is **unverified by
   default**; a dead sibling slug once sat in a piece's README and DASHBOARD as its canonical
   address from the day it published, because that URL had only ever been copied and never
   followed. Fix a dead link here **and** in every scaffold file that repeats it.

0b-pronouns. **Run the pronoun sweep, and justify every hit by naming who it points at:**
   `python3 framework/tools/check_pronouns.py pieces/<name> --names <the named figures> --strict`
   It lists sentence-initial forced capitals (a capital *He* silently reassigns a referent to the
   Son), every masculine pronoun and *a man / the man* (a hypothetical person takes they/them; the
   exception is *this person actually exists*), any lowercase *the one / someone / a mind* in a
   sentence that names God (this voice writes *the One*, *Someone*, and never lets God be a
   *what*), and any lowercase deity pronoun outside a quotation. **`--strict` refuses on those
   last two.** Added 2026-09-03 after *The Mask Comes Off Last* reached a composed draft with
   twenty-one generic masculines and a lowercase *the one* for God — both rules were in force,
   neither was in any sweep, and both were caught by the author reading the page. **A rule that
   is not in the sweep list is not in force.**
   Two more sections look **inside** a scripture quotation, where the first four stop (added
   2026-09-07): **E** lists every capitalized *He / Him / His / Himself* inside an italic or
   blockquoted scripture quotation, with its sentence — justify each as the Son, or, where the
   referent is the Father, bracket the substitution (*[Them] only shalt thou serve*, the verb
   bracketed too where agreement needs it); **F** lists every lowercase *me / my / mine / myself*
   inside a quotation whose footnote cites a Gospel — the Son's own pronouns take the house
   capital in a quotation (*He that hath seen Me*), never bracketed, disclosed once per piece.
   **E and F warn and never refuse**, because each needs a human call on a referent or a speaker.
   Measured on *False Light*, 2026-09-07, four misses in one draft that no section could see:
   Matthew 4:10 *Him only shalt thou serve*, Matthew 5:45 *He maketh His sun*, John 5:30 *mine
   own self*, John 15:5 *without me* — the first caught by the author reading the page. The
   Matthew 4:10 span had no footnote ref of its own (the ref sat on an earlier span), which is why
   E also qualifies a span on King James diction alone.

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

0c-clearance. **Clearance language is scaffold too, and the converter refuses it.** A footnote that
   says the checking was *done* — *(both consulted 2026-09-07)*, *checked 2026-09-02 against …*, a
   bare ISO date — is the desk's verification record reaching the reader. Its place is
   `publish.yaml` → `verified:`; the footnote carries the citation and nothing about the checking.
   Found 2026-09-07 on *The Towel*: eight loans were cleared with sources written into the footnotes,
   one of them carried its access date along, every guard read it as clean (a note that says the
   verifying is finished contains no *verify*), and the author caught it in the composer. The
   converter now refuses on an ISO date anywhere in the reader text, and on *consulted / accessed /
   retrieved* followed by a date, in both transports and in the suite's corpus check. Date a source
   the way a reader expects — *(2002)*, *March 10, 1967* — and put the day you checked it in the
   manifest.

0d. **Header gate — the post has a title AND a subtitle.** The converter (and therefore the
   clipboard tool) **refuses with exit 6** when `publish.yaml` has an empty `title` or
   `subtitle`, and there is no override: add the line. The subtitle is not decoration — it is
   the second line of every archive card, the homepage listing, the social preview and the
   email header, and **the composer accepts an empty one without a murmur.** Found 2026-09-03:
   a post had been live since 2026-08-05 with no subtitle at all, and nothing in the pipeline
   had ever looked, because every check compared *body* blocks and the header is not in the
   body. A `title`/`subtitle` whose trailing comment still says *PROPOSED* / *working title* /
   *not yet settled* **warns rather than refuses** — a private draft is where the author reviews
   it — but say so in chat, because that one line is the part of the post the author is least
   likely to re-read in the editor. Once they sign off, replace the comment with *settled
   <date>* so the suite's note goes quiet. The offline half of this guard runs in
   `test_suite.py` (`corpus_manifests`); the online half is `substack_verify.py --archive`
   (below), which reads the **publication's** list rather than the repo's and is the only check
   that can see a post the desk never composed.

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

1. **Take the pasteboard and paste in ONE process (the default since 2026-09-08):**

   ```
   python3 framework/tools/md_to_clipboard.py pieces/<name> --paste --expect-url publish/post/<id> --fn-b64 <fn.b64> --fn-out <fn.js>
   ```

   after a **real click** into the body (step 3 below happens first — the click gives the editor
   focus; the tool gives the keystroke). It acquires the **`pasteboard` lease** (`lease.py`,
   waiting up to 120s for another session to finish, then stopping and naming the holder — it
   never breaks a lease), runs the same converter and therefore the **same refusals** (a stray
   "verify", nested footnote refs, undefined/duplicated markers), places the HTML flavor, **reads
   it back off the pasteboard and hashes it**, locates the Chrome tab whose URL contains
   `--expect-url`, makes it the active tab of the frontmost window, **reads the active tab's URL
   back and refuses if it does not match**, re-reads the board one last time, sends a **real ⌘V
   through System Events**, and releases the lease. The pasteboard is exposed for the milliseconds
   of the keystroke, not for a tool round-trip.

   **Why this replaced the two-step.** The pasteboard is global mutable state. Until 2026-09-02 the
   tool checked only that "HTML" appeared in `clipboard info`; **it reported a clean write while the
   board held another piece's footnote snippet**, which pasted into a fresh post. The read-back fixed
   that, and `--verify` immediately before the ⌘V was added — and on 2026-09-07 **one session still
   lost the board three times in an afternoon** (a stranger's name and an `assetError` node; a stray
   quotation; a re-check seconds before a paste found another session's whole essay). Every taker was
   another Claude session composing. So: a lease, because the takers all run this tool; and one
   process, because the gap `--verify` guarded was a full round-trip. **Needs Accessibility
   permission** for the app running the tool (System Settings → Privacy & Security →
   Accessibility); without it the tool stops at `not allowed to send keystrokes (1002)` with nothing
   pasted and the lease released. **Say so and stop; do not fall back to retyping.**

   **The two-step still exists and is still lease-guarded:** run without `--paste` to load and hold
   the lease, `--verify` immediately before a ⌘V sent from the browser tool, then `--release`. Use it
   only where System Events cannot reach the browser.
2. **Open the composer in real Chrome** and set Title + Subtitle by JS (small, no prose in it),
   then `clearContent(true)` so a retry can't append to a half-paste. **Snapshot any image or embed
   the live doc holds FIRST** (see 0b-images / 0b-embeds); `clearContent` removes them, and an
   `undo` is a rescue, not a plan (measured 2026-09-07: a hero added in the composer was cleared
   before it was read; `undo` brought it back that time).
3. **Body:** a **real click** into the body, then step 1's `--paste`. Formatting, links and dividers
   arrive intact; footnote refs remain as `[[FNn]]` markers.
   **Substack applies smart-quote input rules on paste** (`'`→`’`, `"`→`“ ”`), so the live text
   will differ from the draft at every apostrophe — that is expected, it is what the whole
   corpus published with, and step 6's digest must account for it rather than treat it as
   corruption.
4. **Footnotes:** run the `--fn-out` snippet. It turns every `[[FNn]]` marker into a **native**
   Substack footnote via Tiptap's `insertFootnote` and fills each note's rich content. Returns
   `{inserted, missing}` — **`missing` must be empty.** Markers are keyed on the footnote's
   **name**, not a number (`[[FNbeelzebul]]`), so grep for `\[\[FN[a-z0-9]+\]\]`.

   **Getting the snippet into the page, measured 2026-09-02.** It carries the author's footnote
   prose, so retyping it into an eval is the same transcription risk the clipboard exists to
   remove — and two obvious alternatives do **not** work on this surface: both
   `navigator.clipboard.readText()` and a `fetch()` to a CORS-enabled `http://127.0.0.1`
   **hang and time out the CDP call at 45s**, with the renderer alive and responsive afterwards
   and no permission prompt on screen. **What does work:** base64 the footnote data (`--fn-b64` writes it), put the cursor in an EMPTY
   TOP-LEVEL paragraph between the body and the footnotes (`splitBlock` at the end of the last body
   node — not `focus('end')`, which lands INSIDE the last footnote), and paste it as text with the
   same lease-guarded one-process tool: `md_to_clipboard.py --text-file <fn.b64> --paste
   --expect-url publish/post/<id>` (base64's charset is immune to the smart-quote input rules that
   would corrupt raw JSON). Read it back out of the DOM with `atob`, **checksum it against the
   file**, delete the carrier node, then insert. **Insert in batches of ~8–9** — thirty-five in one call also exceeds the 45s
   timeout. Prove the transfer with a checksum computed on both sides before inserting anything.
   **Two failures measured on this path, 2026-09-10, and both are silent.**
   **(a) `--paste` raises the window but does not put the caret in the editor.** It reported
   *"pasted body … the lease is released"* into a document that stayed empty — the report is a claim
   about the keystroke, not evidence about the doc (`hasFocus:false`, `editorFocused:false` on the
   page afterwards). **Always a real coordinate click into the body first**, then the ⌘V, then the
   count check. **(b) A carrier ⌘V that appears to have failed may have landed in the wrong place.**
   One went into the *middle of a paragraph*, splitting it mid-word and burying 8,796 characters
   inside the remainder, with no error anywhere; a top-node count of 80 against an expected 79 was
   the only tell. **Check the node count against the converter's, not just the marker count.**

   **And when you strip a base64 carrier back out of prose, bound the match by the payload's known
   length — never by charset greed.** `/^[A-Za-z0-9+/=]{4000,}/` removed 8,797 characters instead of
   8,796, because **`e` is a base64 character**: it ate the *e* of *"a long time"* and left *"a long
   tim taking pictures down"* mid-essay. Use `text.slice(0, text.length - knownB64Len)`, or splice at
   the exact count. **That is a transcription-class corruption introduced by a repair — the precise
   class this whole transport exists to prevent — and no contraction, link or pronoun sweep can see
   it. Only the fidelity digest can.**

5. **Post-check (JS):** title/subtitle set · block counts match · **0 empty paragraphs** ·
   heading/divider/image counts · footnotes == manifest count · **0 `[[FN` markers left** ·
   in-body sibling links present. Report the numbers; don't say "done" without them.
6. **Fidelity check — do this, it is the whole point.** **Read a mismatch before repairing it.**
   An intermediate run mismatched on exactly the blocks carrying `[[FN]]` markers — the live text
   still held them while `render_reader` strips them, so the mismatch was *expected at that point*
   rather than damage, and treating it as damage would have caused a second, needless repair. Run the
   digest **after** the footnotes are in; if it mismatches before that, check whether the differing
   blocks are precisely the marker-bearing ones. Hash every live block's flattened text,
   digest the list, and compare against the same digest computed from `draft.md` via
   `render_reader`. **The two digests must be identical.** A clipboard paste cannot introduce a
   transcription error, so this is cheap and should pass first time; if it does *not*, something
   else moved (a concurrent edit to the draft, a Substack-side input rule) and that is worth
   knowing before a human publishes.
7. **Hand off:** the draft is composed. Tell the user to review it in Substack and click
   **Publish** themselves. **Do not click Publish / Continue / Send on a FIRST publication.**
   That click is the publication itself and is the one that can mail the subscriber list; it stays
   the author's, and asking for permission does not transfer it. *(Shipping a later **edit** to an
   already-published post is a different act with a different rule — see Republish step 5.)*

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

## Getting a snippet into the page — the `window.name` carrier (pane transport)

Every JS path below (surgical repatch, structural repatch, the footnote pass) needs an
80–125 KB generated snippet **inside the page**. The agent must never retype it: that is the
transcription risk the whole transport chapter exists to remove. In **real Chrome** the clipboard
does this. In the **built-in browser pane** use this, measured 2026-09-10 on two live posts.

**Every network route into the page is shut, and no response header opens one:**

| route, from the https editor page | result |
|---|---|
| `fetch('http://127.0.0.1:<port>/…')` | ❌ `TypeError: Failed to fetch` |
| `<script src="http://127.0.0.1:<port>/…">` | ❌ `onerror` |
| `window.open(...)` + `postMessage` to opener | ❌ the pane **navigates the current tab**; no popup, no opener |

**Neither of the first two reaches the server** — the access log stays empty — so the pane blocks
http subresources from an https document, client-side. Both were tried with correct CORS *and*
`Access-Control-Allow-Private-Network: true` for Chrome's PNA preflight. **Do not debug the
server.** Substack is not the obstacle either: its only CSP is `frame-ancestors`, with no
`connect-src` and no `script-src`, which is why inline execution works once the bytes are in.

**What works: `window.name` survives a cross-origin top-level navigation.**

```
python3 framework/tools/pane_carry.py <snippet-path>
```

It writes the carrier page next to the snippet, serves both on a **session-derived port that
fails loudly rather than sharing**, and prints the carry URL and the payload's **sha256**. Then:

1. Navigate the pane tab to the printed **carry URL**. That page is *same-origin* with the file,
   so its own `fetch` is fine; it writes `JSON.stringify({file, hash, text})` into `window.name`.
2. Navigate the **same tab** to the post editor. `window.name` crosses intact (measured at
   **127,994 chars**).
3. **Re-hash in the page and compare to the printed sha256 before arming the payload.** Not
   ceremony: *a port is not an identity; identify the bytes at the point of use.* It is what makes
   an unauthenticated localhost hop safe, and it is the step someone will be tempted to skip.
4. Execute by appending an inline `<script>` whose `textContent` is the verified payload,
   assigning the snippet's promise to a global you read next.
   **A bare `eval` of an opaque variable is refused by the agent's own permission classifier, and
   that refusal is correct.** The script-element form is the ordinary way to run a script and it
   keeps the hash gate in front of execution. Do not go looking for a way around the refusal.

Don't hand-write the carrier page: a transport that is reassembled from memory each time is a
transport whose hash check eventually goes missing.

## Republish — surgically re-sync a live post

> **⚠️ Republish edits a public post. Treat the write as irreversible; do NOT assume it has
> shipped.** These are two different things and both matter.
>
> **Measured 2026-09-01, twice, on `The Sheep in the Basement` and `In the Name`:** guarded body
> edits were applied to the live editor, the header showed **Saved** — and the **public page still
> served the old text**. Not a CDN artifact: the check was cache-busted and came back
> `cf-cache-status: DYNAMIC` with no `age` header. **Update** was present and **enabled**; only
> after **Update → Update now** did the public page change. So on that date a live-post body edit
> **staged** rather than published, which is the opposite of what this box previously asserted
> (*"visible to readers immediately… Continue is normally disabled afterwards"*, from `bea8e5a`).
>
> **Do not replace one belief with the other.** The earlier note was written from a real
> observation too; Substack's behaviour may differ by post type or may simply have changed.
> **The rule that survives either way: never infer the outcome — check the public page.**
> - **Verify BEFORE writing.** If autosave *does* publish, the pre-image hash check is the only
>   gate that exists. This costs nothing when it turns out not to be needed.
> - **Verify AFTER, against the reader URL**, cache-busted. That is the only evidence that the
>   change reached readers.
> - **Never report a re-sync as done on the strength of "Saved."** Either it is confirmed on the
>   public page, or it is *staged and awaiting Update* — say which.
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
5. **Ship it: ask, then click Update → Update now.** A body edit to a published post
   **stages** — measured three times now (2026-09-01 on two posts, 2026-09-03 on `hollow-flute`):
   the editor reads **Saved**, **Update** is **enabled**, and the **cache-busted public page still
   serves the old text.** So the edit is *not* live until the button is pressed, and leaving it
   pressed-by-nobody strands a correction the author believes they asked for.

   **The default is therefore: ask the user for permission in chat, and on a clear yes, click it
   yourself.** Do not make a person walk to a browser to press a button on a change they already
   approved. **What is NOT delegated by that yes:** the *first* publication of an unpublished
   draft (step 7 above) — that click is the publication and stays theirs.

   **The email guard is absolute and survives this change.** Before confirming, read the dialog
   and prove it cannot mail anyone: look for *email / send / newsletter / notify / subscribers
   will receive* wording and for any enabled email control. On an already-published post the
   dialog has consistently offered **none** — audience and comment radios only. **If an email
   option is present, or you cannot tell, STOP and ask.** Never disable, uncheck, or work around
   one to get the button pressed.

   **Then verify against the cache-busted reader URL, not the "Your post is live!" screen** —
   that screen is a claim, not evidence. `substack_verify.py --fresh <piece>` is the evidence.
   Report *confirmed public*, or *staged, awaiting Update* — never "done" on the strength of
   **Saved**.

   **Read the report** the patch returns: `{stagedEdits, unchanged, applied[], footnoteChanges[],
   reviewMarks[], failed[], structural, reordered[], suspect[]}`. **`failed` must be empty** before
   any of the above.

### Structural republish — when the surgical tool refuses

`substack_repatch.py` refuses a block-count change, and it is right to: a paragraph added,
removed, merged or split is a rewrite, and the surgical engine's 1:1 alignment would write into
the wrong paragraph. **The answer used to be "recompose or edit by hand," and both were bad on a
post that carries an embed or an image** — a recompose destroys the embed (nothing in the repo can
rebuild it), and "by hand" meant a hand-built snippet that needed one more guard every time it
ran (`hollow-flute`, three times, 2026-09-04 → 07). That snippet is now the tool's second engine:

```
python3 framework/tools/substack_repatch.py --structural pieces/<name> <out.js>
```

Run it once in the live post's editor, like the surgical snippet. It **aligns the draft against
the live document by block text** (LCS), then: **anchor-bearing blocks pair 1:1 by order inside
each changed range and are edited by text hunk only**, so a native footnote anchor is never
touched by HTML; every other changed block is **replaced whole from the converter's own HTML**
(italics, links), with quotes **smartened outside tags only** — a curled quote inside `href="…"`
is a dead link, measured 2026-09-04; **a retired footnote's anchor is dropped**, and the orphaned
footnote node too if the editor does not remove it itself (Substack did, measured 2026-09-07); an
**insert lands on the draft's side of a divider** (after the `---` if the draft puts one before
the new block, otherwise right after the preceding block).

**It refuses, before touching anything,** when a block's HTML does not hash to its own text (the
**transcription guard** — the sha256/16 is computed by the generator, so a snippet retyped into
an eval fails closed on any slip); when anchor-bearing blocks do not pair 1:1 (un-merge or re-split
the draft so each footnote-bearing paragraph has a live counterpart — that is what the v3 sync
needed); when the draft **adds** a footnote (`insertFootnote` is not automated here — add it in
the composer, or recompose); when footnote order differs; or when a hunk would span an inline
node or cross a mark boundary.

**Read the report:** `{refused, ok, applied[], failed[], plan{replace,insert,delete,hunk,fnHunk,
dropAnchor}, final{body, footnotes, anchors, bodyMismatch[], fnMismatch[], linksMissing[],
dividersOff[], firstNode}}`. **`refused` must be null and `ok` must be true**; `final` is the
whole document read back after the edits — counts, every block's text, every footnote, the anchor
count, and a link mark on every block whose HTML carried one. Then the same as any republish:
ask, click **Update → Update now** after reading the dialog for email, and **`substack_verify
--fresh`**. The engine is exercised against a stubbed editor on every piece by the suite
(`test_substack_structural.js`, cases S1–S9).

## After a human clicks Publish — mark the file as published

A piece keeps its text in `draft.md` for its whole life. The filename does **not** change
on publication: nine tools identify a piece by that name, and a second name would mean a
call site that missed the rename does not fail — it silently drops the piece from the
corpus checks. The **header** carries the state instead.

Once the post is live, record the facts and rewrite the header:

```
# in publish.yaml
public_url:   https://elmuffin.substack.com/p/<slug>
published_at: YYYY-MM-DD        # the live post's own post_date, not the day you noticed

python3 framework/tools/piece_header.py --apply <slug>
```

That replaces the `*Draft — …*` scaffold line with

> *Published 2026-08-27 · [Nothing to Get](…) —*
> *this file is the source of record for the live post.*
> *Edits here are not live until pushed (`substack_sync push`),*
> *and `substack_verify --fresh` confirms they landed.*

and drops a now-false `*(working title)*` from the H1 when the piece shipped under that
exact title. The rest of the scaffold note — voice, arc, consent boundaries, scripture
conventions — is preserved verbatim; only the word "Draft" goes.

All of it sits above the first `---`, which the converter discards, so it can never reach
a reader. It is checked by the suite (`corpus_headers`) precisely because invisible things
rot unnoticed.

## Confirm it reached readers (`substack_verify`)

"Saved" is not "shipped," and a baseline is a local file — a piece can match its
baseline perfectly while the live post says something else. After any write to a live
post, check the page a reader actually gets:

```
python3 framework/tools/substack_verify.py --fresh pieces/<name>
```

It fetches the public URL over plain HTTP (no browser, no credentials, no writes),
pulls the post out of the page's `window._preloads`, renders the local draft, and
compares block for block and footnote for footnote. `--fresh` cache-busts — measured to
turn `cf-cache-status: HIT` into `MISS` — so a stale CDN copy cannot fake either a pass
or a failure.

Exit 0 match, 1 drift, 2 nothing could be read. **2 is not a pass**: a run that verified
no pages reports failure, because "I could not look" and "it matches" must never wear
the same face.

Run with no arguments to sweep every published piece. Each piece's **title and subtitle**
are compared too (normalised for curly quotes and dashes): the body comparison cannot see
them, since they are not in `body_html`, and an **empty live subtitle is drift on its own**.

**`--archive` checks the publication, not the repo.** Every other mode starts from
`pieces/` and can only verify what the desk knows about. `--archive` walks the public
archive API instead — the reader's list — and fails on any live post with **no subtitle**,
no title, one the desk has **no manifest for**, or a header that differs from its manifest.
That is the check that would have caught a post which had sat live for a month with an
empty subtitle (2026-08-05 → 2026-09-03): it was composed by hand, before the desk, so
nothing keyed off `pieces/` could see it. Run it after every publish.

```
python3 framework/tools/substack_verify.py --archive --fresh
```

> Do not put this in CI on a GitHub-hosted runner. Measured 2026-09-02: Substack returns
> **403 to Azure IP ranges** on every path — page, API, and RSS, with any user agent. It
> is an IP block, so there is no header that fixes it. Run it locally, or from a
> self-hosted runner.

## The other outlets — export the bundle, hand it over, verify the reader URL

Substack is bespoke because Substack has no write API. **Nothing else has to be**, and the rest
of `outlets:` is served by one neutral artifact rather than one bespoke integration per host.

**Do this as part of publishing, not afterwards.** A piece is published when every outlet it
names has it. Run this once the piece is confirmed live on the outlets that need a human click,
so the exported text is the text readers actually got.

1. **Export the bundle** — the piece must declare the outlet, or it is not exported:

   ```
   python3 framework/tools/md_to_site.py <bundle-dir> pieces/<name> --outlet <outlet> --apply
   ```

   `md_to_site.py` strips the same things the Substack converter strips — the scaffold above the
   first `---`, HTML comments, and anything after a `†` in a footnote — and **refuses** a draft
   with no `---` rather than guessing where the desk ends and the essay begins. Pass
   `--canonical-base` and `--syndicated substack` so the bundle records which URL is canonical
   and which is syndication; getting that backwards is an SEO decision made by accident.

2. **Hand the bundle to the destination.** How is instance-specific and lives in the instance's
   `publishing/` notes — never here. The framework's job ends at the bundle; the instance's note
   says where it goes and what builds it.

3. **Verify on the reader URL, exactly as with Substack.** A build that succeeded is not a page
   that exists. Fetch the piece's public address on that outlet and confirm it returns 200 and
   contains the text — the same *check, don't infer* rule the Substack half of this skill is
   built on. **A 404 here is the normal failure**, because a piece can be absent from a bundle
   for a quiet reason (it never declared the outlet) and every step will still report success.

4. **Record the outlet's URL** in `publish.yaml` beside `public_url`, so a sibling essay's
   cross-link can reach for the right host.

**Half-published is the failure to design against.** Live on one outlet and missing from another
is the state nothing reports, because each half looks complete from inside itself. Check every
outlet in the list, every time, and say which ones you confirmed.

5. **Audit the outlets against each other** — the check that looks across, rather than each
   outlet checking itself:

   ```
   python3 framework/tools/outlet_audit.py            # after any publish
   ```

   It reads the instance's outlet registry (`publishing/outlets.yaml`; the framework holds no
   URLs), and for every piece that is **published and declares an outlet** it fetches that
   outlet's reader URL cache-busted and expects 200. It also runs the **reverse** direction from
   each outlet's sitemap — every live URL must be a piece the desk knows — which is the only
   direction that can see a page the desk never produced. **Exit 3 is drift; exit 2 is "could not
   reach", which never wears the same face as a pass.**

   Two things it deliberately does *not* treat as failures: a piece that declares an outlet but
   **is not published yet** (reported and skipped — declaration is intent, publication is fact),
   and a legacy manifest that opts in with `site: true` instead of an `outlets:` list (counted,
   and reported as a migration count).

   **Record the outlet's URL in the manifest** (`site_url`, `public_url`) rather than relying on
   the audit to guess it. A guessed URL is derived from a slug, and slugs diverge: one piece
   publishes as `theythem` on one outlet and `they-them` on another, and a retitled piece keeps
   its old directory name for ever. A recorded URL always wins over a derived one.

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
  into the eval — see the transcription warning above. **Note the open question this leaves:** the
  only defect in this path is the transcription, and the `window.name` carrier removes
  transcription entirely. So a **fresh compose from the pane** looks reachable — carry the
  `md_to_substack.py` snippet in, hash-check it, inject it. **Nobody has measured it**, so it is
  not the default and must not be written up as working until someone composes a throwaway draft
  and checks the fidelity digest.
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
- **The pasteboard is a leased singleton.** `md_to_clipboard.py` takes the `pasteboard` lease and
  waits for it; never `pbcopy` around the tool, and never paste from a board you did not load under
  the lease in the same process. Three races in one afternoon (2026-09-07), all to sibling sessions,
  are why. If `--paste` is refused for Accessibility, say so and stop; do not fall back to retyping.
- **Never retype the essay to get it into Substack.** If a step requires the agent to reproduce
  the author's prose character by character, that step is wrong — reach for the clipboard
  transport. The author's words should travel **disk → pasteboard → browser**, never through the
  agent's fingers. This is not a performance preference: a transcription slip publishes a typo in
  the author's voice, and every guard downstream reads it as an intended edit.
- **Shipping an edit is delegable; publishing is not.** Two different acts, two rules.
  **First publication of an unpublished draft: never click.** It is the publication, and it is the
  control that can mail the subscriber list. **Shipping a later edit to an already-published post:
  ask in chat, and on a clear yes, click Update → Update now yourself** (revised 2026-09-03 on
  Eric's instruction — the old blanket never-click made a person press a button on a change they
  had already approved, and stranded corrections behind it).
  **The email guard does not move.** Read the confirm dialog before confirming and prove it cannot
  mail anyone — *email / send / newsletter / notify* wording, any enabled email control. On an
  already-published post it has consistently offered none. **If one is present, or you cannot tell,
  STOP and ask.** Never uncheck or route around one.
  **And permission is per-change, not standing:** a yes to shipping this fix is not a yes to the
  next one.
- **Verify both sides of a live write, and never infer the outcome.** *Before*, because the
  pre-image hash check is the only gate that exists if autosave turns out to publish. *After*,
  against the **cache-busted reader URL** — measured repeatedly, the editor says *Saved* while
  readers still get the old text. **"Saved" is not "shipped," and neither is "Your post is live!"**
  — that screen is a claim; `substack_verify --fresh` is the evidence.
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
