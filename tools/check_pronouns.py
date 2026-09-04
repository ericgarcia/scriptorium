#!/usr/bin/env python3
"""check_pronouns.py — the pronoun sweeps this desk kept doing by hand, as one tool.

WHY THIS EXISTS (2026-09-03).  Three pronoun rules live in the constitutions and all three
were being enforced by ad-hoc greps typed fresh in each session — and a rule that is not in
the sweep list is not in force.  *The Mask Comes Off Last* reached a composed Substack draft
carrying twenty-one generic masculines for the villain (the 2026-09-01 rule said they/them),
and then a lowercase *the one* for God (the essay voice capitalizes an oblique reference to
God: *the One*, *Someone*).  Both were caught by Eric, after compose, reading the page.

WHAT IT CHECKS, on the whole draft body (footnotes included), whitespace-normalized:

  A. SENTENCE-INITIAL CAPITALS  He/Him/His/They/Them/She/Her at the head of a sentence.  English
     forces the capital, and a forced capital silently reassigns the referent to the Son, the
     Father or the Spirit.  Every hit is listed for justification; the usual repair is to
     restructure so the pronoun falls mid-sentence.
  B. GENERIC MASCULINE  he/him/his/himself and *a man / the man / one man / any man*.  A
     hypothetical person takes they/them; the exception is *this person actually exists*
     (scripture, history, a named character, the author).  Hits within a few words of a name
     given with --names are marked `named?`; everything else is `GENERIC?` and needs a referent.
  C. GOD AS A LOWERCASE OBLIQUE, OR AS A *WHAT*  lowercase *the one / someone / whoever /
     something / a mind / one mind* in a sentence that also names God (God, Lord, Father,
     Spirit, Them, infinite, dream(ing), remembering, the One).  The essay voice capitalizes
     these (*the One who*, *Someone infinite*) and never lets God be a *what*.
  D. LOWERCASE DEITY PRONOUN  he/him/his/it within six words after God / the Lord / the Father /
     the Spirit / Christ / Jesus, outside a verbatim quotation.  Inside a quotation the source's
     own case is evidence and stays (the KJV lowercases; the house capitalizes in its own prose
     and, for its own scripture, raises the case — see the constitution).

It REPORTS; it does not edit, and it cannot know a referent.  The operator justifies every hit
by naming who it points at — that is the sweep, and this tool only makes sure it happens.

USAGE
    python3 check_pronouns.py <piece-dir> [--names A,B,C] [--strict]
      --names   comma-separated named figures whose pronouns are theirs (Campbell,Peter,...)
      --strict  exit 3 if any C or D hit remains (for a publish preflight); A and B always
                exit 0 because they are lists to be justified, not verdicts.
    A C-hit whose referent is NOT God is justified by listing a substring of it in the piece's
    publish.yaml under `pronouns_allow:` — reviewable, and it survives the session.
EXIT  0 clean or only A/B listings · 3 C/D hits under --strict · 1 usage
"""
import os, re, sys

GOD_WORDS = r"(God|the Lord|the LORD|the Father|the Spirit|Christ|Jesus|\bThem\b|\bThey\b|infinite|dream(?:ing|er)?|remembering|the One\b|Someone\b)"
QUOTE_SPAN = re.compile(r"\*[^*]+\*|\"[^\"]+\"|“[^”]+”|> [^\n]+")

def body_of(piece_dir):
    src = open(os.path.join(piece_dir, 'draft.md'), encoding='utf-8').read()
    src = re.sub(r'<!--.*?-->', '', src, flags=re.S)
    if '\n---\n' in src:
        src = src.split('\n---\n', 1)[1]
    return src

def sentences(text):
    # Paragraphs first, so a paragraph head is always a sentence head (a forced capital there was
    # missed by a whole-file split); then sentences, allowing the sentence to close in a mark —
    # `*`, `"`, `”`, `]`, `)` — after its terminal punctuation, which is where the other misses were.
    out = []
    for para in re.split(r'\n\s*\n', text):
        flat = re.sub(r'\s+', ' ', para).strip()
        if not flat:
            continue
        out.extend(s.strip() for s in re.split(r'(?<=[.!?])[\*"”\]\)]*\s+(?=[“"\*\[\(]*[A-Z])', flat) if s.strip())
    return out

