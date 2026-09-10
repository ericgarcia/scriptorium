# Publishing — one desk, many outlets

**Status: proposed.** Nothing here is built. This is the design to agree before any
site changes; it supersedes nothing until it does.

## What this is for

A piece is finished on the desk. It has to reach every place it belongs — one or more
websites, a Substack, LinkedIn — with the same words, correct canonical links, and no
half-published state where it is live in one place and 404 in another.

Most of that machinery already exists: [`BUNDLE.md`](BUNDLE.md) is the interchange
format, `publish.yaml` names outlets, `md_to_site.py` exports, `outlet_audit.py` checks
both directions. What this document adds is (a) a delivery model where updating content
does not rebuild a site, (b) talks as a first-class content type, and (c) LinkedIn.

## The decision that shapes everything else

> Content should be live seconds after publishing, without a build.

That single requirement rules out the current model, and it rules out a build-time
content layer as the live path. Velite reads files out of a repo during `next build`;
so does a vendored bundle. Both mean *edit → commit → push → build → live*, which is
minutes at best and a git operation at worst.

It also pulls against a value already written into the alignment site's
`next.config.mjs`:

> Pure static HTML. The publication should outlive any particular host: this output
> redeploys to Cloudflare Pages, Netlify, GitHub Pages, S3 or a thumb drive without a
> code change.

