# Visual style — <Talk Title>

*The general design brief for every slide in this deck. Hand it to the designer first; the
per-slide briefs (`NN-*.md`, generated from `draft.md`) assume it. The author owns this file;
`md_to_marp.py --briefs` never overwrites it.*

## What the deck is for
<One paragraph: the room, the length, the one claim the audience leaves with, and the tone —
e.g. "a 45-minute argued talk to a mixed technical room; deadpan, generous to the other side;
the slides carry what the ear cannot and never the script.">

## The rule every slide obeys
- **One claim per slide.** A slide shows only what a listener can't take in by ear: a figure,
  a number, a source, or one line to keep. It is never the script, and the speaker never reads it.
- **Nothing on a slide the speaker did not write.** The per-slide brief gives the text
  verbatim; do not add, cut, or rephrase it. Design the presentation of it.
- **The back row is the reader.** Minimum type size on a body line: <NN pt at 16:9 1280×720>.

## Canvas
- Aspect: <16:9> · Safe margins: <NN px> · Footer: <text, or none> · Page numbers: <yes/no>

## Palette
| role | value | use |
|---|---|---|
| paper | `#…` | slide background |
| ink | `#…` | all body text |
| accent | `#…` | the one thing to look at; never more than one accent element per slide |
| cool | `#…` | secondary marks, section slides |
| mute | `#…` | captions, footer, the least important line |

The figures were generated in this palette; the slides must not fight them.

## Type
- Display (titles, section slides): <family, weight, size>
- Body (the one line, bullets): <family, weight, size>
- Captions and citations: <family, size>
- Figures use their own type (generated); do not restyle them.

## The five kinds of slide, and how each looks
1. **Title** — <layout: title, subtitle, speaker; nothing else>
2. **Section** — <movement numeral and name only; the room breathes here>
3. **Claim** — <one line, large, centered or left; generous space; the title small above it>
4. **Bullets** — <three at most; never a sentence; no icons>
5. **Figure** — <the figure fills the free height; title above or none; no caption the speaker
   would only read aloud anyway>

## Do / Don't
- Do: <…>
- Don't: <decorate; add stock imagery; animate; put the script on the slide; use a second accent>

## Continuity
<What should stay identical from slide to slide — the footer, the margin, the title position —
so a 30-slide deck reads as one object.>
