#!/usr/bin/env python3
"""
scratch_draft.py — the one draft per outlet that a test is allowed to write into.

Why (Eric, 2026-09-11): every probe of a composer used to make a NEW draft — "TEST — DELETE ME
(caption)" on the MuffinLabs Substack, "[TEST — do not publish]" on LinkedIn — and deleting a
draft is the author's click, never the agent's. So they piled up, each one a chore left for him.
Now each outlet keeps ONE standing scratch draft, recorded in the instance's outlets.yaml, and
every test overwrites it. Nothing new is created, so nothing is left to delete.

  outlets:
    substack-muffinlabs:
      scratch_draft:
        id: 215233016
        edit_url: https://muffinlabs.substack.com/publish/post/215233016

  python3 framework/tools/scratch_draft.py <outlet> [--config publishing/outlets.yaml]
      prints the edit URL and the title to set; exit 2 when the outlet has none recorded
  python3 framework/tools/scratch_draft.py --list

REUSING IT: open edit_url, set the title to TITLE, clear the body (the Tiptap editor's
`commands.clearContent()`), then paste. Never Continue, Publish, Send or Post from it. The title
is set on every use, so the draft always says what it is, whatever the last test left there.

AN OUTLET WITH NONE: create one draft, give it TITLE, and record its id and edit URL in
outlets.yaml in the same session. From then on it is that outlet's scratch, for good.

A SITE has no editor, so its scratch is a store record, scratch/<outlet>.json, that the site
renders with its real renderer at a noindexed page no list or sitemap shows (quire 0.16):

    alignmentfellowship:
      scratch_draft:
        view_url: https://alignmentfellowship.org/scratch/

  python3 framework/tools/bundle_pieces.py <content-dir> <bundle-dir> --outlet <o> --scratch [--images DIR]
  python3 framework/tools/store_publish.py <bundle-dir>      # then open view_url
"""
import sys, argparse
import yaml

TITLE = 'TEST — scratch draft, reused by the tools (never publish)'


def scratch_for(cfg, outlet):
    """The outlet's recorded scratch draft as {id, edit_url}, or None when it has none.
    A half-recorded one is refused: an edit URL that does not carry the id is how a test
    would end up overwriting some other draft."""
    outlets = (cfg or {}).get('outlets') or {}
    if outlet not in outlets:
        raise KeyError(f'no outlet {outlet!r} in outlets.yaml')
    s = (outlets[outlet] or {}).get('scratch_draft')
    if not s:
        return None
    if isinstance(s, dict) and s.get('view_url'):
        if not str(s['view_url']).startswith('https://') or s.get('id') or s.get('edit_url'):
            raise ValueError(f'{outlet}: a site scratch is an https view_url alone, got {s!r}')
        return {'kind': 'store', 'store_key': f'scratch/{outlet}.json', 'view_url': s['view_url']}
    if not isinstance(s, dict) or not s.get('id') or not str(s.get('edit_url', '')).startswith('https://'):
        raise ValueError(f'{outlet}: scratch_draft needs an id and an https edit_url, got {s!r}')
    if str(s['id']) not in s['edit_url']:
        raise ValueError(f"{outlet}: scratch_draft edit_url does not carry its id {s['id']}")
    return {'kind': 'editor', 'id': str(s['id']), 'edit_url': s['edit_url']}


def main(argv=None):
    ap = argparse.ArgumentParser(description='the standing test draft for an outlet')
    ap.add_argument('outlet', nargs='?')
    ap.add_argument('--config', default='publishing/outlets.yaml')
    ap.add_argument('--list', action='store_true', help='every outlet and its scratch draft')
    a = ap.parse_args(argv)
    with open(a.config, encoding='utf-8') as f:
        cfg = yaml.safe_load(f) or {}
    try:
        if a.list:
            for name in (cfg.get('outlets') or {}):
                s = scratch_for(cfg, name)
                print(f"{name:24} {(s.get('edit_url') or s.get('view_url')) if s else '(none recorded)'}")
            return 0
        if not a.outlet:
            ap.error('name an outlet, or pass --list')
        s = scratch_for(cfg, a.outlet)
    except (KeyError, ValueError) as e:
        print(f'scratch_draft: {e.args[0]}', file=sys.stderr)
        return 1
    if s is None:
        print(f'{a.outlet} has no scratch draft recorded. Create ONE draft there, title it\n'
              f'  {TITLE}\n'
              f'and record it under outlets.{a.outlet}.scratch_draft (id, edit_url) in {a.config}\n'
              f'in this session. Never make a second.', file=sys.stderr)
        return 2
    if s['kind'] == 'store':
        print(f"view_url:  {s['view_url']}\nstore_key: {s['store_key']}\n"
              f"upload:    bundle_pieces.py <content-dir> <bundle-dir> --outlet {a.outlet} --scratch "
              f"[--images DIR], then store_publish.py <bundle-dir>")
        return 0
    print(f"edit_url: {s['edit_url']}\ntitle:    {TITLE}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
