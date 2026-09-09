---
name: draft
description: Start or continue a piece in a chosen style. Use when the user says "draft this", "write the next section", "keep going on <piece>", "put this in my voice", or hands you notes/an outline to turn into prose. Loads the piece's target style as steering (style.md + config.yaml + exemplars) and writes into the piece's draft.md. Drafts are cheap and disposable; it never edits the style constitution.
---

# Draft

Turn intent into prose, steered by a style. Drafting is the fast, cheap half of
the loop — write freely, revise later, let git remember old versions.

## Always do this first

1. Identify the **piece** and its **target style** from `pieces/<name>/README.md`
   (the `Style:` line). If the piece or style is ambiguous, ask — don't guess a
   voice.
1a. **When the piece is NEW, settle its outlets before drafting, and confirm them with
   the author.** A piece declares where it will be published in `publish.yaml`:

   ```yaml
   outlets:
     - substack
     - <other outlet>
   ```

   **Never select an outlet silently, and never leave the list empty.** Read the
   instance's outlet registry (`publishing/outlets.md`), **propose** a set with a
   one-line reason, and get an explicit yes — the same way a target style is settled.
   Where a piece goes is an editorial decision about audience, not a deployment
   detail, and the author is the one who makes it.

   *Why this is here rather than in `publish`:* a piece that reaches the publish step
   without a declared destination has already been written for nobody in particular,
   and the pressure at that point is to pick the obvious one and move on. The desk did
   exactly that — it published to a single outlet for weeks while a second live host
   sat unfed, because nothing had ever asked. `publish` now **refuses** a manifest with
   no `outlets:` rather than defaulting, so the question cannot be skipped; this step
   is where it gets answered while it is still cheap. (Eric, 2026-09-09: *"the skill for
   creating a piece should define which outlets it will go to and confirm with the user.
   we should not silently select one."*)
2. Load the style as steering, in this order:
   - `styles/<style>/style.md` — the constitution (voice, do/don't).
   - `styles/<style>/config.yaml` — mechanical knobs. Honor them literally
     (formality, sentence length, person, contractions, the `avoid` list).
   - `styles/<style>/exemplars/` — match the *texture* of these passages.
3. Read the piece's `outline.md` and `notes.md`, and the book's `facts.md` (the
   witness/anchor ledger), if they exist. Draft the outline's spine, not whatever
   comes to mind.

## Drafting

- Write into `pieces/<name>/draft.md`. Keep **one** current draft there; prior
  versions live in git history, not stacked in the file.
- Steer, don't parrot: the exemplars set texture and the constitution sets rules;
  the content is the piece's own.
- If the style and the piece's needs genuinely conflict, surface it and ask —
  don't silently override the style or the user's intent.
- Offer the draft (or the new section) for reaction. Drafts are disposable; say so.

## After a drafting session

0. Run `python3 framework/tools/check_pronouns.py pieces/<name> --names <named figures>` on what
   you just wrote and repair before logging: restructure any sentence-initial forced capital, make
   every invented person *they/them*, capitalize every oblique reference to God (*the One*,
   *Someone*) and keep God a *who*. Inside a scripture quotation, read sections E and F: a
   capitalized *He / Him / His* there says *the Son* — for the Father it is a bracketed *[Them]*
   (verb bracketed too where agreement needs it) — and the Son's own *me / my / mine* take the
   capital. Justify each remaining hit by naming its referent. (Added 2026-09-03 — see the
   constitution's pronoun section and `corrections.md`; E and F added 2026-09-07 after *False
   Light* carried four such misses.)
1. Append a dated entry to `pieces/<name>/log/<current-month>.md` — what you
   drafted, decisions, open threads. Append-only, newest at the bottom.
2. Update `pieces/<name>/README.md` — the `Stage:` and `Next move:` lines.
3. Refresh the piece's block in `DASHBOARD.md`.

## Boundaries

- Don't touch `styles/<style>/style.md` or `config.yaml`. Wording feedback goes
  to `corrections.md` (that's `critique`/`tune-style` territory), never a live
  edit of the constitution.
- Don't publish or send anything. Producing a draft is the whole job here.
- **Render only the witness that's in the ledger.** Every concrete detail about a
  real person or animal — a behavior, a feeling, an event, a timespan — must trace
  to a fact in the book's `facts.md`. If a vivid specific would help but isn't in
  the ledger, write a `[bracket]` for the author to fill; never invent it. The
  machine renders; it does not live.
  - **The rule reaches anything checkable, not only people and animals.** A product
    and its interface, a place, an institution, a date, a price — if a reader could
    verify it in five seconds, it is witness and not scenery. Treat it like a
    quotation: get it from the ledger or from the author, or leave a `[bracket]`.
    Inventing plausible detail about a real thing is the same fault as inventing it
    about a real person, and it is easier to commit because the thing has no
    feelings to bruise.
  - **The check is weakest exactly where the prose is strongest.** An invented
    specific arrives wearing the same clothes as a well-chosen one, and the pressure
    to supply one peaks in an opening, a close, and any passage being rewritten to
    fix an earlier invention. Run the ledger check hardest on the lines you are
    proudest of.
