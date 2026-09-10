#!/usr/bin/env python3
"""
test_suite.py — the desk's regression suite.  Run:  python3 framework/tools/test_suite.py

SAFETY, because this suite exists partly to replace a shell loop that was not safe:

  * It DELETES NOTHING.  Every generated file goes inside one `tempfile.TemporaryDirectory`,
    which the interpreter removes on exit.  There is no `rm` anywhere, and no path is ever
    interpolated into a shell command.
  * It makes NO NETWORK CALLS and drives NO BROWSER, so it can never touch a live post.
    Everything about "live" behaviour is exercised against a stubbed ProseMirror document.
  * It only READS the repository.  Nothing under `pieces/` or `framework/` is written.

The earlier version of this was a bash loop containing `rm -f $S/*` with `$S` unquoted — one
empty variable away from `rm -f /*`.  That is the reason the runner is a program now: a suite
that guards a publishing pipeline should not itself be the most dangerous thing in the repo.

WHAT IT COVERS — every case here is a bug that actually happened (2026-09-01):

  unit    quote/whitespace normalization, and the length-preservation split between the
          positional domain (`flatten_quotes`) and the equality domain (`H`)
  unit    three-way classification: push / pull / converged / conflict / unchanged
  unit    footnote ordering is REFERENCE order, not label order
  unit    escaped asterisks, bullet lists, adjacent-blockquote merging
  unit    footnote blocks render through the footnote path, not the paragraph path
  unit    the CDN image wrapper unwraps to the asset it points at
  unit    a pulled edit is verified by re-rendering; the one confirmed refusal (a
          whitespace run, which no markdown source can produce) is asserted, and no
          other refusal is asserted speculatively
  corpus  every piece renders; no undefined / duplicated / nested footnote refs; no
          unverified † notes left in any draft
  unit    the reader-side extractor, against canned markup (still no network)
  corpus  every live piece's header says it is live, not a draft
  corpus  every published piece matches its sealed baseline
  engine  the JS patcher's own suite (A–E) against every piece, via a stubbed editor
  unit    the pronoun sweep's sections E and F look INSIDE a scripture quotation — the four
          casing/bracket misses measured in *False Light* on 2026-09-07 are reproduced as a
          fixture and must all be listed; --strict warns on them and does not refuse
"""
import os, re, sys, json, shutil, subprocess, tempfile, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMEWORK = os.path.dirname(HERE)
sys.path.insert(0, HERE)


def _resolve_corpus():
    """Find the pieces.  Two layouts run this suite and the difference matters.

        instance   writing-desk/framework/tools/  ->  writing-desk/pieces/
        framework  scriptorium/tools/             ->  tools/fixtures/pieces/

    In a standalone framework checkout `tools/` sits at the REPO ROOT, so the
    instance path resolves to the parent of the checkout — outside it entirely.
    So don't compute the corpus, look for it: take the instance pieces only when
    they are actually on disk, and otherwise fall back to the fixtures that ship
    with the framework.  The fixture corpus exists so that the engine and
    converter checks still RUN in the framework repo, where the code they guard
    lives.  Skipping them there would leave the patcher's regression tests
    running only in a private repo that happens to hold drafts.
    """
    env = os.environ.get('DESK_PIECES')
    if env:
        return os.path.abspath(env), 'explicit ($DESK_PIECES)'
    instance = os.path.join(os.path.dirname(FRAMEWORK), 'pieces')
    if os.path.isdir(instance):
        return instance, 'instance'
    return os.path.join(HERE, 'fixtures', 'pieces'), 'fixture'


PIECES, CORPUS_KIND = _resolve_corpus()

from md_to_substack import (flatten_quotes, smarten_quotes, render_block,
                            render_footnote_block, strip_to_reader, render_reader,
                            read_manifest, parse_blocks, manifest_gate,
                            render_marks, marks_in, mark_keys)
from substack_sync import (H, HM, three_way, align, canonical_image_url,
                           reader_to_source_map, edit_block_source, load_baseline,
                           baseline_has_marks, write_baseline, draft_state)
from substack_verify import live_blocks, extract_post, header_drift, mark_drift
from piece_header import rewrite as header_rewrite
from check_links import extract as extract_links, unrenderable as unrenderable_links
import check_pronouns
import md_to_marp

PASS, FAIL, SKIP = [], [], []


def check(name, ok, detail=''):
    (PASS if ok else FAIL).append((name, detail))
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not ok else ''))


def skip(name, why):
    SKIP.append((name, why))
    print(f"  skip  {name}   ({why})")


# ---------------------------------------------------------------- unit: normalization
def unit_normalization():
    print("\n-- normalization -------------------------------------------------")
    s = 'the “word” it’s'
    check('flatten_quotes is length-preserving',
          len(flatten_quotes(s)) == len(s),
          'a positional offset computed on it must index the real text')
    check('H ignores quote style', H('the "x" y') == H('the “x” y'))
    check('H ignores whitespace runs', H('it.  The') == H('it. The'),
          'a double space describes a block no draft can produce')
    check('H still sees real differences', H('a b') != H('a c'))
    check('H ignores leading/trailing space', H('  a b  ') == H('a b'))
    check('smarten opens then closes', smarten_quotes('"a" b') == '“a” b')
    check('smarten handles an apostrophe mid-word', smarten_quotes("it's") == 'it’s')


# ---------------------------------------------------------------- unit: link extraction
def unit_link_extraction():
    """A cross-link must be seen in every form a draft can carry it.

    The checker read only [text](url) until 2026-09-02. The house cites a published
    sibling as an autolink inside a footnote, so the one form it could not see was
    the one the convention uses — and a 404 shipped into a draft behind that blind
    spot.
    """
    print("\n-- link extraction -----------------------------------------------")
    U = 'https://example.com/p/a'
    check('inline [text](url)', extract_links(f'see [A]({U}) here') == {U})
    check('autolink <url>', extract_links(f'[^a]: *A* — <{U}>.') == {U},
          'how a footnote cites a live sibling — the form that was invisible')
    check('bare url', extract_links(f'watch {U} now') == {U})
    check('trailing period is not part of the url',
          extract_links(f'it is at {U}.') == {U},
          'otherwise a sentence-final url reports a false dead')
    check('inline and autolink de-duplicate',
          extract_links(f'[A]({U}) and <{U}>') == {U},
          'one fetch, not two')
    check('two distinct urls both survive',
          extract_links(f'[A]({U}) then <{U}b>') == {U, U + 'b'})
    check('emphasis markers are stripped from a bare url',
          extract_links(f'see *{U}*') == {U})
    check('no url yields nothing', extract_links('nothing here') == set())

    # ...and seeing a form is not the same as the pipeline being able to RENDER it. The
    # converter emits [text](url) and nothing else, so a checker that merely resolves an
    # autolink is more permissive than the thing it guards — which is how three sibling
    # citations passed a green check and would have published as angle-bracketed strings.
    hdr = '# t\n\n*head <https://example.com/h>*\n\n---\n\n'
    U = 'https://example.com/p/a'
    forms = lambda t: {u: f for u, f in unrenderable_links(t)}
    check('an autolink in the body is flagged as unrenderable',
          forms(hdr + f'x <{U}> y').get(U) == 'autolink <url>')
    check('a bare url in the body is flagged',
          forms(hdr + f'x {U} y').get(U) == 'bare url',
          'measured live: Substack does not autolink one, it publishes as plain text')
    check('an inline [text](url) is NOT flagged', not forms(hdr + f'x [A]({U}) y'))
    check('a url written both ways is NOT flagged',
          not forms(hdr + f'[A]({U}) and <{U}>'),
          'the inline form is present, so it renders')
    check('a url in the scaffold header is NOT flagged',
          not any(u == 'https://example.com/h' for u, _f in unrenderable_links(hdr + 'body')),
          'the header is dropped before publication and never reaches a reader')


# ---------------------------------------------------------------- unit: CLI dispatch
def unit_cli_dispatch():
    """Every command the CLI accepts must resolve to a function that exists.

    This is here because on 2026-09-01 `substack_sync.py images` crashed with
    `NameError: name 'cmd_images' is not defined` — the dispatch branch shipped without its
    handler. It was the scraper half of the recompose image gate, so the gate added that day to
    stop a recompose destroying a live image could not be run at all. Nothing caught it, because
    nothing was checking that the CLI's own table was complete.
    """
    print("\n-- CLI dispatch is complete --------------------------------------")
    src = open(os.path.join(HERE, 'substack_sync.py')).read()
    branches = set(re.findall(r"cmd == '([a-z-]+)'", src))
    called = set(re.findall(r'\b(cmd_[a-z_]+)\(', src))
    defined = set(re.findall(r'^def (cmd_[a-z_]+)', src, re.M))
    check('every dispatched handler is defined', not (called - defined),
          f'undefined: {sorted(called - defined)}')
    check('every documented command has a branch', branches,
          f'found {len(branches)} branches')
    missing_branch = sorted(b for b in branches
                            if f"cmd_{b.replace('-', '_')}(" not in src)
    check('every branch names a handler', not missing_branch, f'{missing_branch}')


