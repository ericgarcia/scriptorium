---
name: linkedin-article
description: Compose a finished, already-published piece as a LinkedIn Article DRAFT for the author to publish — the syndication copy, with an "Originally published at" line in place of rel=canonical and endnotes in place of footnotes. Use when the user says "put X on LinkedIn", "syndicate X to LinkedIn", "LinkedIn article for X", or a piece whose publish.yaml names `linkedin` has gone live on its canonical outlet. Composes and STOPS: the author reviews, writes the announcing post, and clicks Publish. Never posts, never engages, never publishes.
---

# LinkedIn Article

LinkedIn is the last outlet a piece reaches, and it is a copy. The canonical — the site
the piece calls home — goes first and gets indexed; Substack follows; LinkedIn comes
last and says where the original lives. This skill composes that copy and stops.

## Before anything else

**There is no API.** Articles have no write endpoint at all, and even a short share needs
an approved app and OAuth. So the Article is composed the way a person composes one, in
the author's own logged-in Chrome through `mcp__claude-in-chrome__*`.

**That is automated access to LinkedIn, which its user agreement prohibits.** The instance
records the author's decision about it; read that before doing anything (on this desk:
`.claude/skills/linkedin/SKILL.md` in the command center, which decided profile fields
on 2026-09-08 and, in its first version, said *never posts*). If the instance has not
extended that decision to Articles, **stop and ask** — composing an Article draft is a
wider scope than editing a headline, and it is the author's call, not the tool's.

Where it is allowed, keep what makes it defensible:

- **One Article, at human pace, and a human publishes.** No loops, no batches.
- **Nothing social.** Never a reaction, comment, connection, message or repost — and never
  the announcing Post either: the publish dialog asks for one, and the author writes it.
- **Draft only.** Close the editor with the Article saved as a draft; LinkedIn autosaves.

## Preflight — the converter refuses, and that is the point

```bash
python3 framework/tools/md_to_linkedin.py pieces/<name> --outlets publishing/outlets.yaml --check
```

It refuses, with no `--force`, when:

- `publish.yaml` does not name `linkedin`. Nothing goes where it was not sent.
- `check_verified.py` refuses. Syndication does not weaken verification.
- the body carries a verify marker, an unpaired footnote, or a clearance date.
- **the canonical is not recorded and live.** PUBLISHING.md: publish the canonical first
  and let it be indexed. An Article whose first line says *originally published at* a URL
  that 404s is a broken promise in the opening sentence — and if LinkedIn goes up first,
  LinkedIn is the copy search engines find.

Then, without `--check`, it writes `pieces/<name>/linkedin/article.html` and
`article.json` (title, canonical, figures in upload order with their alt text).

## What the copy looks like, and why

| On the canonical | On LinkedIn | Because |
|---|---|---|
| `rel=canonical` | *Originally published at <url>* as the first line | LinkedIn emits no canonical tag |
| subtitle | italic lede under that line | an Article has a title and nothing else |
| native footnotes | `[1]` in the text, **Notes** at the end | LinkedIn has no footnotes; numbered in first-reference order, as Substack numbers them |
| figures | a marked slot per figure, uploaded by hand | unmeasured what the editor does with a pasted data: image |

## Composing — and the parts not yet measured

**This path has not been driven end to end yet.** What follows is the plan; replace each
*unmeasured* with what actually happened, the way the Substack skill records its traps.

1. Open `https://www.linkedin.com/article/new/` in the author's Chrome (they are logged in;
   automation never enters credentials).
2. Title: `article.json` → `title`. Click the title field and **type** it. The profile
   skill measured that pasting through the extension mangles non-ASCII — em dashes arrive
   as `‚Äî` — and typing does not.
3. Body: load `article.html` onto the pasteboard as HTML and paste with a real ⌘V into the
   body after a real click — `md_to_clipboard.py`'s lease and `--expect-url` guard exist
   precisely for this, and the agent never retypes the essay. *Unmeasured: whether the
   editor keeps h2, em, strong and links from a native HTML paste.* Screenshot and zoom to
   confirm before going further.
4. Figures: for each slot in order, delete the slot paragraph, use the editor's image
   button, upload `article.json` → `images[k].file`, and set its alt text from
   `images[k].alt`. *Unmeasured: where the image control is and whether alt text is
   settable at upload.*
5. Cover image: optional; ask.
6. **Stop.** Say what was composed and where, and that the author reviews it, writes the
   announcing post in the publish dialog, and clicks Publish.

## After the author publishes

- Record the Article's URL in `publish.yaml` under the outlet's `manifest_url_key`
  (`linkedin_url` on this desk). **It cannot be derived** — LinkedIn appends an id — so an
  unrecorded URL is an unaudited copy.
- Run `python3 framework/tools/outlet_audit.py --outlet linkedin`. It checks the recorded
  URL, and a missing Article is reported missing: LinkedIn redirects a dead Article to a
  live 200 page, and the audit knows that page when it sees it.
