#!/usr/bin/env python3
"""tags.py — the desk's tag vocabulary, and which pieces carry which tags.

A tag cuts across the pieces the way a collection cannot: *practice* can name an essay
and a witness piece in two different books. So tags are a CONTROLLED VOCABULARY, not
free text. One list on the desk says what the tags are; a piece may carry only tags on
that list; and a new tag is added to the list deliberately, by a person, before any
piece carries it. Free-form tags drift — *practice*, *practices*, *the practice* — and
a tag page that splits one idea three ways is worse than no tag page.

WHERE THINGS LIVE (an instance, not the framework — no personal writing lives here):

    publishing/tags.yaml          the vocabulary. Override with --vocab or $DESK_TAGS.
    pieces/<slug>/publish.yaml    `tags:`, a block list of vocabulary tags.

    # publishing/tags.yaml
    tags:
      - tag: practice             # the id: lowercase, hyphenated, the URL segment
        label: Practice           # what a reader sees
        about: >-                 # what the tag is FOR — read by whoever proposes tags
          The daily doing of it: prayer, return, attention.

USAGE
    tags.py list                           the vocabulary, with how many pieces carry each
    tags.py show <piece>                   one piece's tags
    tags.py add <piece> <tag>...           add tags — each must already be in the vocabulary
    tags.py remove <piece> <tag>...        remove tags
    tags.py find <tag>                     pieces carrying <tag>
    tags.py find --none                    pieces carrying no tag (and pieces with no manifest)
    tags.py check                          every tag on every piece is in the vocabulary
    tags.py define <tag> --label L --about A    add a tag to the vocabulary

    <piece> is a slug or a path to the piece directory.
    --root DIR    the instance (default: the nearest ancestor holding pieces/)
    --vocab FILE  the vocabulary (default: <root>/publishing/tags.yaml)

WHY publish.yaml IS EDITED AS TEXT.  Every manifest on the desk is heavily commented —
settled-by notes, verification records, why a subtitle is what it is. A YAML round-trip
would strip every one of them. So `add` and `remove` rewrite the `tags:` block and
nothing else, and before writing they parse the result and confirm that every OTHER key
still reads back identical. A write that would change anything else is refused, not
attempted. A `tags:` block holding anything but a plain list (a standalone comment, a
nested mapping) is refused too: it was edited by hand, so it is left for a hand.

EXIT  0 ok | 1 check found problems | 2 nothing to check, or usage | 3 refused
"""
import os, re, sys, json, argparse, tempfile

import yaml

DEFAULT_VOCAB = os.path.join('publishing', 'tags.yaml')
TAG_ID = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
KEY_LINE = re.compile(r'^tags[ \t]*:(?P<rest>.*)$')
ITEM_LINE = re.compile(r'^(?:[ \t]*)-[ \t]+(?P<val>[^#\s](?:[^#]*[^#\s])?)?[ \t]*(?P<c>#.*)?$')


class Refused(Exception):
    """A write that was not safe to make. Nothing has been written."""


# ------------------------------------------------------------------ locating things
def instance_root(start=None):
    cur = os.path.abspath(start or os.environ.get('DESK_INSTANCE') or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(cur, 'pieces')):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())
        cur = parent


def vocab_path(root, explicit=None):
    return explicit or os.environ.get('DESK_TAGS') or os.path.join(root, DEFAULT_VOCAB)


def piece_dir(root, ref):
    """A slug or a path -> the piece directory. Refuses one that does not exist."""
    cand = ref if os.sep in ref.rstrip(os.sep) or os.path.isdir(ref) else os.path.join(root, 'pieces', ref)
    cand = os.path.normpath(cand)
    if not os.path.isdir(cand):
        raise Refused(f'no such piece: {ref}')
    return cand


