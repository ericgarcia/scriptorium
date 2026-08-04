# Styles: steering, not models

A **style** is the reusable answer to "write this *like this*." It is structured
context that steers Claude — a constitution, some knobs, and examples. It is
**not** a fine-tuned model, and nothing in scriptorium trains model weights.
"Training" a style means refining that context over time as you correct output.

## Anatomy

```
styles/<name>/
  style.md         # the constitution — voice, principles, do / don't
  config.yaml      # knobs a skill can read mechanically
  exemplars/       # short passages that embody the voice
  corrections.md   # append-only log of your feedback
```

### style.md — the constitution

Prose the way you'd brief a ghostwriter: who the voice is, what it values, what
it never does. This is what `draft` and `critique` read first. Keep it to
principles and concrete do/don't pairs, not a style encyclopedia — a page that's
actually followed beats ten that aren't.

### config.yaml — the knobs

The mechanical dials a skill can act on without interpretation:

```yaml
formality: 3          # 1 casual … 5 formal
sentence_length: short-to-medium
person: first         # first | second | third
audience: general educated reader
contractions: yes
oxford_comma: yes
avoid:
  - em-dash pile-ups
  - "in today's fast-paced world"
```

### exemplars/ — the steering signal

A handful of short passages that *are* the voice. One vivid exemplar steers
better than a paragraph of adjectives. These can be your own writing or a target
voice you're emulating; either way they live in your **instance**, never in the
public framework, if they're personal.

### corrections.md — append-only feedback

Every time you change a draft's wording for a reason worth keeping, log it:

```markdown
## 2026-08-04
- Changed "utilize" → "use". This voice never inflates verbs.
- Cut the opening rhetorical question; it reads as filler here.
```

Append-only, like every log in this system. A correction you can quietly revise
isn't evidence of how the voice actually behaves.

## How "tuning" works

Two speeds, on purpose:

- **Draft fast.** `draft` reads the style and produces text. Cheap, disposable.
- **Tune slow.** When corrections have piled up, run `tune-style`. It reads
  `corrections.md`, proposes distilling the recurring ones into `style.md` or
  `config.yaml` — **one change at a time**, each justified by corrections you can
  point to — and leaves the rest. The constitution is amended, not patched
  mid-draft.

This mirrors how a rule of life is edited: deliberately, with evidence, not in
the heat of a single session. It keeps a style stable enough to trust and honest
about why it says what it says.

## Starter vs. trained styles

The framework ships **starter** styles — generic, clean, safe to share
(`plain-english`, …). You copy one into your instance and tune it into *your*
voice. Trained styles carry your corrections and your exemplars; they stay
private. Don't push a personal voice back into the public framework.
