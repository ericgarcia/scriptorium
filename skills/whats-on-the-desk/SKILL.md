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

## Name the session after the piece

Once you know which piece you are working on, rename the session to that piece's title, by
calling `mcp__ccd_session_mgmt__set_session_title` with `session_id: "self"` and the title. The
app's session list then reads as a shelf of pieces instead of a row of identical entries.

- **Take the title from `pieces/<slug>/publish.yaml` (`title:`), falling back to the README's
  H1.** Titles on this desk move late and often — one was retitled on Substack at publication and
  pulled back into the manifest — and `publish.yaml` is what actually ships to a reader.
- **Re-title whenever the piece changes.** A session that opens on one piece and moves to another
  should carry the name of the one it is on *now*. That is where the value is; naming it once at
  the start is the part that goes stale.
- **Best-effort, and silent when it fails.** The tool lives in the Claude Code desktop app. A
  terminal session does not have it, and there is no way to test for it except by calling. If it
  is missing, carry on — do not retry, do not mention it, and never let it block the work.
- **It will not stomp a title the author chose.** The app asks them to approve a rename over a
  title they set themselves, and replaces its own generated titles without asking. So propose
  freely; the guard is on their side of it.
- **This skill triages across pieces, so rename only once a single piece is settled on** as the
  next move — not while you are still surveying the desk.

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
