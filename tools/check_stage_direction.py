#!/usr/bin/env python3
"""check_stage_direction.py — the commonest breach in the argued voice, in a sweep.

The essay constitution ranks stage direction as its most frequent fault, and names FOUR
SHAPES.  Until now none of them was in any checker, and
the desk's own rule is that A RULE NO SWEEP CHECKS IS NOT ENFORCED — the 2026-09-02
corpus audit found it in 20 of 21 essay-voice pieces, by hand.

The sort that decides every case:
    ADMITTING A LIMIT IS PART OF THE ARGUMENT.  NARRATING THE ADMISSION IS NOT.
    "Strictly, then:" stays.  "I want to be careful here about the scope of my claim" goes.

  procedure   — announcing the move instead of making it
  provenance  — revision history, discovery, formation, expectation.  A steelman describes
                the OBJECTION itself, not how highly the author rates it.
  terms       — naming this voice's own vocabulary to the reader.  THE WORST FORM: the essay
                turns from its argument to a lesson in its own method.
  impersonal  — the same move with the *I* removed ("a caveat is owed here before going
                on").  The constitution singles it out as the hardest to catch, because
                it carries no first person and so reads as argument.
  architecture— pointing at the essay's own parts or the corpus ("this essay", "section four").

WARNS, NEVER REFUSES.  Every hit needs a human call: `movement` is also an ordinary word, and
one piece runs a LEDGER as its literal figure.  A checker that refused would be switched off.

    python3 framework/tools/check_stage_direction.py pieces/<slug> [...]
    python3 framework/tools/check_stage_direction.py --all        # every essay-voice piece
    python3 framework/tools/check_stage_direction.py --all --counts
"""
import argparse, glob, os, re, sys

SHAPES = {
 'procedure': [
   r"\bI'?ll (?:say|add|tell you|put|start|stop|leave|take)\b", r"\bI want to\b",
   r"\bI'?m going to\b", r"\blet me\b", r"\bbefore (?:going|we go) further\b",
   r"\bin a moment\b", r"\bhere is the join\b", r"\band then stop\b",
   r"\bI owe you\b", r"\bwhich brings us to\b", r"\bI mean to\b",
   r"\bworth being precise about\b", r"\bto be precise about\b",
   r"\bnamed before you raise them\b", r"\bbefore you have to\b",
   r"\bhold that\b[.,;]? *\bdon'?t resolve\b", r"\bI will tell you only\b",
   r"\bI would rather tell you\b", r"\bI can only say\b",
 ],
 'provenance': [
   r"\ban earlier version\b", r"\bthe first version of it\b", r"\bI dropped it\b",
   r"\bI did not notice at the time\b", r"\bit turned out\b", r"\bthe way I was taught\b",
   r"\bbefore I knew better\b", r"\bthe one I expected to find\b",
   r"\bthe objection I expected to lose\b", r"\bI thought would beat me\b",
   r"\bfor a while I told it\b", r"\bthe correction I owe\b",
 ],
 'terms': [
   r"\bload-bearing\b", r"\bthe gavel\b", r"\bsteelman\b", r"\bimage-close\b",
   r"\bthe tidy ending\b", r"\bleave the space\b", r"\bguardrail\b",
   r"\bthe file\b", r"\bthe ledger\b", r"\bthe desk\b", r"\bthe movement\b",
 ],
 'impersonal': [
   r"\bthe only honest way to\b", r"\bit has to be quoted whole\b",
   r"\bthe limit has to be stated\b", r"\bhas to be said (?:before|first)\b",
   r"\bthe honest version of\b", r"\bnote precisely what\b",
   r"\bone honest complication\b", r"\bwould be its own (?:kind of )?(?:lie|dishonesty)\b",
   r"\bpretending otherwise would be\b",
 ],
 'architecture': [
   r"\bthis essay\b", r"\bthe rest of this essay\b", r"\bmy other essays\b",
   r"\bsection (?:one|two|three|four|five|six|seven|eight|nine|[IVX]+)\b",
   # case-SENSITIVE: `\bpart I\b` under re.I matches "the part I have come to believe",
   # which is English, not a section reference. Two false positives in one piece.
   r"(?-i:\bPart [IVX]+\b)", r"\bthe whole argument turns on\b", r"\bthe whole of this essay\b",
   r"\bwhich is the last thing\b",
 ],
}
COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in SHAPES.items()}


