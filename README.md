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

## Requirements

The writing loop itself — `draft`, `critique`, `style-audit`, `tune-style` — needs nothing but
Claude Code and a git repo. **Publishing needs a real browser**, because Substack has no public
write API: the `publish` and `substack-sync` skills work by driving the Substack editor.

- **Claude Code**, signed in with `/login`. A session authenticated with an API key or a
  `claude setup-token` long-lived token **cannot** use the browser extension, so Chrome
  integration stays off even if you ask for it.
- **A direct Anthropic plan** — Pro, Max, Team, or Enterprise. Not available through Bedrock,
  Vertex, or Foundry; you would need a separate claude.ai account.
- **[The Claude in Chrome extension](https://chromewebstore.google.com/detail/claude/fcoeoabgfenejglbffodgkkbkcdhcgfn)**,
  **v1.0.36 or higher**, in Chrome, Edge, or another Chromium browser (Brave, Arc, Vivaldi,
  Opera). Not supported in WSL.
- **macOS**, for the default compose transport only (`tools/md_to_clipboard.py` uses the
  AppleScript pasteboard). Everything else is platform-neutral.

### Why the extension is required, and not merely nice

A compose has to move a whole essay — tens of thousands of characters of *your* prose — into the
Substack editor. The old path baked the piece into a JS snippet, which meant **the agent retyped
every byte of it**. That makes the agent's transcription the weakest link in the chain: one wrong
character is indistinguishable from an intended edit, so nothing downstream can catch it, and the
failure mode is publishing a typo in your own voice.

The fix is to take the agent out of the transport. `md_to_clipboard.py` puts the composed HTML on
the system pasteboard and a **real ⌘V** pastes it — the bytes go **disk → pasteboard → browser →
editor**, never retyped. That needs a real browser: an in-app or embedded browser pane **cannot
reach the system pasteboard** (`navigator.clipboard.read()` throws *Document is not focused*, and
a synthetic ⌘V is a no-op — a programmatic `.focus()` does not satisfy the Clipboard API).

### Installing the extension

1. Install **[Claude in Chrome](https://chromewebstore.google.com/detail/claude/fcoeoabgfenejglbffodgkkbkcdhcgfn)**
   from the Chrome Web Store and sign in with your Claude account.
2. Start Claude Code with Chrome connected:

   ```bash
   claude --chrome
   ```

   A one-time dialog explains how site permissions work. To skip the flag in future sessions, run
   `/chrome` and choose **Enabled by default** — note this loads browser tools every session and
   costs context, so leave it off if you publish rarely.
3. Check the connection with `/chrome`. It is working when the panel shows **Status: Enabled** and
   **Extension: Installed**.

You can also let Claude Code prompt you: when a skill needs the browser and no extension is
found, it offers a guided install once per session.

**If it is not detected:** confirm the extension is enabled at `chrome://extensions`, make sure
Chrome is actually running, then `/chrome` → **Reconnect extension**. The first install writes a
native-messaging host file that Chrome only reads at startup, so **restart Chrome** if the first
attempt fails. On a long session the extension's service worker can go idle — same fix,
**Reconnect extension**.

**Site permissions** are the extension's, not this framework's. Grant access to your publication's
domain (e.g. `yourpub.substack.com`) in the extension's settings, and stay signed in there —
automation cannot enter credentials.

## Adopt it

See [docs/SETUP.md](docs/SETUP.md), or just run the scaffolding tool:

```bash
tools/new-desk ~/code/writing-desk
```

## What's inside

- `skills/draft` — continue or start a piece in a chosen style.
- `skills/critique` — review a draft against its style; give concrete feedback.
- `skills/style-audit` — the linter to `critique`'s editor: a mechanical,
  read-only sweep that checks a draft against every rule in the style and reports
  each stray line. Use it to make a pass disciplined instead of impressionistic.
- `skills/tune-style` — the gated pass that folds corrections into a style's
  constitution.
- `skills/whats-on-the-desk` — cross-piece triage: what's in flight, what's the
  next move.

Book-scale skills (for a long-form `books/<name>/` manuscript — novel, memoir):

- `skills/book-status` — the `whats-on-the-desk` of book scale: reads the book
  README (truth) and structure, proposes one next move.
- `skills/gmc` — Goal / Motivation / Conflict sheets (Dixon) for characters and
  chapters; the fix for a passive draft.
- `skills/chapter-draft` — draft a chapter steered by the book's scaffold
  (notes, characters, GMC, motifs, and any tuned style); medium-aware.
- `skills/chapter-audit` — read-only craft gate for one chapter (POV, sensory,
  show-not-tell, emotion, agency, metaphor openness, voice, conventions).
- `skills/pov-audit` — does a second POV layer of one event *add* or just
  re-narrate; the gate for an alternating / accordion multi-POV book.
- `skills/continuity-audit` — timeline / age / fact drift and real-world (legal)
  exposure across the manuscript.

- `styles/plain-english` — a starter style to copy and tune.
- `templates/piece` — the per-piece skeleton (README / outline / draft / notes /
  log). `templates/style` — the empty style skeleton.
- `docs/SETUP.md` — stand up your own desk. `docs/STYLES.md` — the style model
  and how tuning works.
- `tools/new-desk` — scaffold a private instance from this framework.
