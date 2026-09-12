#!/usr/bin/env python3
"""
corpus.py — the desk's text namespaces, in one place.

For most of this desk's life there was one: `pieces/<slug>/`, flat, keyed by slug. That
breaks on a talk and its essay, which are the same argument in two forms and therefore
share a title — and a slug follows its title here. One of them had to answer to a name
that was not its own, and for eleven days it was the talk, still filed under the slug of
a title it had lost.

So there are two roots:

    pieces/<slug>/      a piece: draft.md + publish.yaml
    talks/<slug>/       a talk:  draft.md + talk.yaml, with its deck and slides

**A slug is unique within its namespace, not across the desk.** `love-is-not-a-metric-space`
names the essay in `pieces/` and the talk in `talks/`, and that is the point rather than a
collision to be worked around: the store already files them apart (`pieces/<slug>.json`
against `talks/<slug>/`, talk_bundle.py), and a reader meets one at /blog and the other at
/talks. (Eric, 2026-09-11: *"can it have the name love-is-not-a-metric-space and just be in
the talks directory?"*)

**Which means a bare slug can be ambiguous, and callers say what they want.** `find()` takes
a `prefer` — a companion pointer knows the role it is resolving, so the essay's
`companions: talk: love-is-not-a-metric-space` resolves into `talks/`, and the talk's
`companion_of: love-is-not-a-metric-space` resolves back into `pieces/`. A caller with no
preference gets pieces first, which is what every existing call site meant.

**The lease is not namespaced, deliberately.** `lease.py` keys on the slug, so the essay and
its talk share one lease. They are one argument and are nearly always edited together; a
second lock would mostly be a way to hold half of it.
"""

import os

PIECES = 'pieces'
TALKS = 'talks'
ROOTS = (PIECES, TALKS)

FRAMEWORK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def desk_root(start=None):
    """Up to the directory holding `pieces/` — the desk root. `talks/` is optional."""
    cur = os.path.abspath(start or os.environ.get('DESK_INSTANCE') or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(cur, PIECES)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())
        cur = parent


def root_dirs(root):
    """-> [(kind, path)] for each namespace that exists. kind is 'piece' or 'talk'."""
    out = []
    for name, kind in ((PIECES, 'piece'), (TALKS, 'talk')):
        d = os.path.join(root, name)
        if os.path.isdir(d):
            out.append((kind, d))
    return out


def texts(root, kinds=('piece', 'talk')):
    """-> [(slug, dir, kind)] across the namespaces asked for, sorted within each."""
    out = []
    for kind, d in root_dirs(root):
        if kind not in kinds:
            continue
        out += [(s, os.path.join(d, s), kind) for s in sorted(os.listdir(d))
                if os.path.isdir(os.path.join(d, s)) and not s.startswith('.')]
    return out


def find(root, ref, prefer='piece'):
    """A slug or a path -> a directory, or None.

    `prefer` decides which namespace is searched first when a slug names a text in both;
    the other is still searched, so a pointer to a text that exists only once resolves
    wherever it lives."""
    if os.sep in ref.rstrip(os.sep) or os.path.isdir(ref):
        cand = os.path.normpath(ref)
        return cand if os.path.isdir(cand) else None
    order = (TALKS, PIECES) if prefer == 'talk' else (PIECES, TALKS)
    for name in order:
        cand = os.path.join(root, name, ref)
        if os.path.isdir(cand):
            return cand
    return None


def kind_of(text_dir):
    """'talk' or 'piece', read from the directory itself rather than from its path."""
    return 'talk' if os.path.exists(os.path.join(text_dir, 'talk.yaml')) else 'piece'


def namespace_of(text_dir):
    """'pieces' or 'talks' — the root this text is filed under."""
    return os.path.basename(os.path.dirname(os.path.abspath(text_dir)))


def rel(root, text_dir):
    """'talks/love-is-not-a-metric-space' — how a text is named in prose and in a link."""
    return os.path.relpath(os.path.abspath(text_dir), os.path.abspath(root))


def slug_of(text_dir):
    return os.path.basename(os.path.abspath(text_dir).rstrip(os.sep))
