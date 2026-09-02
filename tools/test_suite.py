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
"""
import os, re, sys, json, subprocess, tempfile

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
                            read_manifest, parse_blocks)
from substack_sync import (H, three_way, align, canonical_image_url,
                           reader_to_source_map, edit_block_source, load_baseline)
from substack_verify import live_blocks, extract_post
from piece_header import rewrite as header_rewrite
from check_links import extract as extract_links, unrenderable as unrenderable_links

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
    b, f = live_blocks('<ul><li><p>alpha</p></li><li><p>beta</p></li></ul>')
    check('a bullet list extracts as a single block', b == ['alphabeta'], repr(b))

    # Same bug, different tag -- and adjacent quotes merge, as the draft renderer merges them.
    b, _ = live_blocks('<blockquote><p>one</p></blockquote><blockquote><p>two</p></blockquote>')
    check('adjacent blockquotes merge into one block', b == ['onetwo'], repr(b))

    b, _ = live_blocks('<p>plain</p><blockquote><p>q</p></blockquote><p>after</p>')
    check('a lone blockquote does not swallow the paragraph after it',
          b == ['plain', 'q', 'after'], repr(b))

    # Furniture Substack injects into the body: not prose, must not count as drift.
    b, _ = live_blocks('<p>real</p><div class="subscription-widget-wrap-editor">'
                       '<div class="subscription-widget"><div class="preamble">'
                       '<p class="cta-caption">Thanks for reading! Subscribe.</p>'
                       '</div></div></div><p>also real</p>')
    check('a subscribe widget is not counted as body', b == ['real', 'also real'], repr(b))

    b, _ = live_blocks('<div class="captioned-image-container"><figure>'
                       '<img src="x"><figcaption>a caption</figcaption></figure></div><p>text</p>')
    check('an image and its caption are not body', b == ['text'], repr(b))

    # Void tags inside a skipped subtree once wedged the parser open forever: <img>,
    # <source> and <hr> have no end tag, so a depth counter that increments on them
    # never comes back down and the whole rest of the post vanishes.
    b, _ = live_blocks('<div class="captioned-image-container"><picture>'
                       '<source srcset="a"><img src="b"></picture></div><hr><p>survives</p>')
    check('void tags in skipped subtrees do not wedge the parser', b == ['survives'], repr(b))

    # The superscript marker is not prose; the footnote body is not body.
    b, f = live_blocks('<p>Sentence<a class="footnote-anchor" href="#footnote-1">1</a> ends.</p>'
                       '<div class="footnote"><a class="footnote-number">1</a>'
                       '<div class="footnote-content"><p>The note.</p></div></div>')
    check('a footnote anchor leaves no digit in the prose', b == ['Sentence ends.'], repr(b))
    check('footnote content is captured separately', f == ['The note.'], repr(f))

    # A page that shipped no post (login wall, layout change) must read as "could not
    # check", never as an empty post that trivially matches nothing.
    check('a page with no _preloads yields no post',
          extract_post('<html><body>nothing here</body></html>') is None)


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
            faults.append(f'{p}: unverified note residue {residual}')
        if not body:
            faults.append(f'{p}: renders to an empty body')
    check(f'all {n} pieces render with no footnote or verify faults',
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


def corpus_baselines():
    print("\n-- corpus: published pieces match their baselines -----------------")
    pieces_dir = PIECES
    if not os.path.isdir(pieces_dir):
        skip('corpus baselines', f'no corpus at {pieces_dir}'); return
    pub, behind = 0, []
    for p in sorted(os.listdir(pieces_dir)):
        d = os.path.join(pieces_dir, p)
        if not os.path.isfile(os.path.join(d, 'draft.md')):
            continue
        if not read_manifest(os.path.join(d, 'publish.yaml')).get('public_url'):
            continue                                              # composed drafts are not live
        pub += 1
        base = load_baseline(d)
        if base is None:
            behind.append(f'{p} (no baseline)')
            continue
        body, fns, _r, _i = render_reader(d)
        if [H(t) for t in body] != base['body'] or [H(t) for t in fns] != base['fns']:
            behind.append(p)
    check(f'all {pub} published pieces are in sync', not behind, '; '.join(behind))


# ---------------------------------------------------------------- engine (stubbed browser)
def engine_suite(tmp):
    print("\n-- engine: JS patcher against a stubbed editor --------------------")
    pieces_dir = PIECES
    if not os.path.isdir(pieces_dir):
        skip('engine suite', f'no corpus at {pieces_dir}'); return
    repatch = os.path.join(HERE, 'substack_repatch.py')
    runner = os.path.join(HERE, 'test_substack_repatch.js')
    if subprocess.run(['node', '--version'], capture_output=True).returncode != 0:
        skip('engine suite', 'node not available')
        return
    failures, ran, skipped = [], 0, 0
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
    check(f'JS patcher suite passes for all {ran} pieces', not failures,
          ' | '.join(failures[:3]))
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
        unit_three_way()
        unit_converter(tmp)
        unit_footnote_continuation(tmp)
        unit_footnote_order(tmp)
        unit_pull_verification()
        unit_images()
        unit_live_extraction()
        corpus_integrity()
        corpus_headers()
        corpus_baselines()
        engine_suite(tmp)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed, {len(SKIP)} skipped")
    for name, detail in FAIL:
        print(f"  FAILED  {name}   {detail}")
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