# ---------------------------------------------------------------- unit: piece resolution
def unit_piece_resolution(tmp):
    """A failure to resolve a piece must name its own cause.

    On 2026-09-02 `substack_verify --fresh forking-paths` reported a freshly published essay as
    "no public_url — not published". The bare slug resolved to no directory, an absent
    publish.yaml read as an empty manifest, and the empty manifest read as unpublished. Three
    different causes printed one message, and the message named the wrong one — which is worse
    than silence, because it gets believed. This asserts they stay distinguishable.
    """
    print("\n-- piece resolution names its own failure ------------------------")
    sys.path.insert(0, HERE)
    from substack_verify import resolve_piece

    repo = os.path.join(tmp, 'repo')
    os.makedirs(os.path.join(repo, 'pieces', 'live'))
    os.makedirs(os.path.join(repo, 'pieces', 'composed'))
    os.makedirs(os.path.join(repo, 'pieces', 'bare'))
    open(os.path.join(repo, 'pieces', 'live', 'publish.yaml'), 'w').write(
        'title: L\npublic_url: https://example.invalid/p/l\n')
    open(os.path.join(repo, 'pieces', 'composed', 'publish.yaml'), 'w').write(
        'title: C\npost_url: https://example.invalid/publish/post/1\n')

    d, url, why = resolve_piece(repo, 'live')
    check('a bare slug resolves', url and why is None, f'url={url} why={why}')
    d2, url2, _ = resolve_piece(repo, os.path.join(repo, 'pieces', 'live'))
    check('a path resolves to the same piece', d2 == d, f'{d2} != {d}')

    _, url3, why3 = resolve_piece(repo, 'composed')
    check('composed-but-unpublished says so', url3 is None and 'not published' in (why3 or ''), str(why3))
    _, url4, why4 = resolve_piece(repo, 'bare')
    check('missing publish.yaml says so', url4 is None and 'never composed' in (why4 or ''), str(why4))
    _, url5, why5 = resolve_piece(repo, 'nope')
    check('a bad slug says no such piece', url5 is None and 'no such piece' in (why5 or ''), str(why5))
    check('the three failures are distinguishable', len({why3, why4, why5}) == 3,
          'a shared message is what caused the 2026-09-02 misdiagnosis')


# ---------------------------------------------------------------- unit: three-way
def unit_three_way():
    print("\n-- three-way classification --------------------------------------")
    base = ['A', 'B', 'C', 'D', 'E']
    draft = ['A', 'B2', 'C', 'D2', 'E2']     # B and D and E moved in the draft
    live = ['A', 'B', 'C2', 'D2', 'E3']      # C and D and E moved live
    rows, structural = three_way('body', base, draft, live)
    got = {r['baseIdx']: r['state'] for r in rows}
    check('unchanged when neither side moved', got[0] == 'unchanged', str(got))
    check('push when only the draft moved', got[1] == 'push', str(got))
    check('pull when only live moved', got[2] == 'pull', str(got))
    check('converged when both made the same edit', got[3] == 'converged', str(got))
    check('conflict when both moved differently', got[4] == 'conflict', str(got))
    check('no structural rows for a same-length change', structural == [], str(structural))

    # The second verdict. Every row above has IDENTICAL text on all three sides here, so
    # `state` is `unchanged` throughout and only `markState` can carry the finding — which is
    # exactly the shape of the bug: a block whose words never moved and whose italics did.
    same = ['T', 'T', 'T', 'T', 'T']
    mrows, _st = three_way('body', same, same, same,
                           base_m=['A', 'B', 'C', 'D', 'E'],
                           draft_m=['A', 'B2', 'C', 'D2', 'E2'],
                           live_m=['A', 'B', 'C2', 'D2', 'E3'])
    check('a text-identical row still classifies its marks',
          all(r['state'] == 'unchanged' for r in mrows), str([r['state'] for r in mrows]))
    mgot = {r['baseIdx']: r['markState'] for r in mrows}
    check('marks unchanged / push / pull / converged / conflict',
          [mgot[i] for i in range(5)] == ['unchanged', 'push', 'pull', 'converged', 'conflict'],
          str(mgot))

    # UNKNOWN IS NOT UNCHANGED. 34 baselines were sealed before marks were tracked, and a
    # tool that answers "no formatting change" when it has nothing to compare is the failure
    # being fixed, wearing a different hat.
    urows, _u = three_way('body', same, same, same)
    check('no mark data anywhere reads as unknown, never unchanged',
          all(r['markState'] == 'unknown' for r in urows), str([r['markState'] for r in urows]))
    prows, _p2 = three_way('body', same, same, same,
                           base_m=None, draft_m=['A'] * 5, live_m=['A'] * 5)
    check('a text-only BASELINE reads as unknown even when both live sides have marks',
          all(r['markState'] == 'unknown' for r in prows), str([r['markState'] for r in prows]))

    pairs, added, removed = align(['A', 'B', 'C'], ['A', 'B', 'X', 'C'])
    check('align reports an inserted row', added == [2] and removed == [],
          f'added={added} removed={removed}')


# ---------------------------------------------------------------- unit: converter
def unit_converter(tmp):
    print("\n-- converter -----------------------------------------------------")
    check('escaped asterisks survive as literal text',
          strip_to_reader(render_block(r'F\*\*k you', '.')) == 'F**k you')
    check('real emphasis still becomes markup',
          '<em>' in render_block('a *real* emphasis', '.'))
    check('escaped asterisks do not open emphasis',
          '<strong>' not in render_block(r'F\*\*k a F\*\*k b', '.'))

    ul = render_block('- one\n- two\n  continued', '.')
    check('a bullet list renders as a list', ul.startswith('<ul>') and ul.count('<li>') == 2, ul[:60])
    check('a list item absorbs its indented continuation', 'two continued' in ul, ul[:80])

    fn = render_footnote_block('[^x]: the note *body*', '.')
    check('a footnote renders without its label',
          fn is not None and strip_to_reader(fn) == 'the note body', repr(fn))
    check('a footnote through the paragraph path keeps its label (the bug)',
          '[[FNx]]' in render_block('[^x]: the note', '.'),
          'render_block must not be used for footnotes')

    # adjacent blockquotes merge, because ProseMirror merges them on paste
    d = os.path.join(tmp, 'bq')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('x\n\n---\n\nbody\n\n> one\n\n> two\n\ntail\n')
    with open(os.path.join(d, 'publish.yaml'), 'w') as f:
        f.write('title: t\nsubtitle: s\n')
    body, fns, res, iss = render_reader(d)
    merged = [b for b in body if b.startswith('one')]
    check('adjacent blockquotes merge into one block',
          len(merged) == 1 and merged[0] == 'onetwo', str(body))


def unit_footnote_continuation(tmp):
    """A footnote's continuation paragraph must stay in the footnote.

    Before 2026-09-02 it did not: the block splitter made it a separate block, it failed
    the `[^id]:` match, and it published as an ordinary BODY paragraph in place. Content
    relocated rather than dropped, which is worse — the output reads as deliberate, the
    paragraph count merely goes up by one, and nothing refuses.
    """
    print("\n-- footnote continuation -----------------------------------------")
    d = os.path.join(tmp, 'fncont')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('t\n\n---\n\n## I\n\nnote here.[^a] and here.[^b]\n\n'
                '[^a]: first of A.\n\n    indented second of A CONT_KEPT.\n\n'
                '[^b]: first of B.\n\nunindented after B CONT_LOOSE.\n')
    with open(os.path.join(d, 'publish.yaml'), 'w') as f:
        f.write('title: t\nsubtitle: s\n')
    blocks, ordered, _stripped, _res, _unv, issues, _src = parse_blocks(d)
    fns = dict(ordered)
    body = ' '.join(blocks)
    check('an indented continuation stays in its footnote',
          'CONT_KEPT' in fns.get('a', ''), repr(fns.get('a')))
    check('an indented continuation does NOT leak into the body',
          'CONT_KEPT' not in body,
          'the 2026-09-02 bug: it published in place, as body text')
    check('an unindented paragraph after a definition stays body text',
          'CONT_LOOSE' in body,
          'it cannot be claimed as a continuation — definitions sit mid-document here')
    check('and that ambiguous case is reported, not silent',
          any(n == 'b' for n, _t in issues.get('orphaned', [])),
          'silence is how a continuation gets written wrong and never noticed')

    # ...but a divider or heading after a definition is the ORDINARY shape here, and warning on
    # it fired on 11 of 27 pieces — a warning that always fires stops being read.
    d2 = os.path.join(tmp, 'fnquiet')
    os.makedirs(d2, exist_ok=True)
    with open(os.path.join(d2, 'draft.md'), 'w') as f:
        f.write('t\n\n---\n\n## I\n\nnote.[^a]\n\n[^a]: the note.\n\n---\n\n## II\n\ntail.\n')
    with open(os.path.join(d2, 'publish.yaml'), 'w') as f:
        f.write('title: t\nsubtitle: s\n')
    _b2, _o2, _s2, _r2, _u2, issues2, _x2 = parse_blocks(d2)
    check('a divider or heading after a definition does NOT warn',
          not issues2.get('orphaned'),
          f"would fire on the ordinary shape: {issues2.get('orphaned')}")


