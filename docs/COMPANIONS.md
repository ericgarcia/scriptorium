# Companions, forms, and voices

A **piece** is one main text, `draft.md`. It may carry **companions**: other texts that go out
with it — the poem posted as its Substack Note, the talk of the same argument. Each companion is
written in its own **form** and steered by its own **voice**, and all of them are previewed on the
piece's one review page. (Eric, 2026-09-11: *"a piece can have an accompanying note that goes with
it. both should be previewable in the same artifact. the note can have its own style and format."*)

The registry is code — `tools/companions.py` — so the tools and this page cannot disagree about
what exists. This page says why.

## Three axes, never blurred

| Axis | Answers | Examples | Owned by |
|---|---|---|---|
| **Role** | what the text is *for*, and where it goes | `note`, `talk` | the framework |
| **Form** | how it is written, checked and shown | `essay`, `poem`, `note`, `talk` | the framework |
| **Voice** | how it sounds | a folder under `styles/` | **your instance — private** |

Before this, "note", "poem" and a voice's name were used interchangeably, and three per-piece
extras (`substack-note.md`, `linkedin-post.md`, a rendered `linkedin/`) each had their own tool and
no voice at all.

### Forms

| Form | Line breaks | Counted in | Markdown | Footnotes | What it is |
|---|---|---|---|---|---|
| `essay` | reflowed | words | yes | yes | long-form prose in movements — the default main form |
| `poem` | **kept** | lines | no | no | lines and stanzas; a line break is part of the text |
| `note` | reflowed | words | no | no | a few short plain-text paragraphs announcing the piece |
| `talk` | reflowed | minutes | yes | no | a spoken script and its deck in one `draft.md` (`md_to_marp.py`) |

A voice declares the form it writes in — `form:` in its `config.yaml`, default `essay` — so a poem
voice pointed at a talk fails `check` instead of surprising someone at compose time.

### Roles

| Role | Kind | Forms | Goes to |
|---|---|---|---|
| `note` | a **file** in the piece's directory | `note`, `poem` | the piece's one Substack Note (`substack_notes.py`) |
| `talk` | a **sibling piece** | `talk` | a room; its deck and page have their own home |

A talk is a companion that is also a piece: it has figures, a deck, a design hand-off and a log,
and burying it inside another piece's directory would hide it from every tool that walks
`pieces/*/draft.md`. So it keeps its directory and the two point at each other.

## Declaring them

In the main piece's `publish.yaml`:

```yaml
companions:
  note: note.md                  # a file companion
  talk: curse-of-dimensionality  # a piece companion
```

A **file companion** opens with its own header, closed by a `---` line. The header is never posted:

```
form: poem
style: being-good-poem
# scaffold comments go here, as `#` lines
---
For the first year, when I threw the ball,
Pickle thought I was throwing it at him.
```

A **Note carries no URL.** The post's own link is appended from `publish.yaml` when the Note is
built, which is also why a Note can be written before its post is live.

A **piece companion** points back from its own manifest — for a talk, `talk.yaml`:

```yaml
companion_of: love-is-not-a-metric-space
```

**One voice per text.** A piece names exactly one voice; so does each companion. A companion is its
own text, so this is the one-voice rule kept, not an exception to it. Never blend two voices *in*
one text.

## Checking

```bash
python3 framework/tools/companions.py check   # every declaration resolves
python3 framework/tools/companions.py list    # role, form, voice, where
```

`check` holds: the role and form exist; the form suits the role; the file or piece exists; the
voice exists (instance `styles/` first, then `framework/styles/`) and writes that form; a plain-text
form carries no markdown; a Note carries no URL; a talk and its essay point at each other. A
leftover `substack-note.md` is refused — the old shape was retired rather than kept alongside.

## A poem in a Note — measured 2026-09-11

The Substack Notes editor's schema has **no hard-break node** (its nodes: paragraph, text, bullet and
ordered lists, blockquote, codeBlock, mention). A line break inside a paragraph cannot be sent; a
`setContent` that tries leaves the composer empty. So a poem goes **one paragraph per line**, which is
exactly how multi-line Notes already render in the feed — tight lines, no gap (a posted five-line
Note read back as five `<p>` and no `<br>`). **Stanzas are separated by an empty paragraph.** The
editor keeps it; **whether a posted Note keeps it is not yet measured** — the first poem Note
measures it. Until then, a poem that depends on its stanza breaks should be read on the live Note
before anyone calls it shipped.

## Voices: what ships, and what stays private

The framework ships **starter voices, one per form**, deliberately generic:

| Starter | Form |
|---|---|
| `plain-english` | essay |
| `plain-poem` | poem |
| `plain-note` | note |
| `plain-talk` | talk |

Copy one into your instance's `styles/`, rename it, and tune it (`docs/STYLES.md`). **Your tuned
voices never come back.** `tools/voice_privacy.py` enforces it, and the regression suite runs it
whenever an instance is present: no framework style may share a name with one of yours, and no run
of twelve consecutive words from any of your voices' files may appear anywhere in the framework
(runs inherited from `templates/style/` excepted). A name is not a leak — a doc may mention a family
name as an example. Content is.

## On the review page

`review_artifact.py` renders every companion after the piece, on the same page:

- **a Note** as it will sit in the feed — byline, the text with its lines kept, and the post card it
  will unfurl (title, subtitle, hero);
- **a talk** as a summary card (duration, live page, voice), minutes per movement at the voice's
  pace, and the whole script and slide text folded under a disclosure.

Findings can anchor in a Note's text exactly as they do in the prose, and `--apply` writes them into
the companion file. A talk is reviewed on its own page; its companion card links the two.
