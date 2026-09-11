#!/usr/bin/env python3
"""
companions.py — the forms a text can take, and the companions a piece can carry.

A PIECE is one main text (`draft.md`). It may carry COMPANIONS: other texts that go out with it,
each written in its own FORM and steered by its own VOICE. The poem posted as a piece's Substack
Note is a companion; so is the talk of the same argument. Every text — main or companion — names
exactly one voice. A companion is its own text, so the one-voice rule is kept, not bent.

THREE AXES, NEVER BLURRED

  role   what the text is FOR and where it goes         note, talk          (this file)
  form   how it is written, checked and shown           essay, poem, ...    (this file)
  voice  how it sounds                                  a style folder      (styles/<name>/)

  Roles and forms are the framework's: they are what every desk shares. Voices are the
  instance's and stay private; the framework ships only generic starters (`framework/styles/`).
  A voice declares the form it writes in (`form:` in its config.yaml, default `essay`), so a
  poem voice pointed at a talk is a check failure, not a surprise.

DECLARING THEM — publish.yaml of the main piece

  companions:
    note: note.md                   # a FILE companion, in the piece's own directory
    talk: curse-of-dimensionality   # a PIECE companion: a sibling piece with its own scaffold

  A file companion opens with its own header, closed by a `---` line:

    form: poem
    style: being-good-poem
    # scaffold comments, never posted
    ---
    For the first year, when I threw the ball,
    ...

  A piece companion keeps its own directory (a talk has figures, a deck and a log; burying it
  inside another piece would hide it from every tool that walks `pieces/*/draft.md`). It points
  back: `companion_of: <main slug>` in its talk.yaml. `check` holds both ends to each other.

Commands

  list [<slug> ...]    every piece's companions: role, form, voice, where
  check                every declaration resolves: role, form, file, voice, voice's form,
                       back-pointer; a legacy substack-note.md is refused (moved to `note`)

Exit: 0 ok, 1 problem found.
"""
import sys, os, re, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMEWORK = os.path.dirname(HERE)
ROOT = os.path.dirname(FRAMEWORK)

# ----------------------------------------------------------------------- the registry
# What a form IS, for the tools. `lines`: keep = a line break is meaning (a poem), reflow = it
# is not (prose). `unit`: what the review page counts. `markdown`: whether the text may carry it.
FORMS = {
    'essay': {'lines': 'reflow', 'unit': 'words', 'markdown': True, 'footnotes': True,
              'what': 'long-form prose in movements, with footnotes — the default main form'},
    'poem':  {'lines': 'keep', 'unit': 'lines', 'markdown': False, 'footnotes': False,
              'what': 'lines and stanzas; a line break is part of the text'},
    'note':  {'lines': 'reflow', 'unit': 'words', 'markdown': False, 'footnotes': False,
              'what': 'a few short plain-text paragraphs announcing the piece'},
    'talk':  {'lines': 'reflow', 'unit': 'minutes', 'markdown': True, 'footnotes': False,
              'what': 'a spoken script and its deck in one draft.md (md_to_marp.py)'},
}

# What a role is FOR. `kind`: file = a text in the piece's directory; piece = a sibling piece.
ROLES = {
    'note': {'kind': 'file', 'forms': ('note', 'poem'), 'outlet': 'substack-notes',
             'what': "the piece's one Substack Note (substack_notes.py posts it)"},
    'talk': {'kind': 'piece', 'forms': ('talk',), 'outlet': None,
             'what': 'the talk of the same argument, delivered to a room'},
}

LEGACY_NOTE = 'substack-note.md'
MARKDOWN = re.compile(r'(\*\*?|__?)\S|\[[^\]]+\]\(|^#{1,6}\s', re.M)


def default_pieces():
    env = os.environ.get('DESK_PIECES')
    return os.path.abspath(env) if env else os.path.join(ROOT, 'pieces')


def style_dirs(pieces_dir):
    """The instance's voices first, then the framework's starters."""
    root = os.path.dirname(os.path.abspath(pieces_dir))
    return [os.path.join(root, 'styles'), os.path.join(FRAMEWORK, 'styles')]


