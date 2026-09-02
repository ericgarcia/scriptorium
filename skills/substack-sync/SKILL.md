---
name: substack-sync
description: Two-way sync between a piece's draft.md and its already-live Substack post, with conflict detection. Use when the user says "sync X", "re-sync X", "pull my Substack edits back", "the live post is behind", "update the published post", or wants a live post and its draft brought back into agreement. Classifies every block three ways against a stored baseline — push (draft moved), pull (Substack moved), conflict (both moved) — pulls Substack-side edits into draft.md, then pushes. On an already-published post the push is LIVE the moment it lands — there is no staging gate; only email stays behind a human click.
---

# Substack sync (two-way, with conflicts)

Bring a **live** post and its `draft.md` back into agreement, in whichever direction each
change actually travelled. Use this — not a bare push — for any piece that is already
published.

## Why this is not just "republish"

`publish`'s republish mode pushes draft → live and is stateless: it diffs the draft against
the live post. That is right for a one-way push and wrong the moment edits can start on
**both** sides, because a bare difference cannot tell you which side moved.

That is not hypothetical. On 2026-09-01, `Nothing to Get` read *"is this for us"* in the
draft and *"is this for me"* live — the phrase entered at the compose commit and was never
touched again, so the edit had been made in Substack. `I Believe in You` had its subtitle
capitalized in Substack while `publish.yaml` still held the lowercase form. A stateless push
would have reverted both and reported success.

So sync is **three-way**, against a baseline of what was last known synced:

| draft vs baseline | live vs baseline | | |
|---|---|---|---|
| same | same | **unchanged** | nothing to do |
| changed | same | **push** | the ordinary re-sync |
| same | changed | **pull** | bring Substack's edit into `draft.md` |
| changed | changed, same text | **converged** | nothing to do |
| changed | changed, different | **conflict** | **stop** — a human decides |

Conflicts need the same block edited on both sides between syncs, so they should be
exceedingly rare. Rare is not never, and the baseline exists so that when one happens it is
**reported** rather than silently resolved in whichever direction the tool ran.

## Preconditions

- The piece is live and `publish.yaml` carries **`post_url`** (the *editor* address,
  `/publish/post/<id>`) and **`public_url`** (the reader address, `/p/<slug>`). These are
  different URLs and both are needed.
- The browser is open and **logged in** on that post's editor. Automation cannot enter
  credentials.
- The piece has a **baseline** (`<piece>/sync-baseline.json`). If it does not, seed one
  first — see *First run* below.

## The loop

Each browser step is one JS eval in the live post's editor.

1. **Scan.** `python3 framework/tools/substack_sync.py scan pieces/<name> scan.js`
   Run it in the editor; save the JSON it returns. It returns title, subtitle and one hash
   per block — not the text, so a 6,000-word essay costs a few hundred bytes to compare.
2. **Plan.** `python3 framework/tools/substack_sync.py plan pieces/<name> live.json plan.json`
   Classifies every block and prints the tally. **Read it before doing anything else.**
   Structural rows (a block added or removed on one side) are described and never
   auto-merged.
3. **Fetch** — only if there are pulls or conflicts:
   `python3 framework/tools/substack_sync.py fetch pieces/<name> plan.json fetch.js`
   Run it; it returns the live text for *just those* blocks.
4. **Pull.** `python3 framework/tools/substack_sync.py pull pieces/<name> plan.json livetext.json`
   Writes the Substack-side edits into `draft.md`, changing only the runs that differ and
   leaving emphasis, links and footnote markers intact. Every edit is **verified by
   re-rendering** the block and comparing; anything that does not land exactly is reported
   for a human instead of being written. It **refuses outright** if there are conflicts.
