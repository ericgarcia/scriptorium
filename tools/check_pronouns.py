#!/usr/bin/env python3
"""check_pronouns.py — the pronoun sweeps this desk kept doing by hand, as one tool.

WHY THIS EXISTS (2026-09-03).  Three pronoun rules live in the constitutions and all three
were being enforced by ad-hoc greps typed fresh in each session — and a rule that is not in
the sweep list is not in force.  *The Mask Comes Off Last* reached a composed Substack draft
carrying twenty-one generic masculines for the villain (the 2026-09-01 rule said they/them),
and then a lowercase *the one* for God (the essay voice capitalizes an oblique reference to
God: *the One*, *Someone*).  Both were caught by Eric, after compose, reading the page.

WHY E AND F EXIST (2026-09-07).  The first four sections stop at a quotation's edge — inside
one, the source's case was taken as evidence and left alone.  But the constitution's casing and
bracket rules reach INSIDE this house's own scripture (see `God_in_quotations`,
`God_in_quotations_casing`, `God_in_quotations_exclusions` in the essay voice's config.yaml), and
nothing was sweeping there.  *False Light*, 2026-09-07, measured four misses in one draft, all
inside italic King James quotations: Matthew 4:10 *Him only shalt thou serve* (a capitalized
*Him* whose referent is the Father — the house pronoun is *[Them]*, bracketed, since that is a
substitution); Matthew 5:45 *He maketh His sun* (same: Father, so *[They make] [Their] sun*);
John 5:30 *of mine own self* and John 15:5 *without me* (the Son speaking, whose own pronouns
the house capitalizes inside a quotation — *Me*, *My*, *Mine* — as a casing convention, never
bracketed).  Eric caught the first one reading the page; the rest fell out of the audit it
prompted.  A sweep that stops at the quotation's edge cannot see any of them.

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
  E. CAPITALIZED He/Him/His/Himself INSIDE A SCRIPTURE QUOTATION.  A capital there is the house
     saying *this is the Son*.  If the referent is the Father, the word is wrong, not the case:
     God-as-God is *They/Them*, and inside a verbatim quotation that is a substitution, so it is
     bracketed — *[Them] only shalt thou serve* — with the verb bracketed too where agreement
     needs it (*[They make]*, never *[They] maketh*).  The tool cannot know the referent; it
     lists every hit with its sentence, and each is justified as the Son or repaired.
  F. LOWERCASE me/my/mine/myself INSIDE A GOSPEL QUOTATION.  Where the speaker is the Son the
     house capitalizes His own pronouns in the quotation — *He that hath seen Me hath seen the
     Father* — as a casing convention (never bracketed, disclosed once per piece).  Heuristic:
     the quotation is followed by a footnote ref whose definition cites a Gospel (Matthew, Mark,
     Luke, John — not 1/2/3 John) and it contains a first-person pronoun.  A Gospel voice is not
     always Jesus (the prodigal's *make me as one of thy hired servants*), so it lists, and the
     operator names the speaker.

  WHAT COUNTS AS A SCRIPTURE QUOTATION, for E and F: an italic span `*…*` that is followed by a
  footnote ref whose definition cites the KJV or a book of the Bible, or a blockquote (`> …`)
  carrying such a ref.  For E only, an italic span or blockquote with no ref but King James
  diction (thou / thee / thy / ye / hath / shalt / -eth …) also counts — the Matthew 4:10 miss
  was exactly a span whose ref sat on a different span two sentences earlier.  Each hit says
  which evidence qualified it (`ref:matt4` or `kjv-diction`).  Footnote DEFINITIONS are never
  swept by E or F: the footnote that records the source wording keeps it unaltered, and is the
  disclosure.  The three exclusions in the constitution (another organization's fixed text; a
  text quoted as evidence about its translators; any non-Judeo-Christian scripture) are
  judgments the tool cannot make — a hit inside one of those is justified by naming the
  exclusion, exactly as a section-B hit is justified by naming the person.

It REPORTS; it does not edit, and it cannot know a referent.  The operator justifies every hit
by naming who it points at — that is the sweep, and this tool only makes sure it happens.

USAGE
    python3 check_pronouns.py <piece-dir> [--names A,B,C] [--strict]
      --names   comma-separated named figures whose pronouns are theirs (Campbell,Peter,...)
      --strict  exit 3 if any C or D hit remains (for a publish preflight); A, B, E and F
                always exit 0 because they are lists to be justified, not verdicts — E and F
                each need a human call on a referent or a speaker, which no rule can make.
    A C-hit whose referent is NOT God is justified by listing a substring of it in the piece's
    publish.yaml under `pronouns_allow:` — reviewable, and it survives the session.
EXIT  0 clean or only A/B/E/F listings · 3 C/D hits under --strict · 1 usage
"""
import os, re, sys

