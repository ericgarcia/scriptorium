---
name: rewrite
description: Rewrite a finished or already-published piece in a voice that has moved since it was written — after a tune-style pass, or when the author says "rewrite X in the new voice", "re-voice this", "bring this up to the current constitution". Asks the depth questions first (how deep; are the footnotes kept; which figure is run literally; what the close does; which facts and consent lines are touched), then drafts a full new version into draft.md, gates it with critique, and STOPS for the author's read. Never re-syncs a live post itself; that is publish, invoked separately on the author's word.
---

# Rewrite

A voice moves. A `tune-style` pass folds a stretch of corrections into the constitution, and
every piece written under the old constitution is now slightly in the wrong voice. This skill
brings one of them forward: the same piece, said the way the voice says things now.

It is not `draft` (which starts from notes and an outline) and not `critique` (which edits
what is there). It is a full re-say of a piece whose facts, arc and footnotes already exist,
under a constitution that has changed. Most of the work is deciding what stays fixed.

## Before writing anything

1. **Read the piece's scaffold, not just its prose.** `README.md` (stage, voice, decisions,
   guardrails, consent), `publish.yaml` (is it live? which footnotes are verified?), the `log/`
   (what has been corrected on the page since it published — those corrections are load-bearing
   and must survive), and the ledger entries it rests on (`books/<name>/facts.md` for a
   witness-anchored piece).
2. **Read what changed in the voice.** `git log` on `styles/<voice>/style.md` and `config.yaml`
   since the piece's last version, and the `corrections.md` entries in that window. The rewrite is
   *for* those changes; name them to yourself before you touch a sentence. A rule that postdates the
   live text (the Son's capital pronoun, the bracketed house pronoun, the American-English fold) is
   applied now, and the log says which ones were.
3. **Ask the depth questions, with a lean on each**, so "go with your leans" is a complete answer:
   - **How deep?** The witness voice's tune (2026-09-07) argued for shorter — no length floor, stop
     when it lands — and *Flow* came out a third shorter with the same beats. The essay voice's tune
     was deliberately lighter, and a texture pass keeps the sections and the footnotes. **Say which
     you intend.** When the author answers "I don't mind if it's extra work," that is the deep one:
     sections and footnotes may go.
   - **Are the footnotes kept?** A verified footnote is an asset: keep it byte-for-byte (splice the
     old text in programmatically, then prove it identical) and the `verified:` block still stands.
     Cut one only with the prose it supports, renumber, and update every `[^n]` reference in
     `publish.yaml`'s `verified:` text. Never write a new footnote in a rewrite without verifying it;
     a rewrite is not an anchor pass.
   - **Which figure is run literally?** The essay voice now takes its governing figure to its
     accounting and never glosses it. Pick one (the one the piece already has — the confluence, the
     tuned instrument), run it in its own section, and add no new figure. The witness voice's
     equivalent is the household comparison and the one odd detail.
   - **What does the close do?** An inversion of the opening is permitted and a bow is not, in
     both voices. The witness close is the smallest true sentence; the essay close opens a space.
   - **Which lines are consent-bound or fact-bound?** A paragraph about a real person written under
     a recorded consent boundary is re-voiced in sentence length only, with no new facts, and
     flagged for the author's read above everything else. A fact the rewrite would restate (a
     chronology, a place, who was in the room) is checked against the ledger first; when the
     author supplies a better fact mid-rewrite, it goes to `facts.md` *before* it goes to the prose.
   - **Which version seams go?** A published piece accumulates sentences about its own earlier
     versions (*the correction I owe*, *for a while I told it as…*). They are process showing
     through; the reader never saw the earlier version. Cut them, or turn them into direct address
     (*You'd like it to be two roads. I'd like that too.*).
4. **Take the lease** (`lease.py acquire <slug> --what "v<N> rewrite …"`) and **back up the prior
   version** to the scratchpad. Git has it too, but the diff you want later is against the file.

## Writing it

- **Same beats, same order, unless the depth answer said otherwise.** The arc was already argued
  out and critiqued; the rewrite is about the voice, and the author can hear a structural change
  only if the voice change is not also arguing with them.
- **Apply the accumulated corrections as you go, not after.** The shapes that recur across the
  ledger — the autobiography of reading (*this is the part that stopped me cold*), announcing a
  move (*I want to name…*, *this is worth slowing down on*, *let me be exact*), the uncounted
  absolute (*one of the most … the human race has ever produced*), the number the source never
  supplied, the wink and the run-up before the big sentence — are cheaper to not write than to
  cut. Grep for them before critique; the list lives in `corrections.md` and in the voice's
  `avoid:` block.
- **Direct address goes at the hinges.** Where the reader is forming an objection, name it and
  concede it (*You are about to say the two traditions could not have touched. I'd like to say it
  too. It's false.*). Never to instruct, never to corner.
- **The huge sentence is delivered flat and nothing follows it.** If a line after it explains or
  dwells (*A year ago I would not have believed that*), cut the line.
- **Upgrade the cross-links.** A sibling that has gone live since the piece was written gets named
  and hyperlinked in the body where the old text said *another essay*. Canonical `public_url` only.
- **Leave slots, never inventions.** Where the new voice wants a real detail the ledger does not
  hold (what was on the desk at 4 a.m.; what the officer in the basement was doing), put a slot in
  an HTML comment for the author and let the piece stand without it.
- **The header says what version this is and that it is not live.** The published-line stays; the
  voice note names the version, the date, what was rewritten under which rules, what was cut, and
  *not yet re-synced*.

## Gate, then stop

1. `check_pronouns.py --strict` with every named figure; justify each hit by naming its referent
   (a crowd, a doctrine, the non-dualists' term for the Absolute) or fix it.
2. Run `critique` against the **current** constitution and apply what is rule-driven. Judgment
   calls — the close, a paragraph whose last line could read as the old thesis in miniature, a
   chronology rendered from one sentence of the author's — are **flagged for the author, not
   decided**.
3. Log it (append-only): what the rewrite did, what it held constant, what critique changed, what
   is flagged, and that it is **not re-synced**. Update the README stage and next move; update the
   dashboard fragment; `dashboard.py sync`; release the lease. Send the author the file.
4. **Stop.** The author reads. On their word, `publish` handles the re-sync — and a rewrite is
   structural, so it will be a **recompose** of the live post, not a surgical patch: hero and
   caption snapshotted first, the pasteboard verified immediately before the paste, the old range
   deleted after the new body lands, footnotes inserted and checksummed, fidelity digest identical
   to the draft before *Update*, the confirm dialog read for an email control, and
   `substack_verify --fresh` on the public page before the word *done*.

## What this skill has decided so far

- *Flow* v4 (witness, 2026-09-07): same beats, a third shorter; the Superviber episode moved
  inside the nine days on the author's word; version seams cut; wife paragraph re-voiced in
  sentence length only under the standing consent; two-line close on the truck; four detail slots.
- *Krishna Is Not Christ* v2 (essay, 2026-09-07): sections kept, one companion beat (Cappo) and its
  footnote cut, the other fifteen footnotes spliced in verbatim and renumbered; the harmonium and
  the confluence run literally; §VII corrected to the author's account of the chapel (a Thursday, the
  public safety officer in the basement, back on Sunday) after that account was written to the
  ledger first; the close an inversion of the opening; the live *Flow* named and linked in the body.
