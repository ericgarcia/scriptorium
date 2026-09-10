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
| **Findings** | `findings` | The review's proposed changes, ranked, each linking to the line it lands on. |
| **Calls** | `calls` | *Every open question listed as a call*, in the flag color, above the fold. This band is the reason the page exists. |
| **Contents** | headings | Movement numbers with per-movement word counts — where the piece is heavy or thin, at a glance. |
| **The piece** | `draft.md` | Sticky movement rail, 66ch column, working footnote jumps both ways. **Each finding's span is marked in place, showing the PROPOSED wording, and its note hangs under that paragraph** — so the prose reads as the revised piece and a change is judged next to the sentence it changes. |
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
  "calls": [["Short title", "One or two sentences (HTML ok)."]],
  "findings": [
    { "severity": "fidelity",
      "anchor": "It asks nothing for Itself",
      "now": "It asks — nothing — for Itself",
      "title": "§II drops the source's dashes from a sentence §I quotes with them",
      "what": "The book reads <em>It asks—nothing—for Itself</em>. (HTML ok.)",
      "evidence": "<em>Unveiled Mysteries</em>, p. 25, read in the PDF today." }
  ] }
```

## Findings — a proposed change, marked where it lands

A review that lists its findings somewhere else asks the author to hold a sentence in
their head while they go and look at another one. So a finding names the span it is
about, and the page **highlights that exact span in the prose and puts the note under
that paragraph.** The severity colours the mark: `fidelity` and `open` in the flag
colour, `argument` in the accent, `voice` a hairline. Findings are numbered in the
order given — **rank them**, because that ranking is the first thing read.

`anchor` is **verbatim `draft.md`**, markdown and all, matched against the
whitespace-normalised block, so line wraps do not matter and `*asterisks*` do. It may
land in a footnote as easily as in the body. `evidence` says what the finding was
checked against, so the author does not have to re-derive it.

### The mark shows the proposal, not the present

Where a finding carries `now`, **the marked span renders the replacement.** Reading the
highlighted prose is then reading the piece *as it would be if every change were taken*
— which is the thing the author is actually deciding about. A page that highlights the
old wording asks them to do the substitution in their head, sentence by sentence, which
is the work the page exists to save. (Eric, 2026-09-10: *"this should show what we are
changing it **to** and not what we are changing it **from** in the inline view."*)

So **`now` must be an exact replacement for `anchor`** — the same span, rewritten — and
the two render as a `was`/`now` pair in the card, **verbatim in mono**, which is the only
way a change of punctuation or case is legible at all (a dropped em dash is invisible in
prose type).

**`was` is not an input.** It is the anchored text itself, derived. Supplying it is
refused, because two hand-typed strings can disagree with the span they claim to
describe and nothing would catch it.

### Every finding proposes a change

`now` is **required**, and a `now` identical to its anchor is refused. A band titled
*proposed changes* whose rows propose nothing is lying about what it is — and a
diagnosis the author has to turn into a rewrite themselves has left the hard half
undone. **If you can name what is wrong but cannot write the replacement, the finding
is a question, and questions go in `calls`.** That is the whole difference between the
two bands. (Eric, 2026-09-10, on a finding that diagnosed a real fault and stopped:
*"this doesn't tell me what the proposed change is. it should."*)

**A deletion is a replacement of a wider span**, not an empty `now` — anchor the text
that survives along with the text that goes, and let `now` be what remains. An empty
`now` is refused: it would render an invisible mark.

**The stamp says so.** Once any mark shows a replacement the page is no longer a faithful
rendering of `draft.md`, so the stamp gains *prose shows N proposed changes*. Every one is
highlighted and numbered, so nothing is edited silently — but an author must never have to
wonder whether they are reading the draft or the proposal.

### The anchor is not allowed to miss

An anchor that matches **nothing**, matches **more than one place**, or **overlaps**
another finding's anchor **exits 3, names the finding, and writes no file.**

This is the one refusal the page cannot do without. Every other failure mode is
visible: a missing hero renders a marked slot, a broken footnote exits 2. But a
finding that silently failed to highlight leaves a page that **looks complete and is
not**, and the author reads it believing they have seen everything the review found.
Lengthen the anchor until it is unique. (Eric, 2026-09-10: *"when reviewing we should
open as an artifact highlighting the suggested changes."*)

## Applying it

```
python3 framework/tools/review_artifact.py <piece_dir> --apply
```

Writes every finding's `now` into `draft.md`. **This is the reason the contract is strict:** because
`now` is an exact replacement for `anchor`, applying a review is a substitution and never a
retyping — so what the author approved on the page and what lands in the file are the same string.
Ten spans re-keyed by hand, one of them a King James verse recased in four places, is exactly where
a slip becomes an edit nobody can see.

**Nothing is written unless every finding lands**; a half-applied review leaves the draft in a state
nobody chose. Anchors are matched across the file's own line wraps, only the changed blocks are
re-flowed (footnotes keep their four-space continuations, blockquotes their `>`), and a markdown
link is never broken across lines.

**Afterwards the review is spent.** Every anchor is gone from `draft.md` by construction, so
re-rendering the same findings exits 3 — which is the staleness guard doing its job, not a fault.
Move them under another key as the record and re-review the new draft.

## It refuses rather than renders wrong

A footnote marker with no definition, or a definition never referenced, **exits 2 and names
the key**. An anchor that does not land **exits 3** (above). Both are invisible in a
hand-built page and both mislead an author about what they are reading.

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
