# The review artifact

The surface an author reads when they are asked to judge a piece.

`draft.md` is not that surface. It carries a scaffold header, `[^slug]` markers, raw
markdown and line wraps the author has to read past. Chat is not that surface either —
review facts posted into a conversation scroll away, and the one thing an author needs to
see (*what is still mine to decide?*) is the first thing lost.

**One generator, one page: `python3 framework/tools/review_artifact.py <piece_dir>`.**

## Why it is a tool and not a paragraph of instruction

Two sessions built this page by hand on 2026-09-09 and 2026-09-10 and produced **two
different formats** — different type pairs, different palettes, one with a contents list and
per-movement word counts and a provenance stamp, the other with gate chips and a tighter
measure. Both were defensible, which is exactly the problem: a format argued fresh each time
drifts, and the author has to re-learn the page every time they open one. (Eric, 2026-09-10:
*"can we formalize the format by which we review pieces in artifacts."*)

**The prose is parsed out of `draft.md` and never retyped** — the same rule the composer
obeys against Substack, for the same reason: a transcription slip becomes an edit nobody can
see.

## What the page shows, in order

| Band | Comes from | Why it is there |
|---|---|---|
| **Stamp** | `version`, `state`, `date` | The live truth, above the title: *not composed*, *Substack holds v1*. An author must never have to ask whether what they are reading has shipped. |
| **Title + subtitle** | `publish.yaml` | As a reader will meet them, not as the file spells them. |
| **Hero + provenance** | `assets/hero.*` | Downscaled to 1400px and embedded. The provenance stamp says **generated** or photograph — load-bearing where a photorealistic image could re-attach a biographical reading the prose dropped. No image yet renders a marked **slot**, because a slot is a decision waiting and a picked image is a decision taken. |
| **Review strip** | counted + `prior` | Body words, movements, footnotes, each with the delta against the previous version. Counted from the file, never asserted. |
| **Gates** | `gates` | Which checks ran and what they said. |
| **Calls** | `calls` | *Every open question listed as a call*, in the flag color, above the fold. This band is the reason the page exists. |
| **Contents** | headings | Movement numbers with per-movement word counts — where the piece is heavy or thin, at a glance. |
| **The piece** | `draft.md` | Sticky movement rail, 66ch column, working footnote jumps both ways. |
| **Notes** | `[^slug]:` | Real numbered notes, back-linked. |

## Facts

Everything about the *piece* is read from the piece. Everything about the *review* comes from
`pieces/<slug>/review.json` (or `--facts`). All keys optional; with no facts file the page
still renders and the strip reports what can be counted.

```json
{ "version": "Draft v3 — the hollow flute",
  "state": ["not composed", "Substack holds v1"],
  "date": "rev. 2026-09-10",
  "prior": {"words": 3072, "movements": 8, "notes": 11},
  "gates": [["check_links", "8 live, 0 dead"]],
  "cover": {"caption": "…", "provenance": "Generated, not a photograph"},
  "calls": [["Short title", "One or two sentences (HTML ok)."]] }
```

## It refuses rather than renders wrong

A footnote marker with no definition, or a definition never referenced, **exits 2 and names
the key**. Both are invisible in a hand-built page and both mislead an author about what they
are reading.

## Word counts

`Body words` counts the prose only — headings and the hero's alt text are excluded. That is a
narrower number than a `wc -w` of the file and it is the one the strip and the contents list
both use, so deltas between versions compare like with like.

## Naming it

**The artifact is named by the piece's title, exactly — no prefix, no label, no version.** The
generator sets `<title>` from `publish.yaml`, so this is not a thing to remember; it is a thing that
cannot go wrong. The reason it matters: the gallery is a shelf of pieces, and a reader picks one out
by its name. A prefix pushes the identifying half of the title out of view and puts a word in front
that could sit on any page — which is precisely the failure a name is supposed to avoid. (Eric,
2026-09-10: *"i dont want 'The Galley' prefixes."*) The state — *galley proof*, *v2*, *not composed*
— belongs in the stamp, where it is read once and never mistaken for the work's name.

## Publishing it

The tool writes HTML; the **Artifact** tool publishes it. Keep one artifact per piece and
republish to the same URL as versions land — the author's link should not change under them.