def style_form(name, pieces_dir):
    """-> ([forms], path) for a voice, or (None, None) when no such voice exists.

    `form: poem`, or a list — `form: [essay, note]` — for a voice that writes more than one
    (a piece's own voice usually writes its Note too). No `form:` means essay."""
    for base in style_dirs(pieces_dir):
        d = os.path.join(base, name)
        if os.path.isdir(d):
            forms = ['essay']
            cfg = os.path.join(d, 'config.yaml')
            if os.path.exists(cfg):
                for line in open(cfg, encoding='utf-8'):
                    m = re.match(r'form\s*:\s*(\[[^\]]*\]|[\w-]+)', line)
                    if m:
                        forms = [f.strip() for f in m.group(1).strip('[]').split(',') if f.strip()]
                        break
            return forms, d
    return None, None


# ----------------------------------------------------------------------- reading
def manifest_block(path, key):
    """The one-level `key:` block of a flat manifest, as {k: v}. Comments dropped."""
    out, inblock = {}, False
    if not os.path.exists(path):
        return out
    for line in open(path, encoding='utf-8'):
        s = re.split(r'\s+#|^#', line.rstrip('\n'), maxsplit=1)[0].rstrip()
        if re.match(rf'{re.escape(key)}\s*:\s*$', s):
            inblock = True
            continue
        if inblock:
            if not s.strip():
                continue
            if not s.startswith((' ', '\t')):
                break
            k, _, v = s.strip().partition(':')
            out[k.strip()] = v.strip().strip('"\'')
    return out


def manifest_value(path, key):
    if not os.path.exists(path):
        return ''
    for line in open(path, encoding='utf-8'):
        m = re.match(rf'{re.escape(key)}\s*:\s*(.+?)\s*(#.*)?$', line)
        if m:
            return m.group(1).strip('"\'')
    return ''


def read_text(path):
    """-> (meta, body). The header is `key: value` lines and `#` comments, closed by `---`."""
    raw = open(path, encoding='utf-8').read()
    head, sep, body = raw.partition('\n---\n')
    if not sep:
        return {}, raw
    meta = {}
    for line in head.split('\n'):
        if line.lstrip().startswith('#') or not line.strip():
            continue
        m = re.match(r'([a-z_]+)\s*:\s*(.*?)\s*$', line)
        if not m:
            return {}, raw                          # not a header after all
        meta[m.group(1)] = m.group(2)
    return meta, body


def stanzas(body):
    """[[line, ...], ...] — blank lines separate stanzas (or paragraphs); lines are kept."""
    return [[l.rstrip() for l in chunk.strip('\n').split('\n')]
            for chunk in re.split(r'\n[ \t]*\n', body.strip()) if chunk.strip()]


def paragraphs(comp):
    """The text as the form reads it: a poem keeps its lines, prose is reflowed."""
    blocks = stanzas(comp['body'])
    if FORMS.get(comp['form'], {}).get('lines') == 'keep':
        return blocks
    return [[' '.join(l.strip() for l in b)] for b in blocks]


def companions(piece_dir):
    """Every companion the piece declares, resolved as far as it will go."""
    pieces_dir = os.path.dirname(os.path.abspath(piece_dir))
    out = []
    for role, target in manifest_block(os.path.join(piece_dir, 'publish.yaml'), 'companions').items():
        c = {'role': role, 'target': target, 'path': '', 'form': '', 'style': '',
             'meta': {}, 'body': ''}
        kind = ROLES.get(role, {}).get('kind')
        if kind == 'file':
            c['path'] = os.path.join(piece_dir, target)
            if os.path.exists(c['path']):
                c['meta'], c['body'] = read_text(c['path'])
                c['form'] = c['meta'].get('form', '')
                c['style'] = c['meta'].get('style', '')
        elif kind == 'piece':
            c['path'] = os.path.join(pieces_dir, target)
            if os.path.exists(os.path.join(c['path'], 'talk.yaml')):
                c['form'] = 'talk'
            c['style'] = readme_style(c['path'])
        out.append(c)
    return out


def companion(piece_dir, role):
    return next((c for c in companions(piece_dir) if c['role'] == role), None)


def readme_style(piece_dir):
    p = os.path.join(piece_dir, 'README.md')
    if os.path.exists(p):
        m = re.search(r'styles/([a-z0-9][a-z0-9-]*)/', open(p, encoding='utf-8').read())
        if m:
            return m.group(1)
    return ''