Both things are worth having, and they are not actually in conflict once you stop
treating the static export as the *live* artifact and start treating it as an
*archive* you can produce at any time. See [Snapshots](#snapshots-keeping-the-thumb-drive-property).

## Shape

```
  desk (private)                    store (public)                 readers
┌────────────────────┐          ┌────────────────────┐         ┌──────────────┐
│ pieces/<name>/     │          │  index.json        │         │ muffinlabs   │
│   draft.md         │  publish │  pieces/<slug>.json│  fetch  │ alignmentf.  │
│   publish.yaml     │ ───────► │  talks/<slug>/     │ ──────► │ (any site)   │
│   outlets: [...]   │          │  images/<slug>/    │         └──────────────┘
└────────────────────┘          └────────────────────┘
         │                                                     ┌──────────────┐
         └──────────────── browser-driven ───────────────────► │ substack     │
                           (compose, human ships)              │ linkedin     │
                                                               └──────────────┘
```

Two kinds of destination, and the difference is not incidental:

- **Stores** are written to. Publishing is a file upload; the site reads. Idempotent,
  reversible, auditable.
- **Surfaces** are driven. Substack and LinkedIn have no usable write API, so a browser
  composes the post and **a human clicks the final button**. That rule is already in the
  `publish` skill and does not change here: outward-facing publication is not delegated.

## The content store

An **S3-compatible bucket behind a CDN**. S3's API is the closest thing to an open
standard in this space — the same client works against AWS S3, Cloudflare R2, Backblaze
B2 or a self-hosted MinIO, so the store is not a vendor lock-in even though it is a
hosted service today.

```
<store>/
  index.json                     # every published piece, per outlet
  pieces/<slug>.json             # one piece: metadata + rendered html + plain text
  talks/<slug>/deck.html         # standalone deck
  talks/<slug>/notes.json        # per-slide speaker notes
  talks/<slug>/assets/…
  images/<slug>/…webp
```

### Bundles carry rendered HTML, not just markdown

This is the substantive change to [`BUNDLE.md`](BUNDLE.md), and it is what makes the
whole thing simpler rather than more complex.

Today a bundle carries markdown and every destination renders it. That means every
destination needs a markdown pipeline, and they disagree: alignmentfellowship renders
through velite with `remark-gfm`, and muffinlabs has a hand-rolled renderer that
handles headings, lists and whole-line bold **and nothing else** — no images, no links,
no inline emphasis, no footnotes. The same bundle would render differently on the two
sites, and badly on one.

So: **the exporter renders once.** A piece is markdown on the desk and HTML in the
store. Consequences worth stating plainly:

- Both sites display identical output, because it is literally the same bytes.
- Neither site needs a markdown pipeline at all — which dissolves the muffinlabs
  blocker without adding velite to it.
- Footnotes, images and links are settled at publish time, where they can be validated
  once, rather than at render time in two places.
- The markdown stays in the bundle beside the HTML. It is the portable form and the
  thing a future destination re-renders from.

The trade: a rendering change means re-publishing pieces rather than redeploying a site.
That is a batch job over the store, and it is the correct direction — content updates
should not require a deploy, and rendering is content.

### Freshness

The CDN serves with a short TTL and `stale-while-revalidate`; publishing purges the
paths it wrote. A reader sees new content within seconds, and the origin is not hit per
request. Sites fetch at request time (Next: `revalidate` short, or on-demand
revalidation triggered by the same purge).

## Snapshots: keeping the thumb-drive property

Runtime content and host-independence are reconcilable if portability is an artifact
rather than a constraint:

```bash
python3 framework/tools/snapshot.py <store> ./snapshot
```

Walks the store and writes a complete static site — every piece as HTML, every image,
an index. That output deploys to Netlify, GitHub Pages, S3 or a thumb drive with no
code change, exactly as the current export does. The difference is that it is produced
on demand, for archival or for the day a host disappears, instead of being the only way
the site can work.

**This is the honest cost of the decision:** the live site now needs a server (or at
least a runtime fetch), where today it needs nothing. In exchange, a typo fix is live in
seconds. If that trade ever looks wrong, the snapshot is the way back.

## Talks

A talk is a piece whose reader is a room. It has three artifacts and they have different
homes:

| artifact | source of truth | why |
|---|---|---|
| the script | desk (`draft.md`) | it is prose, and it is what the speaker says |
| speaker notes | desk | authored with the script, not with the slides |
| the deck | **Claude Design** (`.dc.html`) | designed visually; the desk cannot express layout |

The flow already used once, to be made routine:

1. The talk is defined on the desk — argument, beats, what each slide must carry.
2. That spec is handed to Claude Design, which produces the deck as `.dc.html`.
3. A framework tool converts the design export into a standalone deck: lift the slides
   out of the `<x-dc>`/`<x-import>` authoring wrapper, emit plain `<deck-stage>` markup,
   and drop the design runtime (which needs React). Speaker notes come out as a sidecar
   `notes.json` so a phone remote can read them without loading the deck.
4. The deck and notes go into the bundle and then the store.

**Streamlining it** means the round trip is one command, not a manual export:
`DesignSync` can read the project's files directly, so a `talk-sync` skill fetches the
current `.dc.html` and assets, converts, validates and stages the bundle — the same
shape as `substack-sync`. Two rules the conversion must keep, both learned the hard way:

- **Assets are verified, not assumed.** A design asset larger than the read limit comes
  back truncated. A PNG without an `IEND` chunk is a truncated download, and the build
  must refuse it rather than ship a broken slide.
- **The design runtime never ships.** `support.js` needs React and exists to serve the
  authoring canvas. `deck-stage.js` has no such dependency and documents a plain-HTML
  usage; that is what gets published.

Presenter tooling — speaker view, phone pairing, slide sync — is a *site* feature, not
content. It reads `notes.json` from the store like anything else.

## Outlets

Unchanged in principle: a piece goes only where its `publish.yaml` names, and `publish`
refuses to guess. What changes is that a store outlet is a write, not a deploy.

| outlet | kind | canonical for | how |
|---|---|---|---|
| `muffinlabs` | store | professional pieces | write to store; site reads |
| `alignmentfellowship` | store | theological pieces | write to store; site reads |
| `substack` | surface | — | browser compose, human publishes |
| `substack-muffinlabs` | surface | — | same; subdomain still unchosen |
| `linkedin` | surface | — | browser compose, human publishes |

### LinkedIn

Constraints, none of them negotiable by tooling:

- **No write API.** Articles have none; even a share needs an approved app and OAuth.
  So it is browser-driven, like Substack, for the same reason.
- **An Article carries the text; a Post announces it.** For an essay the Article is the
  surface, with a Post linking it.
- **LinkedIn emits no `rel=canonical`.** "Link to the canonical" means a visible line in
  the body — *Originally published at <url>* — not a tag. Publish the canonical first
  and let it be indexed before the copy goes up.
- **The final click is never delegated.**

## The audit

`outlet_audit.py` gains a third check, because the store makes a new failure possible:

- **forward** — every published piece resolves on every outlet it declares
- **reverse** — every URL an outlet lists is a piece the desk knows about
- **store** — every piece in `index.json` is served by every site that reads it, and the
  digest the site serves matches the digest in the store

The third one matters because a stale CDN edge is invisible: the store is correct, the
site is wrong, and nothing fails. Comparing digests is what catches it.

## Sequence

1. Agree this document.
2. Bundle spec v2: rendered HTML alongside markdown; talks as a content type.
3. Stand up the store and the shared read client; point one site at it.
4. Move the second site; retire the vendored-bundle path.
5. `snapshot.py`, so the portability promise is real before anyone relies on it.
6. LinkedIn outlet.

## Site hosting is a separate question

The store is the shared asset, and sites read it over HTTPS. **Where a site runs has no
bearing on where content lives** — which is why consolidating hosting is not a
prerequisite for any of this, and should be decided on its own merits.

One thing this design does constrain: content fetched at request time needs compute at
the edge. A site that is a pure static export cannot do it, so the choice of host has to
be one that renders per request. That is a point in favour of hosts with first-class
incremental rendering, and a point against any host whose server-side story is shaky.

## Open questions

- ~~Which store.~~ **Decided 2026-09-10: AWS S3 + CloudFront.** At this scale both were
  free — the store is about 25 MB, and the difference worked out near a tenth of a cent
  a month — so cost decided nothing and the operational argument won: no second cloud,
  no second credential set, and the same account that already runs the presenter API.
  CloudFront's flat-rate plans (Free: 1M requests and 100 GB/month; Pro: $15/month flat
  to 50 TB, no overages) also blunt the egress risk that used to make R2 the obvious
  answer. Because the client is written against the S3 API, moving to R2 later is a
  bucket sync and an endpoint change.
- **Where the rendering lives.** The exporter is Python; the sites are TypeScript. A
  Python renderer keeps publishing in one language, but a TS one could share the exact
  component set the sites use. Rendering once is the point either way.
- **Does muffinlabs keep velite at all?** If content comes from the store, velite has no
  live role. It could stay as the snapshot-time validator, or the schema could move into
  the exporter and velite retire. Keeping both means two schemas that can disagree.
- **Migration of 42 pieces.** Re-export is mechanical, but every published URL must keep
  resolving, and some slugs already diverge between outlets.
