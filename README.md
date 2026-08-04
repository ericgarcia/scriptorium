# scriptorium

A markdown-native, Claude-Code-driven **writing desk**: one place to move a piece
from idea to finished draft, and to steer every draft toward a voice you've
tuned — without checking any of your actual writing into a shared repo.

The name is the room: the *scriptorium* was where texts were composed and
copied. This repo is the shareable furniture for that room; your desk is your
own.

## How it's split

- **This repo (`scriptorium`)** is the shareable **framework**: writing skills,
  starter styles, the piece/style templates, docs, and the scaffolding tool. No
  personal writing ever lives here.
- **Your instance** (e.g. `writing-desk`) is a *separate private repo* holding
  your actual pieces, drafts, logs, and your **trained styles**. It mounts this
  framework as a git submodule at `framework/`.

That boundary is the whole trick — same as [trellis](https://github.com/ericgarcia/trellis):
the framework is public and clean; your writing stays private, with its own git
history (so an append-only writing log stays real evidence of what you actually
did).

## Styles are steering, not models

A **style** is a first-class, reusable artifact that *steers* how Claude writes —
it is structured context, not a fine-tuned model. Nothing here trains model
weights. A style is a folder:

```
styles/<name>/
  style.md         # the constitution: voice, principles, do / don't
  config.yaml      # knobs — formality, sentence length, POV, audience
  exemplars/       # passages that embody the voice (the steering signal)
  corrections.md   # append-only: "changed X → Y because…" (your feedback)
```

You "train" a style the way you refine anything here: you draft, you correct, and
the corrections accumulate in `corrections.md`. A deliberate, **gated**
`tune-style` pass distills those corrections into `style.md` — the constitution
is never silently rewritten. See [docs/STYLES.md](docs/STYLES.md).

Starter styles ship here (public, generic). Your *personal* trained voices live
only in your instance.

## Adopt it

See [docs/SETUP.md](docs/SETUP.md), or just run the scaffolding tool:

```bash
tools/new-desk ~/code/writing-desk
```

## What's inside

- `skills/draft` — continue or start a piece in a chosen style.
- `skills/critique` — review a draft against its style; give concrete feedback.
- `skills/tune-style` — the gated pass that folds corrections into a style's
  constitution.
- `skills/whats-on-the-desk` — cross-piece triage: what's in flight, what's the
  next move.
- `styles/plain-english` — a starter style to copy and tune.
- `templates/piece` — the per-piece skeleton (README / outline / draft / notes /
  log). `templates/style` — the empty style skeleton.
- `docs/SETUP.md` — stand up your own desk. `docs/STYLES.md` — the style model
  and how tuning works.
- `tools/new-desk` — scaffold a private instance from this framework.
