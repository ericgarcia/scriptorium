# The Kitchen Sink *(fixture)*

*Published 2026-01-01 · [The Kitchen Sink](https://example.invalid/p/kitchen-sink) —
this file is the source of record for the live post.
Edits here are not live until pushed (`substack_sync push`),
and `substack_verify --fresh` confirms they landed.*

*Fixture — not writing. Every construct below has caused a converter bug at least once.
Change this file only together with its sealed baseline.*

---

![A plain grey placeholder square](https://substack-post-media.s3.amazonaws.com/public/images/00000000-0000-0000-0000-000000000000_16x16.png)

## I. Emphasis and escapes

A converter has to tell *emphasis* from a literal asterisk. The glob `\*.md` is not
italic text, and neither is the footnote marker in `a \* b`. Both must survive intact,
while *this* stays emphasized and **this** stays bold.[^1]

Quotation marks get smartened on the way out and flattened on the way back, and the
flattening has to preserve length — "like this" and 'like this' both.

## II. Blockquotes

> Two blockquotes separated by a blank line are one quotation.
> The converter merges them.

> They must not arrive as two blocks, because a structural count that disagrees
> with the live post aborts the whole patch.

## III. Lists

Bullet lists render as their own block type:

- the first item
- the second item, with *emphasis* inside it
- the third

## IV. Anchors

This paragraph ends on a footnote anchor,[^2] and is followed immediately by another
anchor[^3] with only a space between them. That exact shape — anchor, space, anchor —
is what an off-by-one in the offset resolver once ate.

[^1]: A footnote carrying *emphasis* and a literal asterisk: `\*`.

[^2]: The second footnote. Two are required before a reorder check has anything to
detect; with one, a reversed list is the identity. † verify: this note must be
stripped by the converter and never reach a post.

[^3]: The third footnote, adjacent to the second.