GOD_WORDS = r"(God|the Lord|the LORD|the Father|the Spirit|Christ|Jesus|\bThem\b|\bThey\b|infinite|dream(?:ing|er)?|remembering|the One\b|Someone\b)"
QUOTE_SPAN = re.compile(r"\*[^*]+\*|\"[^\"]+\"|“[^”]+”|> [^\n]+")
SENT_SPLIT = re.compile(r'(?<=[.!?])[\*"”\]\)]*\s+(?=[“"\*\[\(]*[A-Z])')

# A footnote definition "cites scripture" when it names the King James or a book of the Bible.
BIBLE_BOOKS = (
    "Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Joshua|Judges|Ruth|Samuel|Kings|Chronicles|Ezra|"
    "Nehemiah|Esther|Job|Psalms?|Proverbs|Ecclesiastes|Song of Solomon|Song of Songs|Isaiah|Jeremiah|"
    "Lamentations|Ezekiel|Daniel|Hosea|Joel|Amos|Obadiah|Jonah|Micah|Nahum|Habakkuk|Zephaniah|Haggai|"
    "Zechariah|Malachi|Matthew|Mark|Luke|John|Acts|Romans|Corinthians|Galatians|Ephesians|"
    "Philippians|Colossians|Thessalonians|Timothy|Titus|Philemon|Hebrews|James|Peter|Jude|Revelation|"
    "Gen|Ex|Lev|Num|Deut|Ps|Prov|Eccl|Isa|Jer|Ezek|Dan|Matt|Mk|Lk|Jn|Rom|Cor|Gal|Eph|Phil|Col|Thess|Tim|Heb|Rev"
)
SCRIPTURE_REF = re.compile(r"\bKJV\b|King James|\b(?:[1-3]\s*)?(?:" + BIBLE_BOOKS + r")\.?\s+\d+(?::\d+)?")
# A Gospel, and not an epistle of John: "1 John 4:19" is blocked by the lookbehind on a digit.
GOSPEL_REF = re.compile(r"(?<![0-9])(?<![0-9]\s)\b(?:Matthew|Matt|Mark|Mk|Luke|Lk|John|Jn)\.?\s+\d+(?::\d+)?")
KJV_DICTION = re.compile(r"\b(?:thou|thee|thy|thine|ye|hath|doth|saith|shalt|wilt|unto|[a-z]{3,}eth)\b", re.I)
FIRST_PERSON = re.compile(r"\b(?:I|me|my|mine|myself|Me|My|Mine|Myself)\b")
FOOTNOTE_REFS_AFTER = re.compile(r'^[.,;:!?”"\)]*((?:\s*\[\^[^\]]+\])+)')
REF_LABEL = re.compile(r'\[\^([^\]]+)\]')

def body_of(piece_dir):
    src = open(os.path.join(piece_dir, 'draft.md'), encoding='utf-8').read()
    src = re.sub(r'<!--.*?-->', '', src, flags=re.S)
    if '\n---\n' in src:
        src = src.split('\n---\n', 1)[1]
    return src

def paragraphs(text):
    out = []
    for para in re.split(r'\n\s*\n', text):
        flat = re.sub(r'\s+', ' ', para).strip()
        if flat:
            out.append(flat)
    return out

def sentences(text):
    # Paragraphs first, so a paragraph head is always a sentence head (a forced capital there was
    # missed by a whole-file split); then sentences, allowing the sentence to close in a mark —
    # `*`, `"`, `”`, `]`, `)` — after its terminal punctuation, which is where the other misses were.
    out = []
    for flat in paragraphs(text):
        out.extend(s.strip() for s in SENT_SPLIT.split(flat) if s.strip())
    return out

def sentence_at(flat, i):
    """The sentence of a flattened paragraph that contains offset i (same split as sentences())."""
    bounds = [0] + [m.end() for m in SENT_SPLIT.finditer(flat)] + [len(flat)]
    for a, b in zip(bounds, bounds[1:]):
        if a <= i < b:
            return flat[a:b].strip()
    return flat.strip()

def footnote_defs(text):
    """label -> definition text, continuation lines (indented) folded in.  Raw text, not flattened."""
    defs, cur = {}, None
    for line in text.split('\n'):
        m = re.match(r'^\[\^([^\]]+)\]:\s*(.*)$', line)
        if m:
            cur = m.group(1); defs[cur] = m.group(2); continue
        if cur is not None and line[:1] in (' ', '\t') and line.strip():
            defs[cur] += ' ' + line.strip(); continue
        cur = None
    return defs