def unit_footnote_order(tmp):
    print("\n-- footnote ordering ---------------------------------------------")
    d = os.path.join(tmp, 'fnorder')
    os.makedirs(d, exist_ok=True)
    # labels sort as 103 < 999 < zzz, but they are CITED in the order zzz, 999, 103
    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('x\n\n---\n\nfirst[^zzz] second[^999] third[^103]\n\n'
                '[^103]: one-oh-three\n\n[^999]: nine-nine-nine\n\n[^zzz]: zed\n')
    with open(os.path.join(d, 'publish.yaml'), 'w') as f:
        f.write('title: t\nsubtitle: s\n')
    body, fns, res, iss = render_reader(d)
    check('footnotes emit in first-reference order, not label order',
          fns == ['zed', 'nine-nine-nine', 'one-oh-three'], str(fns))
    check('no spurious footnote issues', not any(iss[k] for k in ('undefined', 'duplicated', 'nested')),
          str(iss))

    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('x\n\n---\n\na[^a] b[^a]\n\n[^a]: dup\n')
    _b, _f, _r, iss2 = render_reader(d)
    check('a footnote cited twice is reported', iss2['duplicated'] == ['a'], str(iss2))

    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('x\n\n---\n\na[^a]\n\n[^a]: see [^b]\n\n[^b]: other\n')
    _b, _f, _r, iss3 = render_reader(d)
    check('a footnote referenced inside a footnote is reported',
          'b' in iss3['nested'], str(iss3))


def unit_pull_verification():
    print("\n-- pull verification ---------------------------------------------")
    src = 'take this* but *is this for us* — asked'
    src = 'not *can I take this* but *is this for us* — asked upward'
    reader = strip_to_reader(render_block(src, '.'))
    out, note = edit_block_source(src, reader, reader.replace('for us', 'for me'), '.')
    check('a pulled edit lands inside emphasis without eating the markers',
          out is not None and '*is this for me*' in out, f'{note}: {out!r}')

    m = reader_to_source_map(src, reader)
    check('the offset map is monotonic', all(m[i] <= m[i + 1] for i in range(len(reader))))

    # The genuinely unrepresentable case, and the real one: a double space. strip_to_reader
    # collapses whitespace runs, so no markdown source can render two spaces — the verifier
    # must refuse rather than write something that does not round-trip. This is the refusal
    # that correctly fired on `Both Ends of the Leash`.
    bad, note2 = edit_block_source(src, reader, reader.replace('for us', 'for  us'), '.')
    check('an edit that cannot round-trip is refused, not guessed',
          bad is None, f'expected a refusal, got {note2}')

    # A plain edit with no markup in play must APPLY — the refusals above are not the
    # verifier being timid, they are it declining specific things it cannot round-trip.
    plain = 'a plain source sentence here'
    ok2, note3 = edit_block_source(plain, plain, 'a plain replacement sentence here', '.')
    check('a plain, representable edit still applies',
          ok2 == 'a plain replacement sentence here', f'{note3}: {ok2!r}')



def unit_images():
    print("\n-- images --------------------------------------------------------")
    s3 = 'https://substack-post-media.s3.amazonaws.com/public/images/abc_1536x1024.png'
    cdn = ('https://substackcdn.com/image/fetch/$s_!x,w_1456,c_limit/'
           + s3.replace(':', '%3A').replace('/', '%2F'))
    check('the CDN wrapper unwraps to the asset it points at',
          canonical_image_url(cdn) == s3, canonical_image_url(cdn))
    check('a bare asset URL is unchanged', canonical_image_url(s3) == s3)


# ---------------------------------------------------------------- unit: live extraction
def unit_live_extraction():
    """The reader-side extractor, offline.

    substack_verify fetches live pages; these checks feed it canned markup instead, so
    the suite keeps its no-network promise while still guarding the parser. Every case
    below is a shape that produced a FALSE DRIFT against the real corpus before it was
    fixed -- a verifier that cries wolf is worse than none, because the first thing
    anyone does with a noisy check is stop reading it.
    """
    print("\n-- live-page extraction (offline) --------------------------------")

    # A list is ONE block. Substack nests <li><p>..</p></li>; if the inner </p> closes
    # the buffer, one list becomes N blocks and every piece with a list reports drift.
    b, f, bm, fm = live_blocks('<ul><li><p>alpha</p></li><li><p>beta</p></li></ul>')
    check('a bullet list extracts as a single block', b == ['alphabeta'], repr(b))

    # Same bug, different tag -- and adjacent quotes merge, as the draft renderer merges them.
    b, _f, _bm, _fm = live_blocks('<blockquote><p>one</p></blockquote><blockquote><p>two</p></blockquote>')
    check('adjacent blockquotes merge into one block', b == ['onetwo'], repr(b))

    b, _f, _bm, _fm = live_blocks('<p>plain</p><blockquote><p>q</p></blockquote><p>after</p>')
    check('a lone blockquote does not swallow the paragraph after it',
          b == ['plain', 'q', 'after'], repr(b))

    # Furniture Substack injects into the body: not prose, must not count as drift.
    b, _f, _bm, _fm = live_blocks('<p>real</p><div class="subscription-widget-wrap-editor">'
                       '<div class="subscription-widget"><div class="preamble">'
                       '<p class="cta-caption">Thanks for reading! Subscribe.</p>'
                       '</div></div></div><p>also real</p>')
    check('a subscribe widget is not counted as body', b == ['real', 'also real'], repr(b))

    b, _f, _bm, _fm = live_blocks('<div class="captioned-image-container"><figure>'
                       '<img src="x"><figcaption>a caption</figcaption></figure></div><p>text</p>')
    check('an image and its caption are not body', b == ['text'], repr(b))

    # Void tags inside a skipped subtree once wedged the parser open forever: <img>,
    # <source> and <hr> have no end tag, so a depth counter that increments on them
    # never comes back down and the whole rest of the post vanishes.
    b, _f, _bm, _fm = live_blocks('<div class="captioned-image-container"><picture>'
                       '<source srcset="a"><img src="b"></picture></div><hr><p>survives</p>')
    check('void tags in skipped subtrees do not wedge the parser', b == ['survives'], repr(b))

    # The superscript marker is not prose; the footnote body is not body.
    b, f, bm, fm = live_blocks('<p>Sentence<a class="footnote-anchor" href="#footnote-1">1</a> ends.</p>'
                       '<div class="footnote"><a class="footnote-number">1</a>'
                       '<div class="footnote-content"><p>The note.</p></div></div>')
    check('a footnote anchor leaves no digit in the prose', b == ['Sentence ends.'], repr(b))
    check('footnote content is captured separately', f == ['The note.'], repr(f))

    # ---- marks: the layer reader-text cannot see --------------------------------------
    # Everything above compares TEXT. Wrapping a word already in the post in <em> changes
    # none of it, so none of the checks above can fail on it. These can.
    _b, _f, bm, fm = live_blocks(
        '<p>Plain <em>satsang</em> and <strong>bold</strong> '
        '<a href="https://elmuffin.substack.com/p/x">a link</a>.</p>')
    check('em, strong and link are each enumerated from the live page',
          mark_keys(bm[0]) == [('em', 'satsang', ''), ('strong', 'bold', ''),
                               ('link', 'a link', 'https://elmuffin.substack.com/p/x')],
          repr(mark_keys(bm[0])))

    # THE FALSE PASS, in one assertion. Same reader-text on both sides, one <em> apart:
    # the digest cannot tell them apart, and the mark scan must.
    plain, italic = '<p>He sat in the satsang.</p>', '<p>He sat in the <em>satsang</em>.</p>'
    pb, _pf, pbm, _pfm = live_blocks(plain)
    ib, _if, ibm, _ifm = live_blocks(italic)
    check('an italics-only difference is INVISIBLE to the text digest',
          H(pb[0]) == H(ib[0]), f'{pb[0]!r} vs {ib[0]!r}')
    check('an italics-only difference IS visible to the mark scan',
          mark_keys(pbm[0]) == [] and mark_keys(ibm[0]) == [('em', 'satsang', '')],
          f'{mark_keys(pbm[0])} vs {mark_keys(ibm[0])}')

    # A RUN IS A SPAN, NOT AN ELEMENT. Substack serves `**a _b_ c**` back as three <strong>
    # elements around the em; the converter emits one <strong> wrapping it. Compared
    # element-by-element that is drift on every bold-containing-an-italic in the corpus --
    # 8 pieces of 34 on the first sweep, 2026-09-09, not one a real difference.
    _b1, _f1, split, _m1 = live_blocks('<p><strong>There is no </strong><em><strong>toward'
                                       '</strong></em><strong> in the index.</strong></p>')
    _b2, _f2, whole, _m2 = live_blocks('<p><strong>There is no <em>toward</em> in the '
                                       'index.</strong></p>')
    check('a bold split around an italic is one run, not three',
          mark_keys(split[0]) == mark_keys(whole[0])
          == [('strong', 'There is no toward in the index.', ''), ('em', 'toward', '')],
          repr(mark_keys(split[0])))

    # The two <a> tags that are not links. A footnote superscript counted as a link would
    # put a phantom run in every footnoted block of every piece in the corpus.
    _b3, _f3, anch, fnm = live_blocks(
        '<p>Sentence<a class="footnote-anchor" href="#footnote-1">1</a> ends.</p>'
        '<div class="footnote"><a class="footnote-number" href="#footnote-anchor-1">1</a>'
        '<div class="footnote-content"><p>The <em>note</em>.</p></div></div>')
    check('a footnote anchor is not counted as a link', mark_keys(anch[0]) == [], repr(anch))
    check('a footnote body\'s own italics are collected',
          mark_keys(fnm[0]) == [('em', 'note', '')], repr(fnm))

    # Substack curls quotes on paste; the draft has straight ones. A run must not report
    # drift for that -- the same flattening the text digest has always applied.
    _b4, _f4, cur, _m4 = live_blocks('<p>She said <em>\u201cno\u201d</em> once.</p>')
    check('a run with curled quotes compares straight',
          mark_keys(cur[0]) == [('em', '"no"', '')], repr(mark_keys(cur[0])))

    # A page that shipped no post (login wall, layout change) must read as "could not
    # check", never as an empty post that trivially matches nothing.
    check('a page with no _preloads yields no post',
          extract_post('<html><body>nothing here</body></html>') is None)


