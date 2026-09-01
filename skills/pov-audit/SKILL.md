---
name: pov-audit
description: Read-only audit of two POV chapters covering the same event — does the second POV ADD, or just re-narrate? Use when the user says "pov audit", "do these two chapters earn their doubling", "check the alternating POV", or after a second POV of a shared event is drafted. Checks perceptual tension, dramatic irony, ambiguity, motif evolution, and emotional rhythm across the pair; flags pure re-narration. Especially load-bearing in an alternating-POV novel, where a replayed event drags the pace. Reports; does not rewrite.
---

# POV audit

The gate for a book that tells one event from more than one POV. The failure it
exists to catch: **two cameras on the same event** — a second chapter that re-tells
what the reader already had, dragging the pace and raising "why are we here again?"
The pass: **two fundamentally different ways of experiencing the same reality**, so
holding both, the reader sees a third thing neither character can.

In a linear novel this is load-bearing for pace: a second POV that only replays what the
reader already has drags the whole book, so each must pay its way.

## Always do this first

1. Read both POV chapters (`book/<a>.md`, `book/<b>.md`) that cover the shared event.
2. Read the book's philosophy/thesis file and `CLAUDE.md` (motifs, the reason the book
   alternates POV at all).

## The criteria

1. **Perceptual tension / ironic gap.** Do the two POVs *disagree about what happened*
   — read the same gesture, line, or silence as different things? Is there a third
   truth neither sees? If they agree on everything, the pair is failing — flag it.

2. **Dramatic irony.** What does the reader now know that A doesn't? That B doesn't?
   Has the gap between reader-knowledge and character-knowledge widened? List the
   specific moments the reader sees past the characters.

3. **What the second layer ADDS.** State, in one line, the new revelation / tension /
   decision the second POV delivers that the first could not. **If you can't, the
   layer is re-narration** — flag it to cut, compress into memory/reflection inside a
   forward-moving scene, or re-aim.

4. **Ambiguity preserved.** Can a careful reader take A's side? B's? Is either made
   plainly right/wrong? The pair should resist collapsing into one correct reading.

5. **Motif evolution.** Do shared images/words/gestures recur across the pair and
   *transform* (literal → figurative, funny → painful, background → foreground) rather
   than repeat identically? Note echoes and what the *difference* reveals.

6. **Emotional rhythm.** Name each layer's dominant texture. Do they complement or
   duplicate? A pair should breathe (comedy/weight, tension/release, intimacy/distance)
   — at least one tonal shift between them.

7. **Same words, different worlds.** Where the two layers repeat a phrase/sentence
   verbatim to show two minds landing alike, ask whether it reads as resonance or as
   repetition. If the two are truly different people, they'd rarely reach for the same
   words — flag verbatim echoes that flatten rather than rhyme.

## Output

`Pair: <A> ↔ <B>` with POV of each, then per criterion a rating (STRONG / ADEQUATE /
WEAK) and specific moments/lines. Then a **Summary**: strongest dimension, weakest
dimension, and the top 3 actionable revisions — foremost, **whether the second layer
earns its place** or should be cut/compressed. **Make no edits.**