def ctx(s, m, w=70):
    return '…' + s[max(0, m.start()-w):m.end()+w] + '…'

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print(__doc__); sys.exit(1)
    piece = args[0].rstrip('/')
    names = []
    for a in sys.argv[1:]:
        if a.startswith('--names='):
            names = [n.strip() for n in a[8:].split(',') if n.strip()]
    if '--names' in sys.argv:
        i = sys.argv.index('--names'); names = [n.strip() for n in sys.argv[i+1].split(',')]
    strict = '--strict' in sys.argv
    # Justified C-hits live in publish.yaml under `pronouns_allow:` (one substring per line),
    # so the preflight can pass a hit whose referent has been named, and the justification
    # survives in a reviewable file rather than a flag somebody has to remember.
    allow = []
    try:
        in_block = False
        for ln in open(os.path.join(piece, 'publish.yaml'), encoding='utf-8'):
            if re.match(r'^pronouns_allow\s*:', ln):
                in_block = True; continue
            if in_block:
                m = re.match(r'^\s+-\s+(.*?)\s*(?:#.*)?$', ln)
                if m: allow.append(m.group(1).strip()); continue
                if ln.strip() and not ln.startswith(' '): in_block = False
    except FileNotFoundError:
        pass
    text = body_of(piece)
    sents = sentences(text)
    A, B, C, D = [], [], [], []
    name_re = re.compile(r'\b(' + '|'.join(map(re.escape, names)) + r')\b') if names else None
    for s in sents:
        # A — sentence-initial forced capitals
        m = re.match(r'^[“"\*\[]*(He|Him|His|They|Them|She|Her)\b', s)
        if m:
            A.append((m.group(1), s[:110]))
        # spans that are quotations — case inside them is the source's
        quoted = [(q.start(), q.end()) for q in QUOTE_SPAN.finditer(s)]
        def in_quote(i): return any(a <= i < b for a, b in quoted)
        # B — generic masculine
        for m in re.finditer(r"\b(he|him|his|himself|a man|the man|one man|any man|man who)\b", s):
            if in_quote(m.start()):
                continue
            tag = 'GENERIC?'
            if name_re:
                window = s[max(0, m.start()-120):m.start()]
                if name_re.search(window):
                    tag = 'named?  '
            B.append((tag, m.group(1), ctx(s, m, 60)))
        # C — lowercase oblique for God, or God as a what
        if re.search(GOD_WORDS, s):
            for m in re.finditer(r"\b(the one|someone|whoever|something|a mind|one mind|the mind|a thing|the thing)\b", s):
                if in_quote(m.start()):
                    continue
                window = s[max(0, m.start()-60):m.end()+60]
                if any(a in window for a in allow):
                    continue                                   # justified in publish.yaml
                C.append((m.group(1), ctx(s, m, 70)))
        # D — lowercase deity pronoun right after a God-word, outside quotations
        for m in re.finditer(r"\b(God|the Lord|the LORD|the Father|the Spirit|Christ|Jesus)\b((?:\s+\S+){0,6}?)\s+\b(he|him|his|it|its)\b", s):
            if in_quote(m.start(3)):
                continue
            D.append((m.group(3), ctx(s, m, 50)))
    print(f"check_pronouns — {os.path.basename(piece)}: {len(sents)} sentences")
    print(f"\nA. sentence-initial capitals to justify ({len(A)}):")
    for p, c in A: print(f"   {p:5s} {c}")
    print(f"\nB. masculine / 'a man' to justify ({len(B)}; {sum(1 for t,_,_ in B if t.startswith('GENERIC'))} unexplained):")
    for t, w, c in B: print(f"   {t} {w:8s} {c}")
    print(f"\nC. lowercase oblique near a God-word, or God as a *what* ({len(C)}):")
    for w, c in C: print(f"   {w:9s} {c}")
    print(f"\nD. lowercase deity pronoun outside a quotation ({len(D)}):")
    for w, c in D: print(f"   {w:4s} {c}")
    if strict and (C or D):
        print("\nSTRICT: C/D hits remain — justify or fix before compose.")
        sys.exit(3)

if __name__ == '__main__':
    main()