def unit_mark_drift(tmp):
    """The regression the whole chain used to pass.

    A draft and a live post whose READER-TEXT is identical block for block and footnote for
    footnote, differing only in one <em>. Every digest on this desk reports MATCH; the run
    comparison must report drift, and must say it is FORMATTING drift rather than sending
    the reader to look for a word that changed.

    Measured on `rising-after-falls`, 2026-09-09: after italicising two words the
    regenerated surgical patch was byte-identical in size to the previous one (29,782
    bytes), reported `unchanged`, and applied nothing.
    """
    print("\n-- marks: a formatting-only change is caught ----------------------")
    d = os.path.join(tmp, 'marks'); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'publish.yaml'), 'w') as f:
        f.write('title: A Piece\nsubtitle: With one italic\n')
    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('*Draft*\n\n---\n\n'
                'He sat in the *satsang* and listened.[^1]\n\n'
                'A plain closing line.\n\n'
                '[^1]: The word is *satsang*, a sitting-together.\n')

    body, fns, _r, _i = render_reader(d)
    dbm, dfm, offsets_ok = render_marks(d)
    check('the mark scan stays 1:1 with render_reader',
          len(dbm) == len(body) and len(dfm) == len(fns), f'{len(dbm)}/{len(body)} {len(dfm)}/{len(fns)}')
    check('a run offset indexes the reader-text it was scanned from', offsets_ok)
    check('the draft\'s own italic is seen',
          mark_keys(dbm[0]) == [('em', 'satsang', '')], repr(mark_keys(dbm[0])))

    # the live post: same words, no italics anywhere
    live_html = ('<p>He sat in the satsang and listened.'
                 '<a class="footnote-anchor" href="#footnote-1">1</a></p>'
                 '<p>A plain closing line.</p>'
                 '<div class="footnote"><a class="footnote-number">1</a>'
                 '<div class="footnote-content"><p>The word is satsang, a sitting-together.</p>'
                 '</div></div>')
    lb, lf, lbm, lfm = live_blocks(live_html)
    check('the live page and the draft agree on every block of TEXT',
          [H(x) for x in lb] == [H(x) for x in body] and [H(x) for x in lf] == [H(x) for x in fns],
          f'live={lb} draft={body}')

    drift = (mark_drift(lbm, dbm, lb, body, 'block')
             + mark_drift(lfm, dfm, lf, fns, 'footnote', base=1))
    check('the mark scan catches what the digest cannot', len(drift) == 2, repr(drift))
    check('the report names the block, the kind, and the run',
          any('block #0' in x and 'emphasis' in x and 'satsang' in x for x in drift), repr(drift))
    check('a footnote-only formatting change is caught too',
          any('footnote #1' in x for x in drift), repr(drift))

    # and the converse: identical formatting is silence, not noise
    same = live_blocks('<p>He sat in the <em>satsang</em> and listened.'
                       '<a class="footnote-anchor" href="#footnote-1">1</a></p>'
                       '<p>A plain closing line.</p>')
    check('matching formatting reports nothing',
          mark_drift(same[2], dbm, same[0], body, 'block') == [], repr(mark_drift(same[2], dbm, same[0], body, 'block')))

    # a link whose text is right and whose target is wrong is its OWN kind of drift
    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('*Draft*\n\n---\n\nSee [the essay](https://elmuffin.substack.com/p/right).\n')
    body2, _f2, _r2, _i2 = render_reader(d)
    dbm2, _dfm2, _ok2 = render_marks(d)
    lb2, _lf2, lbm2, _lfm2 = live_blocks(
        '<p>See <a href="https://elmuffin.substack.com/p/wrong">the essay</a>.</p>')
    d2 = mark_drift(lbm2, dbm2, lb2, body2, 'block')
    check('a wrong href is reported as a link target, not as emphasis',
          len(d2) == 1 and 'link target' in d2[0] and 'wrong' in d2[0] and 'right' in d2[0], repr(d2))


def unit_sync_baseline_marks(tmp):
    """The sync baseline's second domain.

    substack_sync's baseline recorded hashes of reader-text and nothing else, so a block
    whose only difference was an <em> hashed identically on both sides and the three-way
    called it `unchanged`. Same false pass as substack_verify and substack_repatch had, one
    tool over — and worse here, because a seal writes the mistake down and every later sync
    measures against a state that was never true.
    """
    print("\n-- sync baseline: marks are recorded and aligned ------------------")
    d = os.path.join(tmp, 'syncmarks'); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'publish.yaml'), 'w') as f:
        f.write('title: A Piece\nsubtitle: With one italic\n')
    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('*Draft*\n\n---\n\nHe sat in the *satsang* and listened.[^1]\n\n'
                '[^1]: A note with *emphasis*.\n')

    st = draft_state(d)
    check('draft_state carries the mark runs beside the text',
          len(st['bodyMarks']) == len(st['body']) and len(st['fnsMarks']) == len(st['fns'])
          and st['bodyMarks'][0], f"{st['bodyMarks']} {st['fnsMarks']}")

    # the hash must move when only the formatting does
    plain = os.path.join(tmp, 'syncplain'); os.makedirs(plain, exist_ok=True)
    shutil.copy2(os.path.join(d, 'publish.yaml'), plain)
    with open(os.path.join(plain, 'draft.md'), 'w') as f:
        f.write('*Draft*\n\n---\n\nHe sat in the satsang and listened.[^1]\n\n'
                '[^1]: A note with emphasis.\n')
    sp = draft_state(plain)
    check('the TEXT hash is identical across a formatting-only difference',
          [H(t) for t in st['body']] == [H(t) for t in sp['body']]
          and [H(t) for t in st['fns']] == [H(t) for t in sp['fns']])
    check('a non-empty footnote list is actually under test',
          len(st['fns']) == 1 and len(sp['fns']) == 1, f"{len(st['fns'])} {len(sp['fns'])}")
    check('the MARK hash is not, in the body',
          [HM(r) for r in st['bodyMarks']] != [HM(r) for r in sp['bodyMarks']])
    check('the MARK hash is not, in a footnote',
          [HM(r) for r in st['fnsMarks']] != [HM(r) for r in sp['fnsMarks']])
    check('an unformatted block hashes to the empty signature',
          all(x == HM([]) for x in [HM(r) for r in sp['bodyMarks']]))

    # a sealed baseline records both; a legacy one records neither and says so
    write_baseline(d, st['title'], st['subtitle'],
                   [H(t) for t in st['body']], [H(t) for t in st['fns']], 'test',
                   body_m=[HM(r) for r in st['bodyMarks']], fns_m=[HM(r) for r in st['fnsMarks']])
    base = load_baseline(d)
    check('a sealed baseline records the mark hashes', baseline_has_marks(base), str(sorted(base)))

    write_baseline(d, st['title'], st['subtitle'],
                   [H(t) for t in st['body']], [H(t) for t in st['fns']], 'legacy')
    check('a text-only baseline is detectable as such', not baseline_has_marks(load_baseline(d)))

    # MISALIGNED mark lists are refused rather than written: a mark list one row short would
    # attach every block's formatting to its neighbour's, which is the precise failure the
    # row alignment exists to prevent.
    write_baseline(d, st['title'], st['subtitle'],
                   [H(t) for t in st['body']], [H(t) for t in st['fns']], 'misaligned',
                   body_m=[], fns_m=[])
    check('a mark list that does not line up 1:1 with the rows is not recorded',
          not baseline_has_marks(load_baseline(d)))


