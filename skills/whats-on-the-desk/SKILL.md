---
name: whats-on-the-desk
description: Cross-piece triage for the writing desk. Use whenever the user asks "what's on the desk", "what should I write", "where do my pieces stand", or opens a writing session without naming a piece. Reads DASHBOARD.md and the relevant piece READMEs and proposes one concrete next move rather than guessing from memory.
---

# What's on the desk

The view across every piece in flight. Proposes the next move; it doesn't do the
writing (that's `draft`) or the reviewing (that's `critique`).

## Always do this first

1. Read `DASHBOARD.md` — the top of the desk, one block per piece.
2. For whichever piece(s) are in play, read `pieces/<name>/README.md` (its stage,
   target style, next move). Only open `draft.md` / `outline.md` / `log/` if you
   need the detail.
3. Note the date.

Don't propose next moves from the dashboard alone or from memory — the README is
current truth; the dashboard is a summary that can lag.

## Proposing the next move

- Give the live picture briefly: what's drafting, what's waiting on a decision,
  what's near done.
- Propose **one** concrete next move — "draft section 3 of <piece>", "critique
  the open of <piece>", "tune my-voice; corrections have piled up" — not a plan.
  If several compete, say so and let the user pick; priority is theirs.
- A piece blocked on an open question isn't a candidate; name the question
  instead.

## After doing the work

Keep the desk honest — the easy-to-skip part:

1. Append a dated entry to the piece's `log/<current-month>.md` — append-only,
   newest at the bottom.
2. Update the piece's `README.md` (stage, next move).
3. Update the piece's block in `DASHBOARD.md`.
