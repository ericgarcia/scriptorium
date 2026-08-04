---
name: critique
description: Review a draft against its target style and give concrete, actionable feedback. Use when the user says "critique this", "how's this draft", "does this sound like my voice", "edit this", or wants a read before calling a piece done. Reads the draft and the style, names specific lines that stray, and — when the user accepts a wording change — records the why in the style's corrections.md. Does not rewrite the whole piece unless asked.
---

# Critique

The quality half of the loop. Read a draft against the voice it's meant to have,
and say — concretely — where it lands and where it strays.

## Always do this first

1. Read the draft (`pieces/<name>/draft.md`) and the piece's `README.md` for its
   target style.
2. Load `styles/<style>/style.md`, `config.yaml`, and a sampling of `exemplars/`
   — the same steering `draft` uses. You're checking the draft against *this*
   voice, not against generic "good writing".

## Giving feedback

- Be concrete and located: quote the line, name what's off (which principle or
  which `avoid` item), propose a specific fix. "Weak" is not feedback; "this
  opens with a rhetorical question, which the style rules out — try leading with
  the claim" is.
- Separate **style** misses (voice, constitution, config) from **substance**
  issues (logic, structure, gaps). Both matter; label which is which.
- Prioritize. Lead with the few changes that matter most, not an exhaustive
  line-edit, unless a full line-edit is what was asked.
- Don't grade with adjectives-as-verdict. Report what's there and what a fix
  would be; the call to accept is the user's.

## When a wording change is accepted

If the user takes a change that reflects the *voice* (not a one-off fix), capture
it so the style can learn:

1. Append to `styles/<style>/corrections.md`, under today's date:
   `- Changed "X" → "Y". <why, in terms of the voice>`. Append-only.
2. Don't touch `style.md` or `config.yaml` here — corrections accumulate; the
   gated `tune-style` pass is what folds them into the constitution.

## After the session

Log the review in the piece's `log/`, update the piece `README.md` stage/next
move if it changed, and refresh the `DASHBOARD.md` block.