def unit_manifest_gate(tmp):
    print("\n-- manifest gate: a post needs a title and a subtitle ---------------")
    d = os.path.join(tmp, 'gate'); os.makedirs(d, exist_ok=True)
    man = os.path.join(d, 'publish.yaml')
    with open(man, 'w') as f:
        f.write('title: T\nfootnotes: native\n')
    errs, _w = manifest_gate(d)
    check('a manifest with no subtitle is refused', errs == ['publish.yaml has no subtitle'], str(errs))
    with open(man, 'w') as f:
        f.write('title: T\nsubtitle:    \n')
    errs, _w = manifest_gate(d)
    check('a blank subtitle counts as missing', errs == ['publish.yaml has no subtitle'], str(errs))
    with open(man, 'w') as f:
        f.write('title: T   # working title (alts: A / B)\nsubtitle: S   # PROPOSED 2026-09-02, not yet settled\n')
    errs, warns = manifest_gate(d)
    check('an unsettled title/subtitle warns but does not refuse',
          not errs and len(warns) == 2 and warns[0].startswith('title') and warns[1].startswith('subtitle'),
          str((errs, warns)))
    with open(man, 'w') as f:
        f.write('title: T   # settled 2026-09-01 (Eric)\nsubtitle: S\n')
    errs, warns = manifest_gate(d)
    check('a settled header passes clean', not errs and not warns, str((errs, warns)))
    check('a missing manifest is an error, not a pass', manifest_gate(os.path.join(tmp, 'nope'))[0])

    # the live side: the body comparison never sees the header, so this one must
    post = {'title': 'T', 'subtitle': ''}
    check('an empty live subtitle is drift even when the manifest is empty too',
          header_drift(post, {'title': 'T'}) == ['live post has NO subtitle'])
    post = {'title': 'T', 'subtitle': 'It\u2019s here \u2014 now'}
    check('curly quotes and dashes do not count as header drift',
          header_drift(post, {'title': 'T', 'subtitle': "It's here -- now"}) == [])
    check('a changed subtitle is reported',
          header_drift(post, {'title': 'T', 'subtitle': 'Other'})[0].startswith('subtitle differs'))


# ---------------------------------------------------------------- unit: pronoun sweep, E and F
PRONOUN_FIXTURE = """*Draft — fixture for the pronoun sweep; the four False Light misses of 2026-09-07 as they were before the audit.*

---

And the answer: *Get thee hence.*[^matt4] Not riches in the abstract. And the reason He gives is
worth the whole essay: *Thou shalt worship the Lord thy God, and Him only shalt thou serve.* The
question on the mountain was never competence.

*For He maketh His sun to rise on the evil and on the good, and sendeth rain on the just and on
the unjust.*[^matt545] The rain is not a reward.

Set that next to the man who said this instead. *I can of mine own self do nothing: as I hear, I
judge … because I seek not mine own will, but the will of the Father which hath sent me.*[^john530]
*Without me ye can do nothing.*[^john155] The grammar of the two texts runs in opposite directions.

He that hath seen Me hath seen the Father: *He that hath seen Me hath seen the Father.*[^john149]
Paul says it plainly: *I can do all things through Christ which strengtheneth me.*[^phil413] John
the elder says *We love [Them], because [They] first loved us.*[^1john] The point is *not* that
*He* wins; the point is that the exam was refused.

> And He said unto them, Why are ye so fearful? how is it that ye have no faith?[^mark440]

[^matt4]: Matthew 4:8–10 (KJV). The King James reads *and him only shalt thou serve*.

[^matt545]: Matthew 5:45 (KJV). The King James reads *for he maketh his sun to rise on the evil and on
    the good*.

[^john530]: John 5:30 (KJV), abridged. Cf. 5:19, *The Son can do nothing of Himself*.

[^john155]: John 15:5 (KJV). The King James reads *without me ye can do nothing*.

[^john149]: John 14:9 (KJV).

[^phil413]: Philippians 4:13 (KJV).

[^1john]: 1 John 4:19 (KJV).

[^mark440]: Mark 4:40 (KJV).
"""


# Section H's fixture: the two reflexives that shipped live in *They Them* (2026-09-10) as they
# read before the correction to *Themself*, the two legitimate uses the same day's corpus sweep
# turned up, and the shapes that must stay quiet — the intensive, a possessive subject, a
# quotation, a footnote definition, and the corrected wording itself.
REFLEXIVE_FIXTURE = """*Draft — fixture for section H.*

---

Read it as a plural of majesty if you like, or as God in deliberation — the *form* is still
plural, in the mouth of God, in the first chapter. And the likeness that comes out the far side of
that sentence is, we've already seen, itself two: male and female. A plural form, speaking of
itself in the plural, and making an image that isn't one thing either.

God is not male. They are the One Xenophanes' oxen could not draw, the no-form seen at Horeb, the
verb that refused to harden into a noun, the source that called itself *us* before They had made
anything at all.

God knows themself the way no creature is known. The Father itself is a phrase this house would
never write. They are doing the thing itself, and *I am that I am, saith the LORD unto itself*[^ex]
is the source's wording, not ours.

Press *all-powerful* hard enough and it leaves no room for a second thing standing outside God on
its own ground. That the clutching self is the source of its own suffering is not a finding a
follower of Jesus has to hold at arm's length.

If God's power is total there is no second engine running anywhere on its own. And the corrected
line reads: the source that called Themself *us*, a plural form speaking of Themself in the plural.

[^ex]: Exodus 3:14 (KJV). The King James reads *I AM THAT I AM*.
"""

