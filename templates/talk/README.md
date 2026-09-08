# <Talk Title>

**Stage:** <idea | outline | drafting | revising | rehearsed | delivered>
**Style:** <a spoken-register style, e.g. talk>
**Venue / audience:** <where, who is in the room, how technical>
**Duration:** <NN min + questions>
**Updated:** <YYYY-MM-DD>

## What it is
One or two lines: the claim the room should leave with, and why this room.

## Figures
| file | what it shows | slide |
|---|---|---|
| assets/fig1.png | <one line> | <movement / slide title> |

Every figure is produced by `assets/figures.py` and checked in. Add the row before the
figure exists; the draft may not reference a figure that is not on disk.

## Next move
The single next action.

## Open questions

## Links
- [outline.md](outline.md) · [draft.md](draft.md) · [notes.md](notes.md) · [talk.yaml](talk.yaml) · [log/](log/)
- Deck: `python3 framework/tools/md_to_marp.py pieces/<slug> --check`, then
  `cd pieces/<slug> && npx -y @marp-team/marp-cli deck.md -o deck.html`