def ctx(s, m, w=70):
    return '…' + s[max(0, m.start()-w):m.end()+w] + '…'

def quotation_spans(flat, defs):
    """Scripture quotations in one flattened paragraph, as (start, end, text, evidence, gospel).

    evidence is `ref:<label>` when a footnote ref follows the span and its definition cites
    scripture, else `kjv-diction` when the span reads as King James; gospel is True only on the
    ref path, when the definition cites a Gospel.  A span with neither is not a quotation here."""
    spans = []
    if flat.startswith('>'):
        body = re.sub(r'(?:^|(?<=\s))>\s*', '', flat)
        candidates = [(0, len(flat), body, REF_LABEL.findall(body))]
    else:
        candidates = []
        for m in re.finditer(r'\*([^*]+)\*', flat):
            tail = FOOTNOTE_REFS_AFTER.match(flat[m.end():])
            labels = REF_LABEL.findall(tail.group(1)) if tail else []
            candidates.append((m.start(), m.end(), m.group(1), labels))
    for start, end, body, labels in candidates:
        cited = [l for l in labels if l in defs and SCRIPTURE_REF.search(defs[l])]
        if cited:
            gospel = any(GOSPEL_REF.search(defs[l]) for l in cited)
            spans.append((start, end, body, 'ref:' + ','.join(cited), gospel))
        elif KJV_DICTION.search(body):
            spans.append((start, end, body, 'kjv-diction', False))
    return spans

def load_allow(piece):
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
    return allow

def sweep(piece, names=(), allow=None):
    """Run every section over the piece.  Returns {'sentences': n, 'A': [...], ... 'F': [...]}."""
    allow = load_allow(piece) if allow is None else allow
    text = body_of(piece)
    sents = sentences(text)
    A, B, C, D, E, F = [], [], [], [], [], []
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
    # E and F look INSIDE scripture quotations, which A–D deliberately do not.  They run on
    # paragraphs, not sentences, because a quotation can hold more than one sentence and its
    # footnote ref sits after the closing `*`.  Footnote definitions are skipped: the note that
    # records the source wording keeps it unaltered, and is the disclosure.
    defs = footnote_defs(text)
    for flat in paragraphs(text):
        if re.match(r'^\[\^[^\]]+\]:', flat):
            continue
        for start, end, body, evidence, gospel in quotation_spans(flat, defs):
            for m in re.finditer(r"\b(He|Him|His|Himself)\b", body):
                E.append((m.group(1), evidence, sentence_at(flat, start + m.start())))
            if gospel and FIRST_PERSON.search(body):
                for m in re.finditer(r"\b(me|my|mine|myself)\b", body):
                    F.append((m.group(1), evidence, sentence_at(flat, start + m.start())))
    return {'sentences': len(sents), 'A': A, 'B': B, 'C': C, 'D': D, 'E': E, 'F': F}

def _clip(s, n=200):
    return s if len(s) <= n else s[:n] + '…'

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
    r = sweep(piece, names)
    A, B, C, D, E, F = (r[k] for k in 'ABCDEF')
    print(f"check_pronouns — {os.path.basename(piece)}: {r['sentences']} sentences")
    print(f"\nA. sentence-initial capitals to justify ({len(A)}):")
    for p, c in A: print(f"   {p:5s} {c}")
    print(f"\nB. masculine / 'a man' to justify ({len(B)}; {sum(1 for t,_,_ in B if t.startswith('GENERIC'))} unexplained):")
    for t, w, c in B: print(f"   {t} {w:8s} {c}")
    print(f"\nC. lowercase oblique near a God-word, or God as a *what* ({len(C)}):")
    for w, c in C: print(f"   {w:9s} {c}")
    print(f"\nD. lowercase deity pronoun outside a quotation ({len(D)}):")
    for w, c in D: print(f"   {w:4s} {c}")
    print(f"\nE. capitalized He/Him/His inside a scripture quotation — justify each as the Son, or bracket [Them] for the Father ({len(E)}):")
    for w, ev, c in E: print(f"   {w:8s} {ev:14s} {_clip(c)}")
    print(f"\nF. lowercase me/my/mine inside a Gospel quotation — the Son's own pronouns take the capital ({len(F)}):")
    for w, ev, c in F: print(f"   {w:8s} {ev:14s} {_clip(c)}")
    if strict:
        if E or F:
            print("\nSTRICT: E/F hits are warnings — each needs a referent or speaker named; not refused.")
        if C or D:
            print("\nSTRICT: C/D hits remain — justify or fix before compose.")
            sys.exit(3)

if __name__ == '__main__':
    main()
