# Namespaces — `pieces/` and `talks/`

The desk has two roots for texts:

```
pieces/<slug>/      a piece: draft.md + publish.yaml
talks/<slug>/       a talk:  draft.md + talk.yaml, with its deck, slides and assets
```

**A slug is unique within its namespace, not across the desk.** `love-is-not-a-metric-space`
names the essay in `pieces/` and the talk in `talks/`, and that is the design rather than a
collision to be worked around.

## Why a second root exists

A talk and the essay of the same argument **share a title**, and on this desk a slug follows its
title. One flat namespace therefore forces one of the two to answer to a name that is not its
own — and for eleven days that was the talk, still filed under `curse-of-dimensionality`, a title
it had lost on 2026-09-08. The README had to carry a line explaining that its address was not its
name, which is the convention this desk decided against.

The published side had already solved it: the store files a piece at `pieces/<slug>.json` and a
talk at `talks/<slug>/` (`talk_bundle.py`), a reader meets one at `/blog` and the other at
`/talks`, and the URLs never collided. The desk was the only place still flattening them.
(Eric, 2026-09-11: *"can it have the name love-is-not-a-metric-space and just be in the talks
directory?"*)

## The rules

- **`corpus.py` is the one place that knows.** `texts(root)` walks both; `find(root, ref, prefer=)`
  resolves a slug; `kind_of(dir)` reads the kind from the directory (a `talk.yaml`), never from the
  path. Tools that walk the corpus go through it rather than joining `'pieces'` themselves.
- **A bare slug prefers `pieces/`**, which is what every call site meant before there were two.
- **A companion pointer resolves by role**, which is what makes the shared slug legible: the
  essay's `companions: talk: love-is-not-a-metric-space` resolves into `talks/`, and the talk's
  `companion_of: love-is-not-a-metric-space` resolves back into `pieces/`.
- **The lease is not namespaced, deliberately.** `lease.py` keys on the slug, so an essay and its
  talk share one lease. They are one argument in two forms and are nearly always worked on
  together; a second lock would mostly be a way to hold half of it.
- **`rename_piece.py` renames pieces only.** A talk has no `publish.yaml`, no `former_slugs` and
  no outlet manifest, so none of that machinery applies; the tool now says so by name instead of
  reporting *no such piece* about a text that plainly exists.

## Moving a text between namespaces, by hand

Rare — and this is the whole procedure, in order:

1. `git mv pieces/<old> talks/<new>` (or the reverse).
2. `git mv DASHBOARD.d/<NNN>-<old>.md DASHBOARD.d/<NNN>-<new>.md`, keeping the number.
3. Sweep every cross-reference: the companion's `publish.yaml` pointer, both READMEs, `outline.md`
   and `notes.md` seam notes, any book index, and any path in a script's docstring.
   `grep -rn '<old>'` and read each hit. **`log/` and `corrections.md` stay** — they are
   append-only records of what was true when written.
4. **`dashboard.py render`, not `sync`.** `sync` ingests `DASHBOARD.md` first, so it will pull the
   old block back down into a *new* fragment and the text appears twice. Render from the
   fragments, then `dashboard.py check`. (This happened during the first such move; the duplicate
   is silent, because neither block is wrong on its face.)
5. Prove it: `companions.py check`, `check_refs.py`, `dashboard.py check`, and the suite.
6. The lease is keyed by slug — release under the old name before the move, re-acquire after.

**What never moves: a public URL.** The talk's page stayed at
`muffinlabs.ai/talks/love-is-not-a-metric-space` throughout, because the bundle already filed it
there. A desk-side move is not a publication event.
