# The content bundle

A **bundle** is scriptorium's interchange format: what a piece looks like once it has
left the desk and before it has reached any particular destination. One format, many
targets — the same way a `draft.md` already becomes a Substack post or a Marp deck.

The point of naming it is that the desk should learn a destination *once*. Substack is
bespoke because Substack chose to have no write API; nothing else has to be.

## Why not just copy `draft.md`

Because `draft.md` is a working file and a bundle is a published artifact. Three things
have to happen in between, and every one of them is a leak if it doesn't:

- **The desk header is stripped.** Everything above the first `---` is desk-internal —
  voice notes, verification status, the working title. `piece_header.py` says it plainly:
  *"everything above the first `---` is front matter that the converter discards, so this
  text can never reach a reader."* A bundle honors the same rule, and **errors** if a
  draft has no `---` rather than guessing.
- **Internal annotations are stripped.** HTML comments anywhere, and anything after a
  `†` or `‡` inside a footnote — those are verify notes, not prose.
- **Images stop being someone else's URLs.** A draft points at wherever the images were
  uploaded. A bundle carries them.

## Layout

```
<bundle>/
  bundle.json               # spec version, generator, what's inside
  content/<slug>.md         # YAML front matter + markdown body
  images/<slug>/<name>.webp # derived, web-sized
  talks/<slug>/piece.json   # a talk's RECORD, filed by kind beside its deck — see Talks
  talks/<slug>/deck.html    # a talk's slides, standalone — see Talks
  talks/<slug>/notes.json   # per-slide speaker notes
  talks/<slug>/deck-stage.js
  talks/<slug>/assets/…
```

Nothing outside this tree is required to render the bundle. That is the property worth
protecting: a bundle is complete, so a repo that vendors one builds standalone, and
anyone who forks it has the whole publication.

## Front matter

The schema is the contract. A destination reads these fields and nothing else.

```yaml
slug: i-believe-in-you
title: I Believe in You
subtitle: What faith was before we broke the word
published_at: 2026-08-27
footnotes: native                  # native | endnotes | none
canonical: https://example.org/writings/i-believe-in-you
syndicated:
  - platform: substack
    url: https://elmuffin.substack.com/p/i-believe-in-you
hero:
  src: ../images/i-believe-in-you/hero.webp
  alt: Two hands reaching toward each other across a stone altar
  width: 1493
  height: 1054
digest: sha256:6f1c…                # of the reader text, see Verification
```

`canonical` is the piece's home address. `syndicated` lists everywhere else it also
lives. Together they encode a publication that is in more than one place without either
copy being a second-class mirror — the destination decides whether to emit
`<link rel="canonical">` pointing home, and a destination that *is* home emits none.

Only `slug`, `title`, `published_at` and `digest` are required.

## Images

**Images are always referenced by relative path. Never an absolute URL.**

That single rule is what keeps content portable: where the bytes actually live is a
property of the *store*, not of the writing, so switching stores never rewrites a draft.

Two stores ship:

- **`repo`** — the default, and correct for almost everyone. Derivatives are written
  into the bundle and committed alongside the content. No account, no API key, no
  vendor, no egress bill, and a fork carries the pictures. A text publication with a
  hero image per piece measures in single-digit megabytes.
- **`s3`** — opt-in, generic S3-compatible: Cloudflare R2, Backblaze B2, MinIO, AWS.
  For a corpus where `repo` genuinely stops being reasonable — photography, video
  stills. The bundle still uses relative paths; the store resolves them at build.

Originals never go in a bundle. They stay with the piece under `assets/`, full
resolution and byte-exact, because that is the archive. A bundle carries derivatives.

## Talks

A talk is a piece whose reader is a room. It is **not a second content type** — it is a
piece with one extra block, so everything already true of a piece stays true: the same
front matter, the same digest, the same rules about images, the same allowlist.

```yaml
slug: love-is-not-a-metric-space
title: Love Is Not a Metric Space
subtitle: or, Why You Should Go to a Weird Party Instead
published_at: 2026-09-20
digest: sha256:…
talk:
  deck: ../talks/love-is-not-a-metric-space/deck.html
  notes: ../talks/love-is-not-a-metric-space/notes.json
  slide_count: 30
  delivered_at: 2026-09-20
  venue: Interintellect
  duration_minutes: 45
```

Only `deck`, `notes` and `slide_count` are required; the rest is a talk being more
specific than the minimum. The presence of `talk` is what makes a piece a talk.

**The body is the transcript.** A talk's `body` is ordinary markdown like any other
piece's, which is the entire reason a talk is not its own type: it renders through the
same renderer, syndicates to the same outlets, and verifies with the same digest. A
reader who never attended gets a piece; the deck is what the room got.

**Deck paths are relative, exactly like images.** Same rule and the same reason — where
the bytes live is a property of the store, not of the writing. A destination rewrites
`../talks/<slug>/deck.html` into whatever it serves; the bundle never names a host.

**The deck is opaque to the bundle.** `deck.html` is a built artifact — slides lifted
out of a Claude Design export by `tools/dc_to_deck.py`, with the design runtime dropped.
The bundle carries it and does not look inside. What a destination needs to *drive* it
(the postMessage protocol, the two-device pairing) lives in the renderer, not here.

**`slide_count` is the deck's own count**, copied from `notes.json` so a destination can
render a position indicator before the deck has loaded. If the two ever disagree, the
deck is right and the bundle is stale.

### Filed by kind (2026-09-10)

A talk's record lives at `talks/<slug>/piece.json`, beside its deck — **not** at
`pieces/<slug>.json`. A talk is still not a second content type: same schema, same renderer, same
digest, same allowlist, same outlets. Only where it is *filed* changed, and the reason is the
slug. With every record in `pieces/`, one slug named one thing across the whole store — every
kind, every site — so *Love Is Not a Metric Space* could not exist as both a talk and its
companion essay, though the sites already served them at `/talks/…` and `/blog/…`. Sites read a
talk with quire's `store.getTalk` (0.8.0), which falls back to the old location only for a record
that is a talk, so the move is safe in either order and an essay is never served as a talk.

### One thing this spec deliberately does not settle

Today the speaker notes are authored in Claude Design and extracted from the export, so
they flow deck → bundle. This document's *Talks* section in `PUBLISHING.md` says the
script's source of truth should be the desk, which is the opposite direction.

Both directions produce the same bundle, which is why the spec can be written now and
that question left open: a bundle is an interchange format, and it should not encode
which end of the desk authored a sentence. What is still unbuilt is the step that turns
notes into transcript markdown — until that exists, a destination that wants a
transcript derives one from `notes.json` at render time. Settle the direction when the
exporter is built, not before.

## Verification

A destination is only trustworthy if you can prove what landed there is what you wrote.
`substack_verify.py` already does this for Substack by comparing the live document's
per-block reader text against `draft.md`. A bundle carries a `digest` over the same
reader-text domain — `render_reader()` in `md_to_substack.py`, which drops markers,
tags and whitespace to leave the text a human actually reads.

**Any new destination should clear that bar before it becomes a default.** A transport
with no verifier is a downgrade, however convenient it looks.

## Opting a piece in

Nothing is exported without being named. In `publish.yaml`:

```yaml
site: true
```

A directory copy would eventually publish a draft nobody meant to publish. An allowlist
read from the manifest cannot. `publish.yaml` is also the file the sync tools keep
current against the live post, which makes it the honest source for what is actually
published — desk prose goes stale, and has.