def body_of(path):
    """Reader text only: below the scaffold header, comments and dagger notes gone."""
    t = open(path, encoding='utf-8').read()
    t = t.split('\n---\n', 1)[-1]
    t = re.sub(r'<!--.*?-->', '', t, flags=re.S)
    t = re.sub(r'†[^\n]*', '', t)
    return t


def voice_of(piece_dir):
    for name in ('publish.yaml', 'README.md'):
        p = os.path.join(piece_dir, name)
        if os.path.exists(p):
            m = re.search(r'being-good-essay|being-good-journal', open(p, encoding='utf-8').read())
            if m:
                return m.group(0)
    return None


# A TERM THE PIECE RUNS AS ITS FIGURE IS CONTENT, NOT A LEAK — and this is the distinction
# that makes the `terms` shape usable at all. `the-way-home-is-down` is BUILT on the gavel:
# bench, gavel, verdict, "hand the gavel back", twelve times down the essay. That is a
# metaphor run literally, which the constitution explicitly licenses; the voice's term of art
# was very likely taken FROM it. Flagging all twelve produced a 29-hit piece that was almost
# entirely noise. A term used once or twice is the vocabulary leaking; a term the essay runs
# throughout is the essay's subject. Threshold, not cleverness.
FIGURE_MIN = 3


def sweep(piece_dir):
    draft = os.path.join(piece_dir, 'draft.md')
    if not os.path.exists(draft):
        return None
    text = body_of(draft)
    flat = re.sub(r'\s+', ' ', text)
    sents = re.split(r'(?<=[.!?]) ', flat)
    hits = []
    for shape, pats in COMPILED.items():
        for pat in pats:
            if shape == 'terms' and len(pat.findall(flat)) >= FIGURE_MIN:
                continue          # the piece's own figure; see FIGURE_MIN
            for s in sents:
                for m in pat.finditer(s):
                    hits.append((shape, m.group(0), s.strip()))
    seen, out = set(), []
    for h in hits:
        k = (h[0], h[2], h[1])
        if k in seen:
            continue
        seen.add(k)
        out.append(h)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pieces', nargs='*')
    ap.add_argument('--all', action='store_true', help='every piece in the argued voice')
    ap.add_argument('--counts', action='store_true', help='one line per piece')
    o = ap.parse_args()

    dirs = o.pieces
    if o.all:
        dirs = [d for d in sorted(glob.glob('pieces/*')) if voice_of(d) == 'being-good-essay']
    if not dirs:
        sys.stderr.write('nothing to sweep (pass piece dirs, or --all)\n')
        return 2

    total, worst = 0, []
    for d in dirs:
        hits = sweep(d)
        if hits is None:
            continue
        total += len(hits)
        worst.append((len(hits), os.path.basename(d), hits))

    worst.sort(reverse=True)
    for n, slug, hits in worst:
        by = {}
        for shape, frag, _s in hits:
            by.setdefault(shape, []).append(frag)
        if o.counts:
            parts = ' '.join(f'{k}={len(v)}' for k, v in sorted(by.items()))
            print(f'{n:>4}  {slug:<34} {parts}')
            continue
        if not n:
            continue
        print(f'\n{"="*92}\n{slug}  —  {n} hit(s)')
        for shape in ('terms', 'impersonal', 'provenance', 'procedure', 'architecture'):
            rows = [h for h in hits if h[0] == shape]
            if not rows:
                continue
            print(f'\n  {shape.upper()} ({len(rows)})')
            for _sh, frag, sent in rows:
                print(f'    «{frag}»')
                print(f'        {sent[:190]}')
    print(f'\n{total} hit(s) across {len([w for w in worst if w[0]])} piece(s) '
          f'of {len(worst)} swept — WARN only; every one needs a human call.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
