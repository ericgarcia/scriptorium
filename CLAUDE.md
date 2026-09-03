# Writing desk — behavior

A markdown-native writing desk run through Claude Code. This framework lives in
`framework/` (a git submodule). Your writing lives in `pieces/` and your tuned
voices in `styles/`, in your instance repo. Copy this file to your instance root
and adjust it.

## The loop

- `DASHBOARD.md` is the top of the desk — one block per piece in flight. It is
  **generated** from `DASHBOARD.d/`; edit the fragment, not the file (see
  *Working alongside other sessions*).
- Each `pieces/<name>/README.md` holds that piece's stage, target style, and the
  single next move.
- Detail lives in `pieces/<name>/outline.md`, `draft.md`, `notes.md`, and
  `log/`.

When asked "what's on the desk," read the dashboard, drill into the live piece
README, and propose one concrete next move. After a writing session, log it
(dated, append-only), update the piece README, and refresh the dashboard block.
The `whats-on-the-desk` skill has the details.

## Styles steer; they don't get trained into a model

A style is structured context that steers a draft — never model weights.

- **Pick a style before drafting.** Every piece names a target style in its
  README. `draft` loads that style's `style.md`, `config.yaml`, and `exemplars/`
  as steering.
- **A publication can carry more than one voice.** A book/publication may name
  several styles — e.g. a witness voice that testifies and an argued-essay voice
  that reasons. Each piece picks exactly one; never blend them in a draft. Name
  siblings by a shared prefix (`being-good`, `being-good-essay`); the book README
  lists the voices and says when to use each. See `docs/STYLES.md`.
- **Corrections are append-only.** When you change Claude's wording, the *why*
  goes in `styles/<name>/corrections.md`. Never edit a past correction.
- **The constitution changes only during a `tune-style` pass.** Don't rewrite
  `style.md` mid-draft. Accumulate corrections, then distill them deliberately —
  one change at a time — the way a rule is amended, not patched.

## Working alongside other sessions

Several Claude sessions run against this desk at once — **six on 2026-09-02**. Most of the desk
is already safe under that, and safe by design: `pieces/<slug>/` has exactly one owner, and logs
and `corrections.md` are append-only. Nothing of that kind was ever damaged. **All the damage
landed on shared singletons**, so those are the things with rules.

- **Never edit `DASHBOARD.md` by hand.** It is **generated** from `DASHBOARD.d/<NNN>-<slug>.md`,
  one fragment per piece. Edit *your piece's fragment*, then run
  `python3 framework/tools/dashboard.py sync`. Two sessions updating two pieces now write two
  different files and cannot collide. *(Before this, the same block was silently overwritten
  three times in one afternoon: every session read the whole file, changed its own block, and
  wrote the whole file back.)* `sync` **ingests hand-edits before it renders**, so if you or
  another session edits the generated file anyway, the work is pulled back into the fragment
  rather than lost — but the fragment is the place to write.
- **Take the lease before a long edit to a piece**, and say what you are doing:
  `python3 framework/tools/lease.py acquire <slug> --what "drafting §V"`, and `release` when
  done. It is **advisory** — it stops nobody, and it is not pretending to. What it buys is that a
  session about to touch a piece finds out in one call that another one already is, and who.
  `lease.py list` shows everything held. A lease whose process is gone reads as stale and can be
  broken; **breaking is recorded in the new lease**, never silent.
- **Cross-reference by slug; check the titles.** Titles move late and often — two pieces were
  retitled mid-session on 2026-09-02 while other files went on naming them the old way, and every
  link still resolved, so nothing could see it. `python3 framework/tools/check_refs.py` compares
  the corpus against itself and reports any slug labelled with two different titles, using each
  README's H1 to say which side is right. **`log/` and `corrections.md` are exempt** — they are
  append-only records of what was true when written, and an old title there is history, not rot.
- **Never hard-code a localhost port.** Use `framework/tools/session_port.py`, which derives one
  from the session and **fails loudly** when it is taken. A fixed port plus a swallowed bind error
  once served one session's code to another session's browser. And **identify fetched bytes at the
  point of use** — hash what came back over the wire, not the file you meant to serve.
- **The system pasteboard is global.** Between loading it and pasting, any other session can take
  it. Run `md_to_clipboard.py --verify` immediately before the paste.
- **Scope your commits by path — but a shared ledger is the exception, and it is not worth
  agonizing over.** Commit the piece you worked on and its style edits; do not sweep in another
  session's in-flight work. **The rule is about `pieces/<slug>/` — somebody else's `draft.md`,
  or a whole piece directory that is theirs.** It does **not** govern the book-level append-only
  ledgers (`facts.md`, `pieces.md`, `sources.md`), where four sessions may be appending at once
  and there is no clean seam to cut along: **commit those whole, and say in the message what rode
  along.** (Eric, 2026-09-02: *"I'm fine with changes from other sessions in facts.md being
  committed in different sessions."*) The reason the disclosure still matters is that the commit
  message becomes the only record of what was reviewed and what merely travelled.

## Principles

- **Logs are append-only.** Never edit a past writing-log entry — a log you can
  revise isn't evidence of what you actually wrote.
- **The README is truth; the dashboard is a summary.** If they disagree,
  reconcile rather than guess.
- **Draft freely; tune deliberately.** Drafts are cheap and disposable. The
  style constitution is load-bearing and changes slowly.
- **Add structure only when it's used.** A new skill, style, or template earns
  its place by being used, not by being anticipated.
- **The scaffold holds the reasoning; the prose carries only the result.** When a
  correction lands, regenerate the prose to be simply *right* — never write a
  defense of the change into the draft. The reader never saw the earlier version; a
  clause arguing against it ("but that was never really about X") only shows the
  seams of the process. Corrections, facts, and notes stay in the scaffold; the
  draft reads as if it had always been correct.
