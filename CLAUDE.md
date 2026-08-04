# Writing desk — behavior

A markdown-native writing desk run through Claude Code. This framework lives in
`framework/` (a git submodule). Your writing lives in `pieces/` and your tuned
voices in `styles/`, in your instance repo. Copy this file to your instance root
and adjust it.

## The loop

- `DASHBOARD.md` is the top of the desk — one block per piece in flight.
- Each `pieces/<name>/README.md` holds that piece's stage, target style, and the
  single next move.
- Detail lives in `pieces/<name>/outline.md`, `draft.md`, `notes.md`, and
  `log/`.

When asked "what's on the desk," read the dashboard, drill into the live piece
README, and propose one concrete next move. After a writing session, log it
(dated, append-only), update the piece README, and refresh the dashboard block.
The `whats-on-the-desk` skill has the details.

## Styles steer; they don't get trained into a model

A style is structured context that steers a draft — never model weights.

- **Pick a style before drafting.** Every piece names a target style in its
  README. `draft` loads that style's `style.md`, `config.yaml`, and `exemplars/`
  as steering.
- **Corrections are append-only.** When you change Claude's wording, the *why*
  goes in `styles/<name>/corrections.md`. Never edit a past correction.
- **The constitution changes only during a `tune-style` pass.** Don't rewrite
  `style.md` mid-draft. Accumulate corrections, then distill them deliberately —
  one change at a time — the way a rule is amended, not patched.

## Principles

- **Logs are append-only.** Never edit a past writing-log entry — a log you can
  revise isn't evidence of what you actually wrote.
- **The README is truth; the dashboard is a summary.** If they disagree,
  reconcile rather than guess.
- **Draft freely; tune deliberately.** Drafts are cheap and disposable. The
  style constitution is load-bearing and changes slowly.
- **Add structure only when it's used.** A new skill, style, or template earns
  its place by being used, not by being anticipated.
- **The scaffold holds the reasoning; the prose carries only the result.** When a
  correction lands, regenerate the prose to be simply *right* — never write a
  defense of the change into the draft. The reader never saw the earlier version; a
  clause arguing against it ("but that was never really about X") only shows the
  seams of the process. Corrections, facts, and notes stay in the scaffold; the
  draft reads as if it had always been correct.
