# Scheduling a publication

A piece can be finished and not be due. Between sealing it and publishing it there was
nothing in the desk that knew the difference — every tool that publishes would publish,
and the only thing standing between a sealed piece and a live one was somebody
remembering. This is the thing that knows.

**One field, one moment, one refusal.**

```yaml
publish_at: 2026-09-15 09:00 America/New_York
```

`tools/schedule.py` holds the field and the rule. (Eric, 2026-09-11, on the first
scheduled piece: *"lets seal it but delay publishing it until next week."*)

## The commands

```
python3 framework/tools/schedule.py check <piece>...     exit 4 while it is embargoed
python3 framework/tools/schedule.py list                 every piece carrying the field
python3 framework/tools/schedule.py due --within 48h     what opens inside a window
python3 framework/tools/schedule.py set <piece> "2026-09-15 09:00 America/New_York"
python3 framework/tools/schedule.py clear <piece>
```

`set` refuses the moment before it writes it, so a manifest never carries a `publish_at`
the tools cannot read.

## What it refuses, and what it only warns about

The line is **public, or not public** — not *finished, or not finished*.

| | | |
|---|---|---|
| **`md_to_site.py`** | **REFUSES**, exit 12 | The store bundle is what a site reads. An embargoed piece in it is a published piece. It **refuses** rather than skipping, because a piece named on the command line and silently dropped is how an embargo is discovered a week later. |
| **`md_to_substack.py`** | warns | A Substack draft is private. Composing early is *how* a scheduled publication is prepared, so it composes and prints the moment where the composer will read it. |
| **`md_to_linkedin.py`** | warns | It writes a file on this Mac. The warning is there because the next thing anyone does with that file is paste it. |
| **the `publish` skill** | **stops** | It runs `schedule.py check` in preflight and will not click Publish before the moment. |

## Nothing here fires by itself

Deliberately. `schedule.py` compares a moment to now; it owns no clock and starts no
job. An unattended publication is a decision made explicitly, in the one place built for
it: **Substack's own scheduler**, set in the composer once the draft is ready, which
sends the subscriber email at the appointed time whether or not anyone is at the Mac.
The blog and LinkedIn are done in the session that opens the piece on the day.

The reason to keep it this way is that the desk's publishing steps are not idempotent in
the way a cron job needs — a store publish, a Substack click that sends the one email, a
LinkedIn post — and a failure at 9 a.m. with nobody watching is a worse failure than a
publication that happens at 9:20 with somebody reading the confirm dialog.

## Why the timezone is required

`2026-09-15` is not a moment. It is a date in whatever zone the reader is in, and an
embargo that opens at a different instant depending on who asks is not an embargo. A
moment with no zone is **refused** (exit 2), never assumed.

Write the zone rather than an offset: `America/New_York` stays correct across a DST
boundary where a fixed `-04:00` quietly does not.

## After it opens

The field does not expire and does not need to. Once the moment has passed, `state()`
reads *open*, every tool proceeds, and the line can stay in the manifest as the record of
when the piece was due. Clear it only if the piece is genuinely unscheduled again.
