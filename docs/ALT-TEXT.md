# Alt text

**The one statement of the rule.** It used to be written only inside the `publish` skill, which
runs at compose time — while alt text is *written* at draft time and *read* on the review
artifact. Whoever needed the rule was the least likely to meet it. This file is what the skills
point at.

## The rule

**Describe what the image shows, and transcribe any text that is *in* the image, in quotation
marks.**

Both halves are required, and the second is the one that gets forgotten:

- **Describe** — what a sighted reader gets from looking. The subject, what it is doing, the
  arrangement that carries the meaning. Not the file, not the figure number.
- **Transcribe** — every word rendered *inside* the picture: a title, both axis labels, a legend,
  an annotation, a caption drawn into the art. In quotation marks, so a listener can tell the
  image's words from your description of them. **WCAG 1.1.1**: text presented within an image has
  to be available as text. A sighted reader getting four phrases off the picture means a
  screen-reader user must get them too, and it is not optional.

## What alt text is not

| not this | why |
|---|---|
| **A caption** | The caption sits beside the image for everyone. Alt replaces the image for someone who cannot see it, and a page that has both should not say the same thing twice. |
| **A figure number** | *"Figure 7a: two attributes"* names the slide. It does not say a single thing about what is on it. |
| **A citation** | *"Iain McGilchrist, The Master and His Emissary (Yale, 2009)"* describes nothing. A source line is not a description, and putting one in the alt leaves a listener with no image at all. |
| **A restatement of the prose** | If the paragraph already says it, the alt still has to describe the *picture* — the reader who cannot see it is reading that paragraph too. |

## Length

As long as the image is informative and no longer. A photograph is usually a sentence. **A chart
is usually several**, because a chart is mostly text and the text has to come across: title,
axes, legend, the labelled points. If a figure genuinely needs a paragraph, it needs a paragraph
— that is the image being complicated, not the alt being indulgent.

## Decorative images

An image that carries no information takes an **empty** alt (`![](…)`), deliberately, so a screen
reader skips it. This desk has none: every image in the corpus is load-bearing. An empty alt on
a load-bearing image is a bug, and the review artifact flags it in the warning colour.

## It is house prose, and the sweeps govern it

Alt text lives in `draft.md`, so the britishism sweep, the pronoun sweep and every other check
cover it — **but only if they run after it was written.** The first version of one hero's alt said
*labelled* against a spelling rule that names `labeled` explicitly; it went in after the last
sweep and nothing caught it but the author. **Re-run the sweeps after adding or changing an
image.** A passage written after a check does not inherit that check's clean bill.

## Where to read it back

The **review artifact** shows every image with its alt text as prose, labelled, under the picture
— because no other surface an author reads displays it: not `draft.md`, where it is buried inside
`![…](…)`; not Substack; not the live post. It is also **anchorable**, so a review finding can
propose better alt text and `review_artifact.py --apply` writes it like any other change.

## Measured

- **2026-09-10** — a hero's alt omitted the four phrases drawn into the image. Fixed; the rule's
  transcription half comes from that.
- **2026-09-10** — 23 of 34 live posts carried **no** hero alt at all, while the desk held good
  alt text for 21 of them. They lost it to the path they were composed by, not to Substack.
- **2026-09-10** — the two figure-heavy pieces carried **eleven** alts that were slide captions
  rather than descriptions, one of them a bare citation. Rewritten by reading each figure.
