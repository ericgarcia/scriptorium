# Publications

A **publication** is what a reader subscribes to: one audience, one byline, a set of voices,
and the outlets it reaches them through. A desk can carry several. The framework names the
concept so that everything which must be kept *apart* per publication has something to key on.

## The shape of a desk

```
desk
├── publications          publishing/publications.yaml — the registry
│   ├── outlets           where it is read (outlets.yaml defines them; each has ONE owner)
│   ├── books             the long projects whose pieces it publishes
│   ├── styles            the voices it speaks in
│   └── tags              its own vocabulary — publishing/tags/<publication>.yaml
└── pieces                each names exactly one publication in publish.yaml
```

```yaml
# publishing/publications.yaml
publications:
  being-good:
    name: Being Good
    byline: E.L. Muffin
    outlets: [substack, alignmentfellowship]
    books: [being-good]
    styles: [being-good-essay, being-good-journal]
  muffinlabs:
    name: MuffinLabs
    byline: Eric Garcia, PhD
    outlets: [muffinlabs, substack-muffinlabs, linkedin]
    styles: [essay, talk]
```

```yaml
# pieces/<slug>/publish.yaml
publication: being-good
```

## What is per publication, and what is per desk

| per publication | per desk, shared |
|---|---|
| its outlets, and so its sites and its Substack | `pieces/`, one directory per piece |
| its tag vocabulary | the desk's concurrency rules, leases, the dashboard |
| its books and styles | the framework, the tools, the regression suite |
| its byline and its notes about its platforms | the content store (see below) |

A piece belongs to one publication. If the same argument should reach two audiences, that is
two pieces — the way a talk and its essay are two — each in its own publication's voice.

## The rules the tools hold

`tools/publications.py check` (and the suite's corpus check) enforce, once a registry exists:

- **Every outlet belongs to at most one publication.** A site reads the store by outlet, so an
  outlet shared by two publications is a site showing both.
- **Every manifest names a publication the registry defines.** `publications.py assign <piece>
  <publication>` writes the line — as text, under the title and subtitle, leaving every comment
  in the manifest where it was.
- **Every outlet a piece declares belongs to its publication.** The exporter refuses (exit 9) a
  piece that declares another publication's outlet.
- Notes, not failures: a README whose style or book is not one its publication lists, and an
  outlet `outlets.yaml` defines that no publication owns.

**Tags** are checked against the piece's own publication's vocabulary. The same tag id can
mean different things in two publications; neither vocabulary knows the other exists.

**The content store is shared** by every publication's sites, and it keys a record by slug
(and kind). So a slug belongs to one publication: the exporter records `publication` in the
bundle, `bundle_pieces.py` refuses (exit 9) to write one publication's piece over another's,
and `store_publish.py` refuses (exit 7) a bundle that would move a live record from one
publication to another. When two publications want the same slug, one of them sets
`site_slug:` in its manifest.

## One publication needs none of this

With no `publishing/publications.yaml`, every tool behaves as it always did: one tag
vocabulary at `publishing/tags.yaml`, and no piece is asked to name a publication. Add the
registry the day a second publication arrives, then `assign` every piece to one of them —
`publications.py check` lists the ones still to do.

## Adding a publication

1. Define its outlets in `publishing/outlets.yaml`, and its platform notes beside them.
2. Add it to `publishing/publications.yaml` with the outlets it owns — moving an outlet from
   one publication to another is a decision about a live site, not a tidy-up.
3. Give it styles (`styles/<prefix>-…`, per `STYLES.md`) and, when its pieces start carrying
   tags, a vocabulary: `tags.py define <tag> --label … --about … --publication <id>`.
4. `publications.py check` — every piece named, every outlet owned.