def pieces(root):
    """-> [(slug, dir)] for every directory under pieces/."""
    pdir = os.path.join(root, 'pieces')
    if not os.path.isdir(pdir):
        return []
    return [(s, os.path.join(pdir, s)) for s in sorted(os.listdir(pdir))
            if os.path.isdir(os.path.join(pdir, s)) and not s.startswith('.')]


# ------------------------------------------------------------------ the vocabulary
def load_vocab(path):
    """-> (entries, problems). entries is an ordered dict tag -> {label, about}.

    Duplicates are checked on the LIST, which is why the file is a list of entries and
    not a mapping keyed by tag: PyYAML lets a repeated mapping key silently overwrite the
    first, so a keyed file could hold a duplicate that no load would ever show."""
    if not os.path.exists(path):
        return None, []
    try:
        with open(path, encoding='utf-8') as fh:
            doc = yaml.safe_load(fh) or {}
    except yaml.YAMLError as e:
        return {}, [f'{path}: not valid YAML ({e})']
    raw = doc.get('tags') if isinstance(doc, dict) else None
    if not isinstance(raw, list):
        return {}, [f'{path}: needs a top-level `tags:` list']
    entries, problems = {}, []
    for i, e in enumerate(raw, 1):
        if not isinstance(e, dict):
            problems.append(f'vocabulary entry {i}: not a mapping'); continue
        tag = e.get('tag')
        if not isinstance(tag, str) or not TAG_ID.match(tag):
            problems.append(f'vocabulary entry {i}: tag {tag!r} must be lowercase words joined by hyphens')
            continue
        if tag in entries:
            problems.append(f'vocabulary: {tag!r} is defined twice'); continue
        for field in ('label', 'about'):
            if not isinstance(e.get(field), str) or not e[field].strip():
                problems.append(f'vocabulary: {tag!r} has no {field}')
        entries[tag] = {'label': str(e.get('label') or '').strip(), 'about': str(e.get('about') or '').strip()}
    return entries, problems


def define(path, tag, label, about):
    """Append one entry to the vocabulary, as text, so its comments survive."""
    if not TAG_ID.match(tag):
        raise Refused(f'{tag!r}: a tag is lowercase words joined by hyphens, e.g. fear-of-god')
    if not label.strip() or not about.strip():
        raise Refused('a tag needs a --label (what a reader sees) and an --about (what it is for)')
    entries, problems = load_vocab(path)
    if problems:
        raise Refused('fix the vocabulary first:\n  ' + '\n  '.join(problems))
    if entries and tag in entries:
        raise Refused(f'{tag!r} is already in the vocabulary')
    q = lambda s: json.dumps(s.strip(), ensure_ascii=False)   # a JSON string is a YAML double-quoted scalar
    entry = f'  - tag: {tag}\n    label: {q(label)}\n    about: {q(about)}\n'
    if entries is None:
        old = ('# The tag vocabulary: the only tags a piece may carry. Add to it with\n'
               '# `tags.py define`, not by hand-typing a tag into a manifest.\n'
               'tags:\n')
    else:
        with open(path, encoding='utf-8') as fh:
            old = fh.read()
        if old and not old.endswith('\n'):
            old += '\n'
    new = old + entry
    after, problems = _load_text_vocab(new)
    if problems:
        raise Refused(f'{path}: appending would not parse ({"; ".join(problems)}); nothing written')
    before = dict(entries or {})
    if list(after) != list(before) + [tag] or any(after[t] != before[t] for t in before):
        # `tags:` is not the last block in the file, so an appended line would land
        # somewhere else. Say so rather than guess where the list ends.
        raise Refused(f'{path}: `tags:` is not the last block in the file, so an entry cannot be '
                      f'appended safely. Move the list to the end, or add the entry by hand.')
    _write_atomic(path, new)
    return after[tag]


def _load_text_vocab(text):
    fd, tmp = tempfile.mkstemp(suffix='.yaml')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(text)
        return load_vocab(tmp)
    finally:
        os.unlink(tmp)