def unit_pronouns(tmp):
    print("\n-- pronoun sweep: E and F look inside a scripture quotation ---------")
    d = os.path.join(tmp, 'pronouns'); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write(PRONOUN_FIXTURE)
    r = check_pronouns.sweep(d)
    E = [(w, ev) for w, ev, _ in r['E']]
    F = [(w, ev) for w, ev, _ in r['F']]
    e_sent = {(w, ev): sent for w, ev, sent in r['E']}
    f_sent = {(w, ev): sent for w, ev, sent in r['F']}

    # the measured misses — each must be listed
    check('E lists Matthew 4:10 "Him only shalt thou serve" (no adjacent ref; KJV diction qualifies it)',
          ('Him', 'kjv-diction') in E, str(E))
    check('E hit carries its sentence',
          'Him only shalt thou serve' in e_sent.get(('Him', 'kjv-diction'), ''), str(e_sent))
    check('E lists Matthew 5:45 "He maketh His sun" — both pronouns, via the ref',
          E.count(('He', 'ref:matt545')) == 1 and E.count(('His', 'ref:matt545')) == 1, str(E))
    check('F lists John 5:30 "mine own self" twice and "sent me" once, via the Gospel ref',
          F.count(('mine', 'ref:john530')) == 2 and F.count(('me', 'ref:john530')) == 1, str(F))
    check('F lists John 15:5 "without me"', ('me', 'ref:john155') in F, str(F))
    check('F hit carries its sentence',
          'Without me ye can do nothing' in f_sent.get(('me', 'ref:john155'), ''), str(f_sent))

    # what must NOT be listed
    check('F skips an epistle — Paul\'s "strengtheneth me" is not a Gospel',
          not any(ev == 'ref:phil413' for _, ev in F), str(F))
    check('F does not mistake 1 John for the Gospel of John',
          not any(ev == 'ref:1john' for _, ev in F), str(F))
    check('F is clean on a recased Gospel quotation ("hath seen Me")',
          not any(ev == 'ref:john149' for _, ev in F), str(F))
    check('E lists the recased John 14:9 "He" for justification (referent: the Son)',
          ('He', 'ref:john149') in E, str(E))
    check('E does not list a bracketed [They]/[Them] as a masculine',
          not any(ev == 'ref:1john' for _, ev in E), str(E))
    check('E ignores italic emphasis in the author\'s own prose (*He* wins — no ref, no diction)',
          not any(sent.startswith('The point is') for _, _, sent in r['E']), str(r['E']))
    check('E sweeps a blockquote carrying a KJV ref',
          ('He', 'ref:mark440') in E, str(E))
    check('neither E nor F sweeps a footnote definition (the note keeps the source wording)',
          not any('King James reads' in sent for _, _, sent in r['E'] + r['F']), str(r['E'] + r['F']))
    check('the quotation edge still holds for D (lowercase "him" inside *…* is not a D hit)',
          not r['D'], str(r['D']))

    # --strict: E and F warn, they do not refuse; C/D still do
    tool = os.path.join(HERE, 'check_pronouns.py')
    p = subprocess.run([sys.executable, tool, d, '--strict'], capture_output=True, text=True)
    check('--strict exits 0 with only E/F/G hits, and says they are warnings',
          p.returncode == 0 and 'E/F/G/H hits are warnings' in p.stdout, f"rc={p.returncode}\n{p.stdout[-400:]}")
    d2 = os.path.join(tmp, 'pronouns-d'); os.makedirs(d2, exist_ok=True)
    with open(os.path.join(d2, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write("*Draft.*\n\n---\n\nGod made the world and he saw that it was good.\n")
    p = subprocess.run([sys.executable, tool, d2, '--strict'], capture_output=True, text=True)
    check('--strict still exits 3 on a D hit', p.returncode == 3, f"rc={p.returncode}")

    # G — the LORD takes capitals (2026-09-07): a mixed-case Lord in the body is listed, a
    # footnote definition's King James wording is not, and LORD itself is never a hit
    d3 = os.path.join(tmp, 'pronouns-g'); os.makedirs(d3, exist_ok=True)
    with open(os.path.join(d3, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write("*Draft.*\n\n---\n\nI turned my life over to the Lord. *Wait on the LORD.*[^ps] "
                "The steward's lord came home.\n\n[^ps]: Psalm 27:14 (KJV): *Wait on the LORD*; "
                "Matthew 22:37 reads *love the Lord thy God*.\n")
    r3 = check_pronouns.sweep(d3)
    check('G lists the mixed-case "the Lord" in the author\'s prose', len(r3['G']) == 1 and 'over to the Lord' in r3['G'][0], str(r3['G']))
    d4 = os.path.join(tmp, 'pronouns-g2'); os.makedirs(d4, exist_ok=True)
    with open(os.path.join(d4, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write("*Draft.*\n\n---\n\n*Wait on the LORD.*[^ps] The steward's lord came home.\n\n"
                "[^ps]: Psalm 27:14 (KJV); Matthew 22:37 reads *love the Lord thy God*.\n")
    check('G does not list LORD, a lowercase lord, or a footnote definition\'s King James wording',
          not check_pronouns.sweep(d4)['G'], str(check_pronouns.sweep(d4)['G']))
    p = subprocess.run([sys.executable, tool, d3, '--strict'], capture_output=True, text=True)
    check('--strict exits 0 with only a G hit, and says it is a warning', p.returncode == 0 and 'E/F/G/H hits are warnings' in p.stdout, f"rc={p.returncode}")

    # H — a lowercase reflexive whose antecedent is God (2026-09-10).  The two hits are the two
    # misses that shipped live in *They Them*; the two non-hits are the only two legitimate uses
    # a corpus sweep found the same day, and both sit as close to a God-word as the misses do.
    d5 = os.path.join(tmp, 'pronouns-h'); os.makedirs(d5, exist_ok=True)
    with open(os.path.join(d5, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write(REFLEXIVE_FIXTURE)
    r5 = check_pronouns.sweep(d5)
    H = [(w, ev.split(':', 1)[0]) for w, ev, _ in r5['H']]
    h_sent = {(w, ev.split(':', 1)[0]): sent for w, ev, sent in r5['H']}
    check('H catches "the source that called itself" — an appositive in a copular God chain',
          ('itself', 'appositive') in H, str(r5['H']))
    check('the appositive hit carries its sentence',
          'called itself' in h_sent.get(('itself', 'appositive'), ''), str(h_sent))
    check('H catches "A plural form, speaking of itself" — a self-naming verb in a God paragraph',
          ('itself', 'self-naming') in H, str(r5['H']))
    check('H does not fire on "standing outside God on its own ground" (the second thing owns it)',
          not any('outside God' in sent for _, _, sent in r5['H']), str(r5['H']))
    check('H does not fire on "the source of its own suffering" (the clutching self owns it)',
          not any('clutching self' in sent for _, _, sent in r5['H']), str(r5['H']))
    check('H skips the intensive "the thing itself" under a God subject',
          not any('doing the thing' in sent for _, _, sent in r5['H']), str(r5['H']))
    check('H keeps a God-word taking the intensive ("the Father itself")',
          any('The Father itself' in sent for _, _, sent in r5['H']), str(r5['H']))
    check('H reads a possessive as the subject it is ("God\'s power ... on its own" is not God\'s)',
          not any("God's power" in sent for _, _, sent in r5['H']), str(r5['H']))
    check('H catches a plain God subject ("God knows themself")',
          ('themself', 'subject') in H, str(r5['H']))
    check('H leaves a quotation alone (the source\'s own case is evidence)',
          not any('saith the LORD' in sent for _, _, sent in r5['H']), str(r5['H']))
    check('H skips a footnote definition', not any('KJV' in sent for _, _, sent in r5['H']), str(r5['H']))
    check('the corrected wording is clean — Themself and Their own are never H hits',
          not any('Themself' in w or 'Their' in w for w, _, _ in r5['H']), str(r5['H']))
    d6 = os.path.join(tmp, 'pronouns-h2'); os.makedirs(d6, exist_ok=True)
    with open(os.path.join(d6, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write("*Draft.*\n\n---\n\nGod knows themself the way no creature is known.\n")
    r6 = check_pronouns.sweep(d6)
    check('the H-only fixture really is H-only (no C or D hit riding along)',
          r6['H'] and not r6['C'] and not r6['D'], str(r6['C'] + r6['D']))
    p = subprocess.run([sys.executable, tool, d6, '--strict'], capture_output=True, text=True)
    check('--strict exits 0 on H hits — an antecedent is a human call, so H warns and never refuses',
          p.returncode == 0 and 'E/F/G/H hits are warnings' in p.stdout, f"rc={p.returncode}\n{p.stdout[-400:]}")
    # a justified hit is silenced the way a C or G hit is, in a reviewable file
    with open(os.path.join(d5, 'publish.yaml'), 'w', encoding='utf-8') as f:
        f.write("title: T\nsubtitle: S\npronouns_allow:\n  - called itself\n")
    check('publish.yaml pronouns_allow silences a justified H hit',
          not any('called itself' in sent for _, _, sent in check_pronouns.sweep(d5)['H']),
          str(check_pronouns.sweep(d5)['H']))


TALK_FIXTURE = """*Draft — v0. Header is scaffold.*

---

## I. The Setup (5 min)

<!-- slide: The promise -->
> Enough attributes and the right person is a query away.
- one bullet

The spoken script of the first slide.
It continues on a second line of the same paragraph.

A second paragraph.

<!-- slide -->
![Figure 1](assets/fig1.png)

Say what the axes are.

<!-- slide: Silent -->
> A line with nobody speaking over it.

## II. The Geometry (12 min)

<!-- slide: One -->
Words words words.
"""


def unit_talk(tmp):
    print("\n-- talk: draft.md -> Marp deck with the script as notes ---------------")
    d = os.path.join(tmp, 'talk'); os.makedirs(os.path.join(d, 'assets'), exist_ok=True)
    with open(os.path.join(d, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write(TALK_FIXTURE)
    with open(os.path.join(d, 'outline.md'), 'w', encoding='utf-8') as f:
        f.write("## I. The Setup (5 min)\n## II. The Geometry (12 min)\n")
    slides = md_to_marp.parse(TALK_FIXTURE)
    kinds = [x['kind'] for x in slides]
    check('movements become section slides and markers become slides',
          kinds == ['section', 'slide', 'slide', 'slide', 'section', 'slide'], str(kinds))
    first = slides[1]
    check('blockquote and list go on the slide, prose becomes notes',
          first['on'] == ['> Enough attributes and the right person is a query away.', '- one bullet']
          and first['notes'] == ['The spoken script of the first slide. It continues on a second line of the same paragraph.',
                                 'A second paragraph.'], str(first))
    check('the header above --- is discarded', not any('scaffold' in n for x in slides for n in x['notes']))
    faults = md_to_marp.check(slides, d)
    check('--check names a missing figure and a slide with no notes',
          any('missing figure assets/fig1.png' in f for f in faults) and any('Silent' in f and 'no speaker notes' in f for f in faults),
          str(faults))
    deck = md_to_marp.render(slides, {'title': 'T', 'subtitle': 'S'}, d)
    check('the deck opens with Marp front matter and the title slide',
          deck.startswith('---\nmarp: true') and '# T' in deck and '## S' in deck)
    check('notes travel as HTML comments and a figure is sized for the slide',
          '<!--\nThe spoken script' in deck and '![Figure 1 h:600px](assets/fig1.png)' in deck, deck[:400])
    out_dir, n, has_style = md_to_marp.write_briefs(slides, {'title': 'T', 'subtitle': 'S', 'speaker': 'Me'}, d)
    briefs = sorted(f for f in os.listdir(out_dir) if f.endswith('.md'))
    check('--briefs writes one brief per slide plus the title slide and an index, and names an untitled figure slide by its figure',
          n == 7 and len(briefs) == 8 and '04-fig1.md' in briefs and 'README.md' in briefs, str(briefs))
    b = open(os.path.join(out_dir, '03-the-promise.md'), encoding='utf-8').read()
    check('a brief carries the slide text verbatim, the script as context, and position/neighbors',
          '> Enough attributes and the right person is a query away.' in b and 'The spoken script of the first slide.' in b
          and '**Position:** 3 of 7' in b and 'A second paragraph.' in b, b[:600])
    check('00-style.md is reported absent rather than invented', has_style is False)
    per = md_to_marp.per_movement(slides, os.path.join(d, 'outline.md'))
    check('per-movement words carry the outline minutes',
          [(t.split('.')[0], b) for t, w, b in per] == [('I', 5), ('II', 12)] and per[0][1] > per[1][1], str(per))


# ---------------------------------------------------------------- corpus
def corpus_integrity():
    print("\n-- corpus: every piece renders cleanly ---------------------------")
    pieces_dir = PIECES
    if not os.path.isdir(pieces_dir):
        skip('corpus render', f'no corpus at {pieces_dir}'); return
    faults, n = [], 0
    for p in sorted(os.listdir(pieces_dir)):
        d = os.path.join(pieces_dir, p)
        if not os.path.isfile(os.path.join(d, 'draft.md')):
            continue
        n += 1
        try:
            body, fns, residual, iss = render_reader(d)
        except Exception as e:                                    # noqa: BLE001
            faults.append(f'{p}: render error {e}')
            continue
        for k in ('undefined', 'duplicated', 'nested'):
            if iss[k]:
                faults.append(f'{p}: footnote {k} {iss[k]}')
        if residual:
            faults.append(f'{p}: verify/clearance residue {residual}')
        if not body:
            faults.append(f'{p}: renders to an empty body')
    check(f'all {n} pieces render with no footnote, verify, or clearance faults',
          not faults, '; '.join(faults[:4]))


def corpus_headers():
    """A published piece's draft.md must say it is published.

    The file keeps the name draft.md for its whole life -- renaming would give nine tools
    a second name to know about, and a call site that missed it would not error, it would
    silently drop the piece from every corpus check. So the header carries the state, and
    this check keeps the header honest: it is front matter, invisible to readers, and
    therefore exactly the kind of thing that rots unnoticed without a test.
    """
    print("\n-- corpus: live pieces say they are live --------------------------")
    pieces_dir = PIECES
    if not os.path.isdir(pieces_dir):
        skip('headers', f'no corpus at {pieces_dir}'); return
    stale, n = [], 0
    for p in sorted(os.listdir(pieces_dir)):
        d = os.path.join(pieces_dir, p)
        if not os.path.isfile(os.path.join(d, 'draft.md')):
            continue
        man = read_manifest(os.path.join(d, 'publish.yaml'))
        if not man.get('public_url'):
            continue
        if not man.get('published_at'):
            stale.append(f'{p} (live but no published_at)'); continue
        n += 1
        new, _note = header_rewrite(open(os.path.join(d, 'draft.md')).read(), man)
        if new is not None:
            stale.append(p)
    check(f'all {n} live pieces carry a current published header',
          not stale, '; '.join(stale[:4]) + '  (fix: piece_header.py --apply)')


def corpus_manifests():
    """Every composed piece carries the two lines the body check cannot see.

    A post's title and subtitle are not in body_html, so corpus_baselines and
    substack_verify's block comparison are blind to them by construction. This is the
    offline half of the guard: the manifest that will be composed must already carry both.
    (The online half is `substack_verify.py --archive`, which reads the reader's list.)
    """
    print("\n-- corpus: composed pieces carry a title and a subtitle -------------")
    pieces_dir = PIECES
    if not os.path.isdir(pieces_dir):
        skip('manifests', f'no corpus at {pieces_dir}'); return
    bad, unsettled, n = [], [], 0
    for p in sorted(os.listdir(pieces_dir)):
        d = os.path.join(pieces_dir, p)
        if not os.path.isfile(os.path.join(d, 'publish.yaml')):
            continue
        n += 1
        errs, warns = manifest_gate(d)
        if errs:
            bad.append(f'{p}: ' + '; '.join(errs))
        if warns and read_manifest(os.path.join(d, 'publish.yaml')).get('public_url'):
            unsettled.append(p)
    check(f'all {n} composed pieces carry a title and a subtitle', not bad, '; '.join(bad[:4]))
    if unsettled:
        print(f"  note  live but the manifest still marks the header unsettled: {', '.join(unsettled)}"
              "  (clear the comment once the author has signed off)")


def corpus_baselines():
    print("\n-- corpus: published pieces match their baselines -----------------")
    pieces_dir = PIECES
    if not os.path.isdir(pieces_dir):
        skip('corpus baselines', f'no corpus at {pieces_dir}'); return
    pub, behind, ahead, textonly = 0, [], [], []
    for p in sorted(os.listdir(pieces_dir)):
        d = os.path.join(pieces_dir, p)
        if not os.path.isfile(os.path.join(d, 'draft.md')):
            continue
        man = read_manifest(os.path.join(d, 'publish.yaml'))
        if not man.get('public_url'):
            continue                                              # composed drafts are not live
        pub += 1
        base = load_baseline(d)
        if base is None:
            behind.append(f'{p} (no baseline)')
            continue
        body, fns, _r, _i = render_reader(d)
        differs = [H(t) for t in body] != base['body'] or [H(t) for t in fns] != base['fns']
        # The second domain. A baseline sealed before marks were tracked cannot answer, and
        # is listed rather than quietly passed -- an unanswerable check that reports success
        # is the thing this whole change is about.
        if baseline_has_marks(base):
            bm, fm, _ok = render_marks(d)
            if ([HM(r) for r in bm] != base['bodyMarks']
                    or [HM(r) for r in fm] != base['fnsMarks']):
                differs = True
        else:
            textonly.append(p)
        # A draft may be DELIBERATELY ahead of its live post: a rewrite is drafted and is
        # waiting on the author to read it before anything touches a public page. That is a
        # normal, intended state on this desk, and reporting it as a failure for as long as it
        # lasts is how a corpus-wide gate gets tuned out. `draft_ahead:` in publish.yaml is the
        # declaration, and it is deliberately shaped like the `verified:` clearance: a date and
        # a sentence, written where it is reviewable in the diff and survives the session.
        #
        #     draft_ahead:
        #       since: 2026-09-07
        #       note: v2 rewrite drafted, awaiting Eric's read; the post still holds v1.
        #
        # One line per value — `read_manifest` does not fold `>-` block scalars, and a `note:`
        # written as one would parse to the literal string '>-'.
        #
        # Two rules keep it from becoming a way to switch the check off:
        #   * a declaration with no `since:` date does NOT excuse anything — it still fails, so
        #     the escape hatch cannot be a bare toggle;
        #   * a declaration on a piece that is back IN SYNC fails too, which retires the key by
        #     itself once the rewrite ships, instead of letting it sit there excusing the next
        #     drift nobody noticed.
        decl = man.get('draft_ahead')
        since = decl.get('since', '').strip() if isinstance(decl, dict) else ''
        if decl and not since:
            behind.append(f'{p} (draft_ahead: with no since: date)')
        elif decl and not differs:
            behind.append(f'{p} (draft_ahead: but the draft matches the post — retire the key)')
        elif decl:
            ahead.append((p, since, _age(since), decl.get('note', '').strip()))
        elif differs:
            behind.append(p)
    check(f'all {pub} published pieces are in sync', not behind, '; '.join(behind))
    if textonly:
        print(f"  note  {len(textonly)} baseline(s) predate mark tracking, so FORMATTING is not "
              f"checked for them: {', '.join(textonly[:6])}"
              + (' …' if len(textonly) > 6 else ''))
        print(f"        (they seal with marks on the next completed sync; until then only their "
              f"text is held to the baseline)")
    for name, since, age, note in ahead:
        print(f"  note  {name}: draft deliberately ahead of the live post since {since}{age} "
              f"(declared in publish.yaml; a re-sync or recompose clears it)"
              + (f"\n        {note}" if note else ''))


def _age(since):
    """' , N days' for a declaration date, so one left to rot is visible in the report."""
    try:
        d = datetime.date.fromisoformat(since)
    except ValueError:
        return ''
    n = (datetime.date.today() - d).days
    return f', {n} day{"" if n == 1 else "s"}' if n > 0 else ''


# ---------------------------------------------------------------- engine (stubbed browser)
def engine_suite(tmp):
    print("\n-- engine: JS patcher against a stubbed editor --------------------")
    pieces_dir = PIECES
    if not os.path.isdir(pieces_dir):
        skip('engine suite', f'no corpus at {pieces_dir}'); return
    repatch = os.path.join(HERE, 'substack_repatch.py')
    runner = os.path.join(HERE, 'test_substack_repatch.js')
    srunner = os.path.join(HERE, 'test_substack_structural.js')
    scanner = os.path.join(HERE, 'test_substack_scan.js')
    if subprocess.run(['node', '--version'], capture_output=True).returncode != 0:
        skip('engine suite', 'node not available')
        return
    # SCAN_JS carries no per-piece content, so it is generated once and run against every
    # piece's document below.
    scan_js = os.path.join(tmp, 'scan.js')
    subprocess.run([sys.executable, os.path.join(HERE, 'substack_sync.py'),
                    'scan', os.path.join(PIECES, os.listdir(PIECES)[0]), scan_js],
                   capture_output=True, text=True)
    failures, ran, skipped, scan_ok = [], 0, 0, 0
    for p in sorted(os.listdir(pieces_dir)):
        d = os.path.join(pieces_dir, p)
        if not os.path.isfile(os.path.join(d, 'draft.md')):
            continue
        js = os.path.join(tmp, f'{p}.js')
        gen = subprocess.run([sys.executable, repatch, d, js], capture_output=True, text=True)
        if gen.returncode != 0:
            failures.append(f'{p}: generator refused ({gen.stdout.strip().splitlines()[:1]})')
            continue
        r = subprocess.run(['node', runner, js], capture_output=True, text=True)
        ran += 1
        skipped += r.stdout.count('\nskip') + r.stdout.startswith('skip')
        if r.returncode != 0:
            failures.append(f'{p}: ' + '; '.join(l.strip() for l in r.stdout.splitlines()
                                                 if l.startswith('FAIL')))
        # the structural engine, against the same piece: S1–S9, with a document model that
        # moves whole blocks, anchors and marks (see test_substack_structural.js)
        sjs = os.path.join(tmp, f'{p}.structural.js')
        sgen = subprocess.run([sys.executable, repatch, '--structural', d, sjs], capture_output=True, text=True)
        if sgen.returncode != 0:
            failures.append(f'{p}: structural generator refused ({sgen.stdout.strip().splitlines()[:1]})')
            continue
        sr = subprocess.run(['node', srunner, sjs], capture_output=True, text=True)
        skipped += sr.stdout.count('\nskip') + sr.stdout.startswith('skip')
        if sr.returncode != 0:
            failures.append(f'{p} [structural]: ' + '; '.join(l.strip() for l in sr.stdout.splitlines()
                                                              if l.startswith('FAIL')))

        # THE CROSS-THE-WIRE ASSERTION, and the one the sync baseline rests on. SCAN_JS
        # computes a mark signature in the browser; mark_sig() computes one in Python. They
        # are the same string derived on two sides of a wire, and a hash of two strings that
        # can disagree is not a baseline. Run the real scan snippet against this piece's own
        # document and require both domains to match digest for digest.
        if os.path.isfile(scan_js):
            cr = subprocess.run(['node', scanner, scan_js, sjs], capture_output=True, text=True)
            if cr.returncode != 0:
                failures.append(f'{p} [scan]: runner failed ({cr.stderr.strip()[:120]})')
            else:
                try:
                    live = json.loads(cr.stdout)
                except Exception as e:                            # noqa: BLE001
                    failures.append(f'{p} [scan]: unparseable output ({e})')
                    continue
                st = draft_state(d)
                want_t = ([H(t) for t in st['body']], [H(t) for t in st['fns']])
                want_m = ([HM(r) for r in st['bodyMarks']], [HM(r) for r in st['fnsMarks']])
                if (list(want_t[0]), list(want_t[1])) != (live['body'], live['fns']):
                    failures.append(f'{p} [scan]: the browser and Python disagree on TEXT hashes')
                elif (list(want_m[0]), list(want_m[1])) != (live['bodyMarks'], live['fnsMarks']):
                    bad = next((i for i, (x, y) in enumerate(zip(want_m[0], live['bodyMarks']))
                                if x != y), None)
                    failures.append(f'{p} [scan]: the browser and Python disagree on MARK '
                                    f'signatures (first body row {bad})')
                else:
                    scan_ok += 1
    check(f'JS patcher suite passes for all {ran} pieces', not failures,
          ' | '.join(failures[:3]))
    check(f'the browser and Python agree on text AND mark digests for all {scan_ok} pieces',
          scan_ok == ran, f'{scan_ok}/{ran}')
    if skipped:
        print(f"        ({skipped} inapplicable check(s) skipped across the corpus)")


def reseal_fixtures():
    """Rewrite the fixture golden baselines from the converter's current output.

    This is the ONE writing operation in this file, it is opt-in, and it refuses to
    touch anything but the shipped fixtures — a golden file you can reseal by accident
    is not golden, and resealing the real corpus from here would silently move a
    published piece's sync baseline without ever looking at the live post.
    """
    from substack_sync import write_baseline
    fixtures = os.path.join(HERE, 'fixtures', 'pieces')
    if os.path.abspath(PIECES) != os.path.abspath(fixtures):
        print(f"refusing: --reseal-fixtures only reseals {fixtures}, but the corpus "
              f"is {CORPUS_KIND} ({PIECES})")
        return 1
    n = 0
    for name in sorted(os.listdir(fixtures)):
        d = os.path.join(fixtures, name)
        if not os.path.isfile(os.path.join(d, 'draft.md')):
            continue
        man = read_manifest(os.path.join(d, 'publish.yaml'))
        if not man.get('public_url'):
            continue
        body, fns, _r, _i = render_reader(d)
        write_baseline(d, man.get('title', ''), man.get('subtitle', ''),
                       [H(t) for t in body], [H(t) for t in fns],
                       'fixture golden file — sealed by test_suite.py --reseal-fixtures')
        print(f"  sealed  {name}  ({len(body)} body, {len(fns)} fns)")
        n += 1
    print(f"{n} fixture baseline(s) resealed")
    return 0


def main():
    if '--reseal-fixtures' in sys.argv:
        return reseal_fixtures()
    print("regression suite — no deletion, no network, no browser, repo read-only")
    print(f"corpus: {CORPUS_KIND}  ({PIECES})")
    with tempfile.TemporaryDirectory(prefix='desk-suite-') as tmp:
        print(f"scratch: {tmp}  (removed on exit)")
        unit_normalization()
        unit_link_extraction()
        unit_cli_dispatch()
        unit_piece_resolution(tmp)
        unit_three_way()
        unit_converter(tmp)
        unit_footnote_continuation(tmp)
        unit_footnote_order(tmp)
        unit_pull_verification()
        unit_images()
        unit_live_extraction()
        unit_mark_drift(tmp)
        unit_sync_baseline_marks(tmp)
        unit_manifest_gate(tmp)
        unit_pronouns(tmp)
        unit_talk(tmp)
        corpus_integrity()
        corpus_headers()
        corpus_manifests()
        corpus_baselines()
        engine_suite(tmp)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed, {len(SKIP)} skipped")
    for name, detail in FAIL:
        print(f"  FAILED  {name}   {detail}")
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
