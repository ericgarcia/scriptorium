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
