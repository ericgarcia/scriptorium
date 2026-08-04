---
name: tune-style
description: The gated pass that folds accumulated corrections into a style's constitution. Use when the user says "tune my style", "update the style", "the corrections have piled up", or after a stretch of drafting/critique on one voice. Reads styles/<name>/corrections.md, proposes distilling recurring feedback into style.md or config.yaml one change at a time, each backed by corrections you can point to. Deliberate and slow — never rewrites the constitution mid-draft.
---

# Tune style

Styles change slowly and on purpose. Drafting is fast and disposable; the
constitution is load-bearing. This pass is the *only* place `style.md` and
`config.yaml` get amended — deliberately, with evidence, one change at a time.

## When to run it

Not mid-draft. Run it when corrections have accumulated — after several drafting
or critique sessions on the same voice — or when the user explicitly asks. If
`corrections.md` has only a few one-off entries, say so and stop; there's nothing
to distill yet.

## The pass

1. Read `styles/<name>/corrections.md` end to end. Read the current `style.md` and
   `config.yaml`.
2. Look for **patterns** — the same kind of correction recurring. One-off fixes
   stay as history; a pattern is a candidate amendment. Name each candidate with
   the corrections that support it: "three entries cut inflated verbs → add
   `utilize/leverage/facilitate` to the `avoid` list."
3. Propose amendments **one at a time**, each as a specific edit (a new do/don't
   line, a changed knob), with its evidence. Let the user accept, reject, or
   reword each. Never batch-rewrite the constitution.
4. Apply only accepted changes to `style.md` / `config.yaml`.

## Discipline

- **Evidence or it doesn't go in.** Every amendment points to corrections, not a
  hunch about good writing.
- **One cell at a time.** Small, reversible edits keep the voice stable enough to
  trust and honest about why it says what it says.
- **`corrections.md` is append-only.** Distilling a pattern doesn't delete the
  entries that justified it — they stay as the record.
- Keep `style.md` a page that's *followed*, not an encyclopedia. Prefer replacing
  a vague line with a sharper one over piling on new ones.

## After the pass

Note what was amended (and what was deferred) in the piece or style log if the
instance keeps one. The corrections that fed an amendment stay where they are.
