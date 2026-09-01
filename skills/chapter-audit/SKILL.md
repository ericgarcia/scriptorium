---
name: chapter-audit
description: Read-only craft audit of one book chapter against the book's review criteria. Use when the user says "audit this chapter", "is this chapter working", "check X against the criteria", or before a chapter is called done. Goes section by section on POV discipline, sensory grounding, show-not-tell, emotional depth, agency (GMC), metaphor openness, and voice — flagging specific lines. Reports and suggests fixes; it does not rewrite.
---

# Chapter audit

The quality gate for a single chapter. Read-only: it finds and reports, section by
section; it does not edit. (For the POV-*pair* check across two chapters covering one
event, use `pov-audit`. To rewrite from findings, go back to `chapter-draft`.)

## Always do this first

1. Read the chapter `book/<n>.md`. Identify the POV character (header / context).
2. Read `outline/characters.md` (looks + dialogue voice), the book's `CLAUDE.md`
   (the criteria and any conventions), and the POV's `gmc/` sheet.

Use `---` breaks or natural scene shifts as section boundaries. Audit each section
against every criterion below.

## The criteria

1. **POV discipline (strict third limited, unless the book says otherwise).** Flag
   every line inside another character's head (their thoughts, feelings, memories,
   decisions as *fact*). Inference framed as the POV's read ("he suspected", "she had
   to know", "you could see it on her face") is fine. Stating what others feel/decide
   is a violation. Also flag omniscient zoom-outs and future knowledge the POV lacks.

2. **Sensory grounding.** Is the reader physically in the space — sight, sound, smell,
   texture, temperature; bodies in space (where people are, hands, posture, movement);
   setting *evoked*, not just named? Rate STRONG / ADEQUATE / WEAK, cite weak spots.

3. **Show, not tell.** Flag lines that *tell* an emotion or trait instead of showing
   it through action, detail, or dialogue. "She was sad" vs. "she didn't speak for
   twenty miles." Abstractions without grounding are telling. **Prefer external action
   and dialogue over interior monologue** — flag stretches where the POV *thinks* a
   feeling the scene could have *shown*. Rate STRONG / ADEQUATE / WEAK.

4. **Emotional depth.** At least one moment that hooks feeling, not just intellect; the
   emotion arising from the situation, not from being told; the gap between what a
   character says and what they feel doing the work. Rate STRONG / ADEQUATE / WEAK.

5. **Agency / GMC.** Does the POV character *want* something in this scene and *act*,
   or does life merely happen to them? Passivity is allowed only when the notes make it
   a deliberate, motivated choice. Flag scenes where nobody wants anything and nothing
   collides.

6. **Metaphor openness.** Vary the *degree* to which figures pin their meaning —
   closed ("time is a thief"), half-open ("silence like an unplowed field"), fully
   open ("the rusty scaffold of her goodbye"). Flag runs where every figure hits the
   same half-open note, and any 1:1 metaphor that closes
   off ambiguity the scene wants to keep.

7. **Voice.** Does the POV's internal voice and each speaker's dialogue match
   `outline/characters.md`? Flag slips into another character's register.

8. **Book conventions.** Whatever the book's `CLAUDE.md` sets (e.g. a recurring-bit
   rule, a motif system, a pronoun/casing convention) — flag violations by name.

## Output

Per section: `POV violations` (list or none) · `Sensory` (rating + weak lines) ·
`Show-not-tell` (flagged telling lines) · `Emotional` (rating) · `Agency` (does
someone want/act? — or flag) · `Metaphor` (flag same-note runs) · `Voice` (OK/slip) ·
`Conventions` (OK/violation).

Then a **Summary**: total POV violations; sections needing sensory / emotional /
agency work; and a numbered list of specific, actionable fixes for the author to
approve. **Make no edits.**