# ----------------------------------------------------------------------- checking
def problems_of(c, piece_dir):
    slug = os.path.basename(os.path.abspath(piece_dir))
    pieces_dir = os.path.dirname(os.path.abspath(piece_dir))
    role = ROLES.get(c['role'])
    if not role:
        return [f"unknown role {c['role']!r} (known: {', '.join(ROLES)})"]
    if role['kind'] == 'file' and not os.path.exists(c['path']):
        return [f"{c['role']}: no file {c['target']}"]
    if role['kind'] == 'piece':
        if not os.path.isdir(c['path']):
            return [f"{c['role']}: no piece {c['target']}"]
        if c['role'] == 'talk' and not c['form']:
            return [f"talk: {c['target']} has no talk.yaml"]
        back = manifest_value(os.path.join(c['path'], 'talk.yaml'), 'companion_of')
        if back != slug:
            return [f"talk: {c['target']}/talk.yaml must say `companion_of: {slug}` (says {back or 'nothing'})"]
    out = []
    if c['form'] not in FORMS:
        out.append(f"{c['role']}: unknown form {c['form']!r} (known: {', '.join(FORMS)})")
    elif c['form'] not in role['forms']:
        out.append(f"{c['role']}: a {c['role']} is written as {' or '.join(role['forms'])}, not {c['form']}")
    if not c['style']:
        out.append(f"{c['role']}: names no voice (`style:`)")
    else:
        vforms, _ = style_form(c['style'], pieces_dir)
        if vforms is None:
            out.append(f"{c['role']}: no voice {c['style']!r} in styles/ or framework/styles/")
        elif c['form'] in FORMS and c['form'] not in vforms:
            out.append(f"{c['role']}: voice {c['style']} writes {', '.join(vforms)}, not {c['form']} "
                       f"(add it to the voice's `form:` if it should)")
    if role['kind'] == 'file' and c['form'] in FORMS:
        if not c['body'].strip():
            out.append(f"{c['role']}: empty")
        if not FORMS[c['form']]['markdown'] and MARKDOWN.search(c['body']):
            out.append(f"{c['role']}: markdown in a plain-text {c['form']}")
        if c['role'] == 'note' and re.search(r'https?://', c['body']):
            out.append("note: carries a URL — the post's own link is added when the Note is posted")
    return out


def check(pieces_dir):
    """-> [(slug, problem)] across the corpus."""
    out = []
    for slug in sorted(os.listdir(pieces_dir)):
        d = os.path.join(pieces_dir, slug)
        if not os.path.isdir(d):
            continue
        if os.path.exists(os.path.join(d, LEGACY_NOTE)):
            out.append((slug, f'legacy {LEGACY_NOTE}: move it into a `note` companion (note.md with a form/style header)'))
        for c in companions(d):
            out += [(slug, p) for p in problems_of(c, d)]
        back = manifest_value(os.path.join(d, 'talk.yaml'), 'companion_of')
        if back:
            main = os.path.join(pieces_dir, back)
            tgt = manifest_block(os.path.join(main, 'publish.yaml'), 'companions').get('talk')
            if tgt != slug:
                out.append((slug, f'talk.yaml says companion_of: {back}, but {back} does not declare it as its talk'))
    return out


# ----------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('cmd', choices=['list', 'check'])
    ap.add_argument('slugs', nargs='*')
    ap.add_argument('--pieces', default=default_pieces())
    args = ap.parse_args(argv)

    if args.cmd == 'list':
        slugs = args.slugs or sorted(os.listdir(args.pieces))
        for slug in slugs:
            d = os.path.join(args.pieces, os.path.basename(slug.rstrip('/')))
            for c in companions(d) if os.path.isdir(d) else []:
                print(f"  {os.path.basename(d):36} {c['role']:5} {c['form'] or '?':6} "
                      f"{c['style'] or '?':22} {c['target']}")
        return 0

    found = check(args.pieces)
    for slug, p in found:
        print(f'  {slug:36} {p}')
    n = sum(len(companions(os.path.join(args.pieces, s))) for s in os.listdir(args.pieces)
            if os.path.isdir(os.path.join(args.pieces, s)))
    print(f"{n} companion(s); {len(found)} problem(s)")
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