# ------------------------------------------------------------------ a piece's tags
def manifest_path(pdir):
    return os.path.join(pdir, 'publish.yaml')


def read_manifest(pdir):
    p = manifest_path(pdir)
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as fh:
        return yaml.safe_load(fh) or {}


def tags_of(man):
    """-> (tags, problem). A malformed field is a problem, never silently an empty list."""
    if not man or 'tags' not in man or man['tags'] is None:
        return [], None
    t = man['tags']
    if not isinstance(t, list) or not all(isinstance(x, str) for x in t):
        return [], f'`tags:` must be a list of tag names, got {t!r}'
    dupes = sorted({x for x in t if t.count(x) > 1})
    return list(t), (f'repeats {", ".join(dupes)}' if dupes else None)


def _find_block(lines):
    """-> (start, end, key_comment, items) for the top-level `tags:` block, or None.

    items is [(value, comment)]. Raises Refused on a block this cannot rewrite faithfully."""
    for i, line in enumerate(lines):
        m = KEY_LINE.match(line.rstrip('\n'))
        if not m:
            continue
        rest = m.group('rest').strip()
        value, _, comment = rest.partition('#')
        value, comment = value.strip(), ('#' + comment if _ else '')
        items = []
        if value.startswith('['):                           # tags: [a, b]   # comment
            if not value.endswith(']'):
                raise Refused('`tags:` is a flow list that spans lines; edit it by hand')
            items = [(v.strip().strip('\'"'), '') for v in value[1:-1].split(',') if v.strip()]
            return i, i + 1, comment, items
        if value:
            raise Refused(f'`tags:` holds {value!r}, not a list; edit it by hand')
        end = i + 1
        while end < len(lines):
            ln = lines[end].rstrip('\n')
            if not ln.strip() or not (ln[:1] in ' \t' or ln.startswith('-')):
                break
            im = ITEM_LINE.match(ln)
            if not im or not im.group('val'):
                raise Refused(f'`tags:` holds a line this tool will not rewrite: {ln.strip()!r}. '
                              f'Edit the block by hand.')
            items.append((im.group('val').strip().strip('\'"'), (im.group('c') or '').strip()))
            end += 1
        return i, end, comment, items
    return None


def render_block(tags, key_comment='', comments=None):
    comments = comments or {}
    if not tags:
        return []
    out = ['tags:' + (f'   {key_comment}' if key_comment else '') + '\n']
    width = max(len(t) for t in tags)
    for t in tags:
        c = comments.get(t)
        out.append(f'  - {t}' + (' ' * (width - len(t)) + f'   {c}' if c else '') + '\n')
    return out


def set_tags(pdir, tags):
    """Rewrite the manifest's `tags:` block to exactly `tags`. Everything else is untouched.

    Returns True when the file changed. Raises Refused, writing nothing, when the edit
    cannot be made safely."""
    path = manifest_path(pdir)
    if not os.path.exists(path):
        raise Refused(f'{os.path.basename(pdir)} has no publish.yaml. Tags live in the manifest; '
                      f'create it first (templates/piece/publish.yaml).')
    with open(path, encoding='utf-8') as fh:
        old = fh.read()
    lines = old.splitlines(keepends=True)
    found = _find_block(lines)
    if found:
        start, end, key_comment, items = found
        comments = {v: c for v, c in items if c}
        block = render_block(tags, key_comment, comments)
        if not block and start > 0 and not lines[start - 1].strip() and (end >= len(lines) or not lines[end].strip()):
            start -= 1                                      # don't leave a double blank line behind
        new_lines = lines[:start] + block + lines[end:]
    else:
        block = render_block(tags)
        if not block:
            return False
        if lines and not lines[-1].endswith('\n'):
            lines[-1] += '\n'
        new_lines = lines + (['\n'] if lines and lines[-1].strip() else []) + block
    new = ''.join(new_lines)
    if new == old:
        return False

    try:
        before, after = yaml.safe_load(old) or {}, yaml.safe_load(new) or {}
    except yaml.YAMLError as e:
        raise Refused(f'{path}: the edit would not parse ({e}); nothing written')
    got = after.get('tags') or []
    rest_b = {k: v for k, v in before.items() if k != 'tags'}
    rest_a = {k: v for k, v in after.items() if k != 'tags'}
    if got != list(tags) or rest_a != rest_b:
        raise Refused(f'{path}: the edit would change more than `tags:`; nothing written. '
                      f'Edit the block by hand.')
    _write_atomic(path, new)
    return True


