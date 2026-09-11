---
name: tags
description: Tag the desk's pieces from their publication's controlled vocabulary, and find pieces by tag. Use when the user says "tag X with Y", "untag X", "what should X be tagged", "suggest tags for X", "tag the backlog", "which pieces are tagged Y", "what isn't tagged", or wants a new tag. Proposes tags only from the piece's own publication's vocabulary and asks before writing anything; a new tag is proposed as its own question and never added without a yes.
---

# Tags

A tag names what a piece is **about**, across books and collections — *practice* can name an
argued essay and a witness piece that sit in different reading orders. A tag list is only worth
having if one idea gets one tag with one label, so tags are a **controlled vocabulary**, and a
piece carries only tags from it.

**The vocabulary belongs to a publication, not to the desk.** Two audiences do not share a sense
of what a tag means. On a desk with a publication registry (`publishing/publications.yaml`, see
`docs/PUBLICATIONS.md`) each publication has its own list at `publishing/tags/<publication>.yaml`,
and a piece's tags are checked against **its** publication's list — the same id may mean
different things in two publications. A desk with no registry has one publication and one list,
`publishing/tags.yaml`, and nothing below asks which.

Everything goes through `framework/tools/tags.py`. It edits `publish.yaml` **as text** (those
files are heavily commented, and a YAML round-trip would strip every comment), and it refuses —
exit 3, nothing written — a tag the piece's vocabulary does not define, another publication's
tag, a `tags:` block edited by hand, or any write that would change another key.

```bash
python3 framework/tools/tags.py list [--publication P]      # each vocabulary, with counts
python3 framework/tools/tags.py show <slug>                 # its tags and its publication
python3 framework/tools/tags.py add <slug> <tag>...
python3 framework/tools/tags.py remove <slug> <tag>...
python3 framework/tools/tags.py find <tag> [--publication P]      # or: find --none
python3 framework/tools/tags.py check                       # every tag is in its vocabulary
python3 framework/tools/tags.py define <tag> --label "…" --about "…" --publication P
```

## Always do this first

1. `tags.py show <slug>` — which publication the piece belongs to. If it names none, stop: a tag
   means something only within a publication. Say which publication the piece looks like it
   belongs to (its outlets and its README's book and style say) and ask; on a yes,
   `publications.py assign <slug> <publication>` — never guess it silently.
2. `tags.py list --publication <it>`. Propose from **that** vocabulary **as it is on disk now**,
   never from memory, and never from another publication's list — it grows, and another session
   may have added to it an hour ago.
3. Read each tag's `about`. A tag means what its `about` says, not what its name suggests.

## The rules

- **Nothing is written without a yes.** A direct instruction that names the piece and a tag
  already in its publication's vocabulary ("tag in-vain with practice") *is* the yes. A
  suggestion is not; wait for it.
- **Never invent a tag, and never borrow one.** If the vocabulary has no tag for what a piece is
  about, say so and propose a new one **as a separate question**, naming the publication it is
  for: the id (lowercase, hyphenated — it becomes a URL), the label a reader sees, the one-line
  `about`, and which existing tag came closest and why it does not fit. That another publication
  has a tag for the idea is not a reason to use its id or its label here. `define` it only on a
  yes, and only then tag the piece with it. A tag that one piece would carry is usually a sign
  the idea is a word in that piece, not a theme across them.
- **Take the lease before writing to a piece**, and release it after:
  `python3 framework/tools/lease.py acquire <slug> --what "tagging"`. If another session holds it,
  stop and say who — do not `--force`. A vocabulary file is a shared singleton: `define` only
  appends, and says so rather than guessing if it cannot append cleanly.
- **Tags touch the manifest and nothing else.** Not the draft, the README, the dashboard, or the
  log — a tag is metadata, and the commit is its record.
- **Commit only when asked**, and then by path:
  `git commit -m "…" -- pieces/<slug>/publish.yaml publishing/tags/<publication>.yaml`. Never
  `git add` then a bare commit; the index is shared with other sessions.
- **Run `tags.py check` after any write.** It is the drift check, the way `check_refs.py` is for
  titles; the regression suite runs it too.

## Mode 1 — tag or untag a named piece

"Tag in-vain with practice", "take fear-of-god off the-towel". Resolve the piece (slug, or the
title from `publish.yaml`) and its publication, lease, `add` / `remove`, release, report the
piece's tags as they now stand. If the tag is not in the piece's vocabulary, the tool refuses —
go to the new-tag question above rather than picking the nearest existing tag on the user's
behalf.

## Mode 2 — suggest tags for a piece

"What should X be tagged?" Read enough to know what the piece is **about**, not what it is
titled:

- `publish.yaml` — title, subtitle, publication, current tags.
- `README.md` — the piece's argument in brief, its book and voice.
- `draft.md` — the body. A title is often a figure (*For the Love of Dogs* is about the fear of
  God); tag the subject, not the figure.

Propose **one to four** tags from its publication's vocabulary, each with one line saying why
*this piece* earns it — a sentence from the piece's argument, not a restatement of the tag's
`about`. Name a close tag you decided against when the call was close, so the author can overrule
you in one word. If something the piece is centrally about has no tag, raise it as the new-tag
question. Then **stop and wait.** Apply exactly what was approved — if the author strikes one,
the other three still go on.

## Mode 3 — tag the backlog

"Tag the backlog", "let's tag the rest". Work **one publication at a time** — its vocabulary is
the frame for every proposal in the run, so switching mid-run blurs it.
`tags.py find --none --publication P` lists its untagged pieces; without `--publication` it lists
every publication's, marked, plus pieces with no `publish.yaml` (those cannot carry tags; list
them and move on). Say how many there are and the order you will take them in — **published
pieces, oldest first**, unless the author picks another — then go **one piece at a time**:

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
`find --none`, with `--publication` when the question is about one. Report titles, not only
slugs, with the published date the tool prints. Across publications a shared id is a
coincidence of spelling, not one tag: report the results per publication.

## Where tags go from here

- **The sites.** `md_to_site.py` carries each tag and its label — from the piece's own
  publication's vocabulary — into the bundle, and **refuses** (exit 8) a tag that vocabulary does
  not define. A site reads the store by outlet, and every outlet belongs to one publication, so a
  site only ever shows its own publication's tags. Tagging a published piece changes nothing a
  reader sees until the next bundle export and store publish.
- **Substack.** `framework/tools/substack_tags.py pieces/<slug>` emits a script that puts the
  piece's tags on its Substack post, by label, from the endpoints the editor itself uses (measured
  2026-09-11 — the tool's docstring has them). **Run it on the publication's origin but never in
  that post's editor**: the dashboard (`/publish/home`) is right, and the script refuses the
  editor. It is additive — it creates only missing tags, attaches only missing ones, reports tags
  the desk does not list as `extra` and removes nothing — and it returns the post's tags read back.
  A vocabulary entry with `substack: false` (a membership tag) is never sent. **A live post is a
  public edit:** the tool refuses without `--live`, which is the author's word; afterwards
  `substack_tags.py pieces/<slug> --verify` reads the public post's tags and compares.