5. **Push.** `python3 framework/tools/substack_repatch.py pieces/<name> push.js`, run once
   in the editor, then check the report (see *Reading the push report*).

   > **Do not retype a large push script into the browser.** `substack_repatch.py` bakes the
   > **entire rendered essay** into its snippet — 73KB for a 5,700-word piece — so driving it by
   > hand means the agent reproducing every byte of the author's prose. On a **live, public**
   > post that is the worst place to accept a transcription risk: one wrong character diffs as a
   > real edit, the tool applies it faithfully, and the guards cannot object because to them a
   > typo is just another edit.
   >
   > **When the script is small enough to read in full, run it as-is.** When it is not, and
   > `plan` has already told you exactly which blocks moved, prefer a **minimal guarded edit**:
   > pull the target text **programmatically** out of the generated script (never retype it),
   > and apply only the changed span with every guard the tool uses, plus one it lacks —
   >
   > - refuse unless body and footnote counts match the draft exactly (structural guard);
   > - refuse if the old text is absent, or occurs more than once (alignment guard);
   > - refuse if the span's start and end marks differ (formatting guard — this one fires in
   >   practice: a span crossing `<em>` would otherwise flatten the emphasis);
   > - **re-read `doc.textBetween(from, to)` and refuse unless it equals the expected text**
   >   (position guard — `substack_repatch.py` does not do this);
   > - apply multiple edits **latest-position-first** so unapplied positions stay valid;
   > - normalize curly/straight apostrophes for the *lookup*, and **re-smarten the replacement
   >   to match the live document's own typography** so nothing downgrades a `’` to a `'`.
   >
   > Six live posts were re-synced this way on 2026-09-01; every one reported `marks: 0`, and a
   > re-scan and re-plan read `converged / nothing to do` before sealing.
6. **Hand off — confirm on the public page, do not infer.** **Measured 2026-09-01:** a guarded
   body edit on a live post left the editor showing *Saved* while the **public page still served
   the old text**, until **Update → Update now** was clicked (cache-busted check;
   `cf-cache-status: DYNAMIC`, so not a caching artifact). Earlier notes here asserted the
   opposite. **So check the cache-busted reader URL and report what you actually saw** — either
   *live and confirmed*, or *staged, awaiting Update*. **"Saved" is not "shipped."** The old
   wording follows and is kept for the part that is still true — that you must verify before
   writing, and that the write itself is not undoable.

   **Original note — the push is already public.** **There is no staging gate on a live post.** The
   edit reaches readers on autosave; **Continue** is usually **disabled** afterwards, because
   nothing is left unpublished. Do not report the sync as "staged, awaiting your click" — report
   it as **done**, and hand over the list of what changed so a human can read it on the public
   page. Never click **Continue / Publish / Send** yourself: that control is what **sends email**.
7. **Seal.** Re-run *scan*, then
   `python3 framework/tools/substack_sync.py seal pieces/<name> live-after.json`
   It refuses unless draft and live now agree, and records the new baseline. **Do not skip
   this** — an unsealed sync leaves the next one unable to tell which side moved.

## First run (a piece published before sync existed)

`plan` refuses without a baseline, because it would have to guess. **Do not guess either.**

1. Scan the live post first.
2. `python3 framework/tools/substack_sync.py detect pieces/<name> live.json`
   Renders `draft.md` at every commit that touched it and reports how many blocks each
   revision still matches. **The revision matching the live post on every body block is the
   state that was last pushed** — that is the baseline, whatever its date.
3. `seed pieces/<name> --from-git <the rev detect names>`

`--from-draft` and `--from-live` also exist, but they are *assertions*, and a wrong
assertion makes the first sync push or pull something nobody asked for.

**Never seed from "the newest commit" because it is newest.** A commit can carry an
editorial pass that was never published, and seeding from it **inverts every row that pass
touched**: the plan reports a PULL, and the sync dutifully reverts the author's own work in
`draft.md` and reports success.

This is the mistake that motivated `detect`. `e37d5f3` bundled a corpus-wide deity-pronoun
capitalization sweep into an unrelated compose commit, and the sweep never reached Substack.
On `The Way Home Is Down` the comparison was run by hand and caught it — ten capitals that
would have been reverted. On `They/Them` and `I Believe in You` it was **not** run, and ten
more capitals were quietly pulled out of two live essays before the author caught it. Against
the live scan, `detect` scores the right revision 83/83 and the tempting newest one 80/83.

The check is the tool's job, not the operator's memory. Run it.

## Before a recompose: check the images

A surgical push never touches an image. A **recompose** re-pastes the whole body, and any
image the live post holds that `draft.md` does not reference is destroyed by that paste.

Images are **URL-only** on this desk (2026-09-01): the repo stores no bytes, and a draft
points at the asset already hosted on Substack. That keeps binaries out of git history, and
it is safe **only** while every live image is actually referenced in the draft — so check,
every time, before anything rebuilds a post:

```
python3 framework/tools/substack_sync.py images pieces/<name> images.js     # run it in the editor
python3 framework/tools/substack_sync.py check-images pieces/<name> images.json
```

It exits non-zero and names any live image the draft does not know about. **Fix a gap by
pasting that URL into `draft.md` where the image belongs — never by deleting the image from
the post.**

Two details it handles so you don't have to: the same picture appears twice in a scrape (the
node's S3 `src` and the rendered `<img>`, which Substack wraps in a `substackcdn.com/image/
fetch/…` transform), and the wrapper embeds the original URL-encoded — so it unwraps and
dedupes before comparing. Without that it would report a perfectly safe post as unsafe.

`The Highest Peak` is why this exists: a `captionedImage` in the body, no image markdown in
the draft, and a recompose requested. It was one paste from losing the image with nothing on
disk to rebuild it from.

## Reading the push report

`{stagedEdits, unchanged, applied[], footnoteChanges[], reviewMarks[], failed[],
structural, reordered[], suspect[]}`.

- **`failed` must be empty.**
- `structural: true` — nothing was applied. Check `reordered` and `suspect`:
  - **`reordered`** — a target block's exact text sits at a *different* live index. The two
    lists are misaligned, not edited. Do not patch; find out why.
  - **`suspect`** — a changed pair too dissimilar to be the same node.
- `reviewMarks` — a hunk that crossed a formatting boundary. Eyeball those in the editor.

## Guardrails

- **Never click Publish / Continue / Update / Send** — that control **sends email**. But the old
  claim here, *"the skill stages; a human ships — this holds doubly here,"* was **backwards, and
  it was most wrong exactly where it sounded most careful.** The target being a live post is what
  **removes** the gate, not what strengthens it: **on an already-published post the push is the
  publication.** Readers see it on autosave.
  **Therefore the checks that matter all run _before_ the write:** the pre-image hash per block,
  the conflict refusal, the structural refusal. There is no after. Anything wrong that lands is
  **already public**, and the fix is another public edit — so re-read *Reading the push report*
  and mean it.
- **Conflicts stop the run.** Do not pick a side. Show the user both versions and let them
  choose.
- **Structural divergence is not auto-merged.** A block added, removed or reordered on
  either side is described and left alone. A live essay is not the place to guess at a
  paragraph.
- **Never pass a flag to force past a refusal.** The refusals here exist because each one
  has already been the failure mode once.
- **Seal every completed sync.** The baseline is the whole mechanism.
- **A pull that reverses an editorial pass is a red flag, not a result.** If a plan wants to
  undo something the author clearly meant (capitalization, a house convention, a considered
  rewrite), stop and re-run `detect` — the baseline is probably wrong, and the "Substack-side
  edit" is really the live post being *behind*.
- **The same preflight as `publish` applies**: footnote claims fact-checked, internal notes
  behind a `†`, and the critique gate for a substantive re-sync.

## Two bugs this replaced (do not reintroduce them)

Both were found on 2026-09-01, in a batch of six live posts that were one click from being
damaged.

- **Footnote order.** `md_to_substack.render_reader` emitted footnotes sorted by *label*
  (numerics, then alphabetically) while the live post holds them in *reference* order — and
  the surgical patcher aligns footnote nodes **1:1 by index**. `In the Name` rendered
  footnote #0 as `John 10:3` against a live #0 that was the *shelucho shel adam* maxim.
  Thirty footnotes, thirty mismatched, and the only structural check was a count: 30 == 30,
  so it passed. Footnotes are now emitted in first-reference order, and `substack_repatch`
  carries a guard that detects a permutation.
- **Smart quotes.** `draft.md` is written with straight quotes; Substack curls them as the
  body is pasted. Nothing normalized this, so every quote-bearing block looked changed and a
  "one-word" re-sync would have rewritten the typography of an entire essay. The diff domain
  is now flattened (curly → straight, a length-preserving substitution so offsets stay
  valid), and any run actually inserted is smartened to match the document it lands in.

The lesson both share: **a guard that cannot see the failure it is named for is worse than
no guard**, because it reads as coverage. A count cannot see a permutation.
