---
name: continuity-audit
description: Read-only sweep for continuity drift and real-world/legal exposure across a book. Use when the user says "continuity check", "does the timeline hold", "check ages/dates", "do a legal pass", or before a draft is called done. Flags timeline and age contradictions, fact drift against the ledger, and real people/teams/brands/works that need fictionalizing. Reports a fix list; it does not edit.
---

# Continuity audit

Two jobs, both read-only: keep the book's facts consistent with themselves, and keep
it clear of real-world/legal exposure. Reports; the author (or `chapter-draft`)
applies fixes.

## Always do this first

1. Read `outline/characters.md` (ages, birthdates, looks) and any timeline files
   (e.g. `outline/*timeline*.md`), plus the README's continuity notes.
2. Read the chapters in scope (a chapter, an act, or the whole book). Build a small
   internal ledger of every dated/aged/named fact as you read.

## 1. Continuity

- **Ages & birthdates.** Flag every place a character's stated age contradicts their
  birthdate or an earlier chapter (a character stated as 16 in one scene, 17 in the next).
  Compute from
  the birthdate in `characters.md`; the sheet is the source of truth.
- **Timeline.** Flag contradictions in dates, seasons, elapsed spans, and event order
  ("4 years… they won in 2023" vs. a later date that implies 5–6; "Day 4… still
  December" after a Dec 29 start; a play that is 40 s in one chapter and 3 s in the
  next). Note where the book anchors to a real year so hard it will date badly.
- **Fact drift.** Flag details that mutate across chapters (a couple's kids counted as
  4 then 3; a restaurant/brand name that changes; a physical detail that shifts) and
  anything a chapter states that an earlier one contradicts.
- **Reference integrity** (interactive medium): flag songs/works/links referenced but
  missing from the book's reference index, or links that point nowhere.

## 2. Real-world / legal

- **Real people & organizations.** Flag every real person, team, coach, league,
  company, show, or branded work used as itself — especially any shown in a damaging
  light (a real athlete dropping a decisive catch; a real figure fictionalized into a
  crime; real children of a real person). These are libel/right-of-publicity exposure.
  Recommend a **fictional** name + light detail change that keeps the resonance and
  loses the identification (change the team, gloss the score, invent the coach).
- **Named real venues / consumer works.** Flag real hotels, restaurants, and named IP
  (e.g. a specific children's show) used directly; recommend fictionalizing or letting
  the reader infer without the name.
- **Consistency of the fictionalization.** Once a real thing is renamed, flag any
  later chapter that reverts to the real name.

Keep the book's own deliberate real references (public song links, real place-names
the author chose to keep) out of scope unless they create exposure — note them, don't
force them.

## Output

Two lists — **Continuity** and **Legal** — each a table of `location (chapter:line) ·
the problem · the fix`. Then a short **Summary**: the count of each, the highest-risk
legal items first, and any single fix that resolves several. **Make no edits**; where
the fix implies a ledger change (e.g. lock a birthdate, adopt a fictional team name),
recommend adding it to `characters.md` / the continuity ledger so later chapters honor it.
