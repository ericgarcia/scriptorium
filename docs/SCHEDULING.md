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

## The order: compose, review, THEN arm

**The schedule is not set until the drafts are reviewed and approved.** (Eric, 2026-09-11:
*"in general, we dont set the schedule until the drafts are reviewed and approved."*)

A scheduled publication is the one kind that fires with nobody watching, so the reading has to
have happened before it is armed — and the thing to read is produced by composing, which puts
composing *first* and arming last:

1. **Compose the drafts** under the embargo. A Substack draft is private and a LinkedIn Article
   is a draft until published; `md_to_substack.py` prints the embargo and carries on, which is
   what makes this step possible at all.
2. **The author reads them** — the drafts themselves, and the review artifact beside them.
3. **Then arm.** Each platform's own scheduler is set to the moment, and any desk-side wake-up
   is recorded with `schedule.py arm --reviewed "<who, when>"`. **`arm` refuses without
   `--reviewed`**, and writes who approved it into the manifest, so the order is auditable
   afterwards rather than merely intended.

Ordering note for a syndicated piece: the LinkedIn copy carries *Originally published at
&lt;canonical&gt;*, so it is composed **after** the canonical is live, not before. That is a
publication-day step, not a preparation step.

## Not every outlet waits — `on_schedule:`

**One piece has one moment; the outlets it names do not all want it.** (Eric, 2026-09-11: *"we
should be able to configure an outlet for immediate publishing when scheduling … this is because
the other sites (substack and linkedin) benefit from regular publishing and the websites (using
quire) are the canonical publications and do not drive traffic".*)

So the policy belongs to the **outlet**, in the instance's `publishing/outlets.yaml`:

```yaml
outlets:
  alignmentfellowship:
    on_schedule: immediate     # canonical quire site: publishes as soon as the piece is ready
  substack:
    on_schedule: at_moment     # the default; a feed outlet waits for publish_at
```

| class | outlets | why |
|---|---|---|
| **immediate** | the quire websites | They are the **canonical** publication and drive no traffic. A finished piece belongs there at once, and its URL is what every other outlet points at. |
| **at_moment** | Substack, LinkedIn | Regular publishing is the point of a feed. The moment is for them. |

**It fails closed, in every direction.** A missing registry, an unknown outlet, an absent
`on_schedule`, a typo (`imediate`), or no PyYAML all answer `at_moment` — the answer that refuses
to publish. Only the exact string `immediate`, on that one outlet, turns the moment off.

**An exemption is said out loud.** `md_to_site.py` prints *"… is embargoed until <moment>, and
<outlet> is configured `on_schedule: immediate` — publishing it there now, on purpose"*, because a
piece published before its moment with nothing on the terminal reads exactly like a piece that
never had an embargo.

### What dates a canonical-first piece

`md_to_site.py` exports a piece once it has `published_at`, and `bundle_pieces.py` **requires**
it — the page a reader gets has to be dated. So the date is the mechanism, and it is written at
the canonical publication rather than derived from `publish_at`:

- **A piece published canonically first** records `published_at` on the day the site goes live.
  The feed outlets are then *scheduled, not missing* — `outlet_audit` reads that state through the
  outlet's `on_schedule` and counts it as `sched` while the moment is ahead.
- **A redraft of an already-live piece keeps its original date** (Eric, 2026-09-11:
  *"the redrafts KEEP THEIR ORIGINAL DATES"*), held in `original_published_at:` and copied to
  `published_at` at the cutover, so setting it early cannot put the piece into the store before
  the switch.

An earlier version of this page said the unpublished guard in `md_to_site.py` had to move for an
immediate outlet. It did not: that guard only decides what enters the bundle *content*, and
`bundle_pieces` refuses an undated piece immediately afterwards — so relaxing it moved a refusal
one step later and changed nothing that could publish. The date is what makes a canonical-first
publication possible, and `publish_at` still governs every outlet that waits.

## The wake-up, and what it is for

`schedule.py runbook <piece>` prints a self-contained prompt for a scheduled session: the piece,
the moment, the gates, the order, and what to do if it fires late. It is generated from the
manifest rather than typed, so moving `publish_at` cannot leave a stale moment buried in a prompt
nobody re-reads. `arm` records the task; `armed` lists what is armed across the desk.

What a wake-up is *for* is the step no platform can do for itself — the canonical store publish
and the redirect removal. The subscriber email and the syndicated copies belong to Substack's and
LinkedIn's own schedulers, which need nothing from this Mac and do not care whether the app is
open.

## Record the act, not only the intent

`publish_at` says when a piece is **due**. A native schedule — Substack's, LinkedIn's — lives on
the platform, where nothing in this desk can see it. So a tool reading `publish_at` alone reports
*"its own scheduler has it for Tuesday"* **whether the schedule was set or forgotten**, which is
the one failure a scheduled publication actually has.

So the act is written down where the intent is:

```yaml
scheduled:
  substack-muffinlabs:
    at: 2026-09-15 09:00 EDT
    set: 2026-09-11
    where: Substack's own scheduler, on draft 215307337
    evidence: https://muffinlabs.substack.com/publish/post/215307337
    approved: Eric, 2026-09-11
```

written by `schedule.py record`, which **refuses without `--approved`** for the same reason `arm`
does. `outlet_audit` then reads three states rather than two:

| | |
|---|---|
| **scheduled** | due later, and a record says a scheduler was told — printed with where and when |
| **NOT SCHEDULED** | due later, and nothing records one. **A finding, on the day it can still be fixed.** |
| **MISS** | the moment has passed and the copy is not there |

## Two things measured on the first scheduled publication (2026-09-11)

**A scheduled Substack post has its slug from the moment it is scheduled.** `GET
/api/v1/drafts/<id>` reads `slug: null` on a plain draft and the real slug once `postSchedules`
exists — so the post's public URL is knowable days ahead, and anything that needs it (a Note, a
cross-link, a LinkedIn copy) can be prepared before the post is live. The URL serves a teaser
page in the meantime: title and `og:` tags, **no body**, `robots: noindex`. The piece is not
readable early.

**But a Note cannot attach a post that has not published.** Composing the Note ahead of time —
with the correct URL, from the correct slug — puts *"This attachment is not available"* in the
composer instead of the post's card. The teaser page carries every `og:` tag a card needs, so
this is Substack refusing to attach an unpublished post, not missing metadata. The consequence
is the rule:

> **A Note scheduled ahead of its post carries a plain link, not a card.** To get the card, the
> Note is composed *after* the post is live. `substack_notes.py text <slug> --post-url <url>`
> builds the scheduled version for the case where a plain link is acceptable.

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
