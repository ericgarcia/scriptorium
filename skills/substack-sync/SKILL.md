---
name: substack-sync
description: Two-way sync between a piece's draft.md and its already-live Substack post, with conflict detection. Use when the user says "sync X", "re-sync X", "pull my Substack edits back", "the live post is behind", "update the published post", or wants a live post and its draft brought back into agreement. Classifies every block three ways against a stored baseline — push (draft moved), pull (Substack moved), conflict (both moved) — pulls Substack-side edits into draft.md, then stages the push. Only a human clicks Continue/Update.
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
6. **Hand off.** Staging lights up **Continue**. The human reviews the diff and clicks
   **Continue → Publish**, choosing **not** to resend email. **Never click it.**
7. **Seal.** Re-run *scan*, then
   `python3 framework/tools/substack_sync.py seal pieces/<name> live-after.json`
   It refuses unless draft and live now agree, and records the new baseline. **Do not skip
   this** — an unsealed sync leaves the next one unable to tell which side moved.

## First run (a piece published before sync existed)

`plan` refuses without a baseline, because it would have to guess. Seed one:

- `seed pieces/<name> --from-git <rev>` — render `draft.md` as it stood at the commit the
  piece was composed from. This is the honest one: that text **is** what was pushed. Find
  the rev with `git log --oneline -- pieces/<name>/draft.md`.
- `seed pieces/<name> --from-draft` — assert the draft is what is live.
- `seed pieces/<name> --from-live live.json` — assert the live post is authoritative.

Prefer `--from-git`. The other two are assertions, and if the assertion is wrong the first
sync will push or pull something nobody asked for.

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

- **Never click Publish / Continue / Update / Send.** The skill stages; a human ships. This
  holds doubly here: the target is a **live, public** post.
- **Conflicts stop the run.** Do not pick a side. Show the user both versions and let them
  choose.
- **Structural divergence is not auto-merged.** A block added, removed or reordered on
  either side is described and left alone. A live essay is not the place to guess at a
  paragraph.
- **Never pass a flag to force past a refusal.** The refusals here exist because each one
  has already been the failure mode once.
- **Seal every completed sync.** The baseline is the whole mechanism.
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