def _write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.tags-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(text)
        if os.path.exists(path):
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def ordered(tags, vocab):
    """Vocabulary order, so a manifest's list is the same whoever added the tags. A tag
    the vocabulary does not know keeps its place at the end, for `check` to report."""
    known = [t for t in vocab if t in tags] if vocab else []
    return known + [t for t in tags if t not in known]


# ------------------------------------------------------------------ the corpus
def title_of(pdir, man):
    if man and man.get('title'):
        return str(man['title'])
    try:
        with open(os.path.join(pdir, 'README.md'), encoding='utf-8') as fh:
            for line in fh:
                if line.startswith('# '):
                    return re.sub(r'\s*\*\(.*$', '', line[2:].strip()) or os.path.basename(pdir)
    except OSError:
        pass
    return os.path.basename(pdir)


def corpus(root):
    """-> [{slug, dir, title, manifest, tags, problem, published_at}] for every piece."""
    out = []
    for slug, d in pieces(root):
        try:
            man = read_manifest(d)
        except yaml.YAMLError as e:
            out.append({'slug': slug, 'dir': d, 'title': slug, 'manifest': False, 'tags': [],
                        'problem': f'publish.yaml does not parse ({e.__class__.__name__})',
                        'published_at': None})
            continue
        t, problem = tags_of(man)
        out.append({'slug': slug, 'dir': d, 'title': title_of(d, man), 'manifest': man is not None,
                    'tags': t, 'problem': problem,
                    'published_at': str(man.get('published_at'))[:10] if man and man.get('published_at') else None})
    return out


def check(root, vocab_file):
    """-> (problems, notes). A problem fails the check; a note is only worth knowing."""
    vocab, problems = load_vocab(vocab_file)
    notes = []
    rows = corpus(root)
    used = {}
    for r in rows:
        if r['problem']:
            problems.append(f"{r['slug']}: {r['problem']}")
        for t in r['tags']:
            used.setdefault(t, []).append(r['slug'])
    if vocab is None:
        if used:
            problems.append(f'pieces carry tags but there is no vocabulary at {vocab_file}')
        return problems, notes
    for t in sorted(used):
        if t not in vocab:
            problems.append(f"{t!r} is not in the vocabulary — carried by {', '.join(used[t])}")
    for t in vocab:
        if t not in used:
            notes.append(f'{t!r} is in the vocabulary but no piece carries it')
    return problems, notes


# ------------------------------------------------------------------ the CLI
def _row(r):
    date = r['published_at'] or 'unpublished'
    return f"  {r['slug']:44} {date:12} {r['title']}"


