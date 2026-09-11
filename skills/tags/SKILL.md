---
name: tags
description: Tag the desk's pieces from its controlled vocabulary, and find pieces by tag. Use when the user says "tag X with Y", "untag X", "what should X be tagged", "suggest tags for X", "tag the backlog", "which pieces are tagged Y", "what isn't tagged", or wants a new tag. Proposes tags only from the desk's one vocabulary list and asks before writing anything; a new tag is proposed as its own question and never added without a yes.
---

# Tags

A tag names what a piece is **about**, across books and collections — *practice* can name an
argued essay and a witness piece that sit in different reading orders. The desk keeps **one
vocabulary** (`publishing/tags.yaml` in the instance), and a piece carries only tags from it.
That is what makes a tag page worth having: one idea, one tag, one label, everywhere.

Everything goes through `framework/tools/tags.py`. It edits `publish.yaml` **as text** (those
files are heavily commented, and a YAML round-trip would strip every comment), and it refuses —
exit 3, nothing written — a tag the vocabulary does not define, a `tags:` block edited by hand,
or any write that would change another key.

```bash
python3 framework/tools/tags.py list                      # the vocabulary, with counts
python3 framework/tools/tags.py show <slug>
python3 framework/tools/tags.py add <slug> <tag>...
python3 framework/tools/tags.py remove <slug> <tag>...
python3 framework/tools/tags.py find <tag>                # or: find --none
python3 framework/tools/tags.py check                     # every tag is in the vocabulary
python3 framework/tools/tags.py define <tag> --label "…" --about "…"
```

## Always do this first

1. `tags.py list`. Propose from the vocabulary **as it is on disk now**, never from memory — it
   grows, and another session may have added to it an hour ago.
2. Read each tag's `about`. A tag means what its `about` says, not what its name suggests.

## The rules

- **Nothing is written without a yes.** A direct instruction that names the piece and a tag that
  already exists ("tag in-vain with practice") *is* the yes. A suggestion is not; wait for it.
- **Never invent a tag.** If the vocabulary has no tag for what a piece is about, say so and
  propose a new one **as a separate question**: the id (lowercase, hyphenated — it becomes a URL),
  the label a reader sees, the one-line `about`, and which existing tag came closest and why it
  does not fit. `define` it only on a yes, and only then tag the piece with it. A tag that one
  piece would carry is usually a sign the idea is a word in that piece, not a theme across them.
- **Take the lease before writing to a piece**, and release it after:
  `python3 framework/tools/lease.py acquire <slug> --what "tagging"`. If another session holds it,
  stop and say who — do not `--force`. `publishing/tags.yaml` is a shared singleton: `define`
  only appends, and says so rather than guessing if it cannot append cleanly.
- **Tags touch the manifest and nothing else.** Not the draft, the README, the dashboard, or the
  log — a tag is metadata, and the commit is its record.
- **Commit only when asked**, and then by path:
  `git commit -m "…" -- pieces/<slug>/publish.yaml publishing/tags.yaml`. Never `git add` then a
  bare commit; the index is shared with other sessions.
- **Run `tags.py check` after any write.** It is the drift check, the way `check_refs.py` is for
  titles; the regression suite runs it too.

## Mode 1 — tag or untag a named piece

"Tag in-vain with practice", "take fear-of-god off the-towel". Resolve the piece (slug, or the
title from `publish.yaml`), lease, `add` / `remove`, release, report the piece's tags as they now
stand. If the tag is not in the vocabulary, the tool refuses — go to the new-tag question above
rather than picking the nearest existing tag on the user's behalf.

## Mode 2 — suggest tags for a piece

"What should X be tagged?" Read enough to know what the piece is **about**, not what it is
titled:

- `publish.yaml` — title, subtitle, current tags.
- `README.md` — the piece's argument in brief, its book and voice.
- `draft.md` — the body. A title is often a figure (*For the Love of Dogs* is about the fear of
  God); tag the subject, not the figure.

Propose **one to four** tags, each with one line saying why *this piece* earns it — a sentence
from the piece's argument, not a restatement of the tag's `about`. Name a close tag you decided
against when the call was close, so the author can overrule you in one word. If something the
piece is centrally about has no tag, raise it as the new-tag question. Then **stop and wait.**
Apply exactly what was approved — if the author strikes one, the other three still go on.

## Mode 3 — tag the backlog

"Tag the backlog", "let's tag the rest". `tags.py find --none` lists the untagged pieces (and,
separately, pieces with no `publish.yaml` — those cannot carry tags; list them and move on).
Say how many there are and the order you will take them in — **published pieces, oldest first**,
unless the author picks another — then go **one piece at a time**:

1. lease the piece;
2. propose, exactly as in Mode 2;
3. wait for the answer, apply it, release the lease;
4. report `N of M done` and move to the next.

A yes covers the piece it answered and no other; never batch-apply proposals for several pieces
on one approval. Keep the new-tag questions honest across the run: when the same missing idea
comes up a second time, that is the moment to propose the tag, and the earlier piece can be
revisited once it exists. Stop whenever the author says so; `find --none` is the bookmark, so a
backlog run can resume in another session.

## Mode 4 — find by tag

"Which pieces are tagged practice?", "what isn't tagged?" — `tags.py find <tag>` or
`find --none`. Report titles, not only slugs, with the published date the tool prints. A tag that
is not in the vocabulary is worth saying so about; `check` explains it.

## Where tags go from here

- **The site.** `md_to_site.py` carries each tag and its label into the bundle, and **refuses**
  (exit 8) a tag the vocabulary does not define; the store's index carries them to the sites.
  Tagging a published piece changes nothing a reader sees until the next bundle export and store
  publish.
- **Substack.** Not automated. Substack has no write API, so post tags are set in the editor, and
  a live post is a public edit — see the `publish` skill before touching one.