def main(argv=None):
    ap = argparse.ArgumentParser(prog='tags.py', description=__doc__.split('\n')[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--root')
    ap.add_argument('--vocab')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list')
    sub.add_parser('check')
    p = sub.add_parser('show'); p.add_argument('piece')
    for name in ('add', 'remove'):
        p = sub.add_parser(name); p.add_argument('piece'); p.add_argument('tags', nargs='+')
    p = sub.add_parser('find'); p.add_argument('tag', nargs='?'); p.add_argument('--none', action='store_true')
    p = sub.add_parser('define'); p.add_argument('tag')
    p.add_argument('--label', required=True); p.add_argument('--about', required=True)
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0

    root = instance_root(a.root)
    vfile = vocab_path(root, a.vocab)
    try:
        return _dispatch(a, root, vfile)
    except Refused as e:
        print(f'refused: {e}', file=sys.stderr)
        return 3


def _dispatch(a, root, vfile):
    if a.cmd == 'define':
        e = define(vfile, a.tag, a.label, a.about)
        print(f"defined {a.tag!r} ({e['label']}) in {os.path.relpath(vfile, root)}")
        return 0

    if a.cmd == 'check':
        problems, notes = check(root, vfile)
        rows = corpus(root)
        if not rows:
            print(f'tags: no pieces under {root}', file=sys.stderr)
            return 2
        for n in notes:
            print(f'  note  {n}')
        for p in problems:
            print(f'  FAIL  {p}')
        tagged = sum(1 for r in rows if r['tags'])
        print(f"{tagged} of {len(rows)} piece(s) tagged: "
              + (f'{len(problems)} problem(s)' if problems else 'every tag is in the vocabulary'))
        return 1 if problems else 0

    vocab, vproblems = load_vocab(vfile)
    if a.cmd in ('add', 'list') and vproblems:
        raise Refused('fix the vocabulary first:\n  ' + '\n  '.join(vproblems))

    if a.cmd == 'list':
        if vocab is None:
            print(f'no vocabulary yet at {os.path.relpath(vfile, root)} — `tags.py define` starts one')
            return 0
        counts = {}
        for r in corpus(root):
            for t in r['tags']:
                counts[t] = counts.get(t, 0) + 1
        for t, e in vocab.items():
            print(f"  {t:28} {counts.get(t, 0):3}  {e['label']} — {e['about']}")
        print(f'{len(vocab)} tag(s)')
        return 0

    if a.cmd == 'find':
        rows = corpus(root)
        if a.none:
            bare = [r for r in rows if r['manifest'] and not r['tags']]
            nomanifest = [r for r in rows if not r['manifest']]
            print(f'{len(bare)} piece(s) with no tag:')
            for r in bare:
                print(_row(r))
            if nomanifest:
                print(f'{len(nomanifest)} piece(s) with no publish.yaml (tags live there):')
                for r in nomanifest:
                    print(_row(r))
            return 0
        if not a.tag:
            raise Refused('find needs a tag, or --none')
        if vocab is not None and a.tag not in vocab:
            print(f'note: {a.tag!r} is not in the vocabulary', file=sys.stderr)
        hits = [r for r in rows if a.tag in r['tags']]
        print(f'{len(hits)} piece(s) tagged {a.tag!r}:')
        for r in hits:
            print(_row(r))
        return 0

    d = piece_dir(root, a.piece)
    slug = os.path.basename(d)
    man = read_manifest(d)
    current, problem = tags_of(man)
    if problem:
        raise Refused(f'{slug}: {problem}')

    if a.cmd == 'show':
        print(f"{slug}: {', '.join(current) if current else '(no tags)'}")
        return 0

    if a.cmd == 'add':
        if vocab is None:
            raise Refused(f'there is no vocabulary yet at {os.path.relpath(vfile, root)}. '
                          f'Define the tag first: tags.py define <tag> --label ... --about ...')
        unknown = [t for t in a.tags if t not in vocab]
        if unknown:
            raise Refused(f"not in the vocabulary: {', '.join(unknown)}. A new tag is added on "
                          f"purpose, with `tags.py define`, before any piece carries it.")
        new = ordered(list(dict.fromkeys(current + a.tags)), vocab)
    else:
        missing = [t for t in a.tags if t not in current]
        if missing:
            print(f"note: {slug} does not carry {', '.join(missing)}", file=sys.stderr)
        new = ordered([t for t in current if t not in a.tags], vocab)

    changed = set_tags(d, new)
    print(f"{slug}: {', '.join(new) if new else '(no tags)'}" + ('' if changed else '   (unchanged)'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
