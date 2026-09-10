#!/usr/bin/env python3
"""Check a draft's scripture quotations against an indexed KJV.

WHY THIS EXISTS
  `check_verified.py` records whether anyone SAID they checked, and says plainly
  that it cannot tell you a citation is correct. For scripture that gap is
  closable: the text is a fixed, indexable source. (Eric, 2026-09-10.)

  On this desk it matters more than average. The house quotes scripture constantly,
  quotes it in fragments, elides with an ellipsis, and starts quotations
  mid-sentence — every one of which is a way for a quotation to drift without
  anybody noticing.

WHAT MAKES THIS HARDER THAN A STRING COMPARE
  **The house alters its quotations on purpose**, and a checker that does not know
  the conventions reports every correctly-styled quote as an error, which is worse
  than no checker — it trains you to ignore it.

  1. **Bracketed substitution.** The Father's pronoun is replaced and bracketed:
     *and [Them] only shalt thou serve* for the King James's *him*. The bracket is
     the disclosure. Reported as SUBSTITUTION, never as drift.
  2. **Deity pronoun casing.** *He / Him / His / Me / My* are capitalized in the
     author's prose where the King James lowercases them. Reported as RECASED.
  3. **The King James's own brackets.** This edition prints translators' supplied
     words as [was], [is], [there be]. A quotation may keep or drop them.
  4. **Ellipsis and mid-sentence starts.** *Whatsoever things are true… think on
     these things* is three fragments of one verse, and its opening capital is the
     author's. Each fragment is matched in order.

  So the comparison runs on a normalized form, and every difference the normalizer
  absorbed is REPORTED rather than hidden. A quote that matches only after a
  substitution is not the same as one that matches outright, and you get told which.

USAGE
  python3 check_scripture.py <piece_dir> [--index <kjv.tsv.gz>] [-v]

EXIT
  0  every locus resolved and every quotation matched
  1  usage / no draft / no index
  4  a quotation does not match its locus, or a locus is not in the index
"""
import sys, os, re, gzip, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))

# The INDEX IS CONTENT AND LIVES IN THE INSTANCE, not here. The framework stays
# generic — no publication specifics, no source texts — and a whole Bible is a
# source text with its own provenance and redistribution status, which is what
# `books/<name>/references/` exists to record. The framework ships the builder;
# the instance ships the book.
INDEX_CANDIDATES = [
    os.environ.get("KJV_INDEX", ""),
    "references/kjv.tsv.gz",
    "books/being-good/references/kjv.tsv.gz",
]


def find_index():
    import glob
    for c in INDEX_CANDIDATES:
        if c and os.path.exists(c):
            return c
    hits = sorted(glob.glob("books/*/references/kjv.tsv.gz"))
    return hits[0] if hits else None

# The book must come from the closed set. A loose pattern matched "And 22:17" as a
# book called "And" (measured on false-light, 2026-09-10) — the same class of error
# as the index's "Page 621 John" matching "1 John". Names are known; use them.
from refindex import KJV_BOOKS, HEADER_ALIASES
ALIASES = dict(HEADER_ALIASES)
ALIASES.update({"Psalm": "Psalms"})
_NAMES = sorted(set(KJV_BOOKS) | set(ALIASES), key=len, reverse=True)
LOCUS_RE = re.compile(r"\b(" + "|".join(re.escape(b) for b in _NAMES) +
                      r")\s+(\d+):(\d+)(?:\s*[-–—]\s*(\d+))?")


def load(path):
    op = gzip.open if path.endswith(".gz") else open
    idx = {}
    with op(path, "rt", encoding="utf-8") as f:
        for line in f:
            b, c, v, t = line.rstrip("\n").split("\t")
            idx[(b, int(c), int(v))] = t
    return idx


def strip_brackets(t):
    """Keep the words the King James italicizes; drop only the brackets."""
    return re.sub(r"\[([^\]]*)\]", r"\1", t)


def norm(t):
    t = unicodedata.normalize("NFKD", t)
    t = t.replace("’", "'").replace("‘", "'")
    t = t.replace("“", '"').replace("”", '"')
    t = strip_brackets(t)
    t = re.sub(r"[^a-z0-9' ]+", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def footnotes(draft):
    body = draft.split("\n---\n", 1)[-1]
    m = re.search(r"^\[\^[\w-]+\]:", body, re.M)
    if not m:
        return []
    tail, out = body[m.start():], []
    starts = [(x.group(1), x.start()) for x in re.finditer(r"^\[\^([\w-]+)\]:", tail, re.M)]
    for i, (k, st) in enumerate(starts):
        en = starts[i + 1][1] if i + 1 < len(starts) else len(tail)
        out.append((k, " ".join(tail[st:en].split())))
    return out


def quoted_spans(text):
    """Italic spans are how this house sets a quotation — and also how it sets a
    sibling essay's title, a Greek phrase, and ordinary emphasis.

    A checker that flags all of them is worse than none: it trains the reader to
    skim past it, which is the failure this tool exists to prevent. So a span is
    a candidate only if it LOOKS like it is trying to be this verse — measured by
    how much of it actually appears in the verse. A span with almost nothing in
    common is commentary; a span with most of the verse is a quotation; the band
    between them is reported as SUSPECT rather than judged either way, because
    that is exactly where a real drift would sit.

    Titles are removed outright first: a `[*Title*](url)` is a link, never a quote.
    """
    text = re.sub(r"\[\*[^*]+\*\]\([^)]*\)", " ", text)
    return [s for s in re.findall(r"\*([^*]{12,})\*", text)]


def overlap(span, canon):
    """Fraction of the span's words that sit in the verse as one contiguous run."""
    w = norm(span).split()
    if not w:
        return 0.0
    best = 0
    for i in range(len(w)):
        for j in range(len(w), i + best, -1):
            if " ".join(w[i:j]) in canon:
                best = max(best, j - i)
                break
    return best / len(w), best


def quote_pattern(fragment):
    """A bracketed word in a DRAFT quotation is a wildcard, not a word to match.

    The two directions of a bracket are not the same thing and must not be treated
    alike. In the CANONICAL text, [was] / [is] are the King James's own italics for
    words the translators supplied — real words, kept. In a DRAFT quotation,
    [Them] / [They do] are the house's disclosed substitution for a pronoun, and
    the bracket is precisely the statement that this is not what the source says.

    Comparing the substituted word against the source therefore reports the
    convention as drift — which is how *and that [Their] fear may be before you*
    read as an error against the King James's *his* (measured 2026-09-10, three
    pieces). The bracket matches whatever the source has there.
    """
    out = []
    for i, chunk in enumerate(re.split(r"(\[[^\]]*\])", fragment)):
        if i % 2:
            out.append(r"[\w' ]{0,24}")          # the disclosed substitution
        elif norm(chunk):
            out.append(re.escape(norm(chunk)).replace(r"\ ", " "))
    return r"\s*".join(x for x in out if x)


def match(quote, canon):
    """Return (ok, detail). Fragments split on an ellipsis must appear in order."""
    parts = [p for p in re.split(r"\s*(?:\.\.\.|…)\s*", quote) if norm(p)]
    pos, missed = 0, None
    for p in parts:
        pat = quote_pattern(p)
        if not pat:
            continue
        m = re.compile(pat).search(canon, pos)
        if not m:
            missed = p
            break
        pos = m.end()
    if missed is None:
        return True, ("whole verse" if len(parts) == 1 and norm(quote) == canon
                      else f"{len(parts)} fragment(s), in order")
    words = norm(missed).split()
    for n in range(len(words), 2, -1):
        if canon.find(" ".join(words[:n])) >= 0:
            return False, (f"diverges after …{' '.join(words[max(0,n-6):n])}… "
                           f"→ draft has ‘{words[n] if n < len(words) else ''}’")
    return False, f"not found: ‘{missed[:60]}’"


def house_changes(quote, canonical):
    """What the normalizer absorbed, reported so it is a decision and not a silence."""
    notes = []
    for w in re.findall(r"\[([A-Z][a-z]+|[A-Z]+)\]", quote):
        notes.append(f"SUBSTITUTION [{w}] — bracketed, the house disclosure")
    low = strip_brackets(canonical)
    for pron in ("He", "Him", "His", "Me", "My", "Mine", "Thee", "Thy"):
        if re.search(rf"\b{pron}\b", quote) and re.search(rf"\b{pron.lower()}\b", low):
            notes.append(f"RECASED {pron.lower()} → {pron}")
    return notes


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__.strip()); sys.exit(1)
    piece = args[0].rstrip("/")
    draft_path = os.path.join(piece, "draft.md")
    if not os.path.exists(draft_path):
        print(f"no draft.md in {piece}"); sys.exit(1)
    index_path = (sys.argv[sys.argv.index("--index") + 1]
                  if "--index" in sys.argv else find_index())
    if not index_path or not os.path.exists(index_path):
        print("no KJV index found. The framework ships the builder; the index is\n"
              "content and lives in the instance, with its provenance recorded:\n"
              "  python3 framework/tools/refindex.py <kjv.pdf> --scheme kjv \\\n"
              "      --out books/<name>/references/kjv.tsv.gz\n"
              "then add a row to that folder's README (work, edition, date,\n"
              "redistribution status), as every other reference file has.")
        sys.exit(1)
    idx = load(index_path)
    verbose = "-v" in sys.argv

    checked = bad = 0
    for name, note in footnotes(draft_path and open(draft_path).read()):
        # A footnote may cite more than one verse — this house routinely raises a
        # counterweight in the same note (1 Thess 5:18 answered by Eph 5:20). Check
        # every quotation against EVERY locus the note cites, or the second verse's
        # quotation reads as drift against the first verse.
        keys = []
        for lm in LOCUS_RE.finditer(note):
            book = ALIASES.get(lm.group(1), lm.group(1))
            k = (book, int(lm.group(2)), int(lm.group(3)))
            if k not in keys:
                keys.append(k)
        if not keys:
            continue
        print(f"[^{name}] " + " · ".join(f"{b} {c}:{v}" for b, c, v in keys))
        unknown = [k for k in keys if k not in idx]
        if unknown:
            for b, c, v in unknown:
                print(f"   NOT IN INDEX — {b} {c}:{v} does not exist in this edition")
            bad += len(unknown)
        keys = [k for k in keys if k in idx]
        if not keys:
            continue
        canons = {k: norm(idx[k]) for k in keys}
        spans = quoted_spans(note)
        if not spans:
            print("   locus only, no quotation to check"); continue
        skipped = 0
        for q in spans:
            key, (score, run) = max(((k, overlap(q, canons[k])) for k in keys),
                                    key=lambda kv: kv[1])
            canon = canons[key]
            # A short commentary fragment can score high on one common word, so a
            # candidate needs an absolute run too: "What the ellipsis drops" hits
            # 25% on the word "the" alone.
            if score < 0.25 or run < 4:
                skipped += 1
                if verbose:
                    print(f"   skipped (not a quotation of this verse): {' '.join(q.split())[:60]}")
                continue
            checked += 1
            ok, detail = match(q, canon)
            if ok:
                where = f" — {key[0]} {key[1]}:{key[2]}" if len(keys) > 1 else ""
                print(f"   MATCH   {detail}{where}")
                for n in house_changes(q, idx[key]):
                    print(f"     {n}")
                if verbose:
                    print(f"     KJV  : {idx[key][:110]}")
                continue

            # The commonest real finding is not drift but an UNDER-CITED RANGE: the
            # quotation continues into the next verse while the note names only the
            # first. Extend forward before calling anything wrong.
            # Extend BOTH ways: a quotation can begin before the verse the note
            # names as easily as it can run past it (2 Corinthians 11:13-14 cited
            # as 11:14, measured on false-light 2026-09-10).
            b, c, v = key
            span_lo = span_hi = None
            for lo in range(v, max(0, v - 4) - 1, -1):
                for hi in range(v, v + 5):
                    if (b, c, lo) not in idx or (b, c, hi) not in idx or (lo, hi) == (v, v):
                        continue
                    joined = " ".join(idx[(b, c, i)] for i in range(lo, hi + 1))
                    if match(q, norm(joined))[0]:
                        span_lo, span_hi = lo, hi
                        break
                if span_lo:
                    break
            bad += 1
            if span_lo:
                rng = f"{c}:{span_lo}" if span_lo == span_hi else f"{c}:{span_lo}-{span_hi}"
                print(f"   RANGE   the quotation covers {b} {rng}, but the note cites "
                      f"only {c}:{v} — cite {rng}")
            elif score < 0.6:
                print(f"   SUSPECT only {int(score*100)}% of the span is in the verse — "
                      f"read it; a real drift looks like this")
                print(f"     draft: {' '.join(q.split())[:110]}")
                print(f"     KJV  : {idx[key][:110]}")
            else:
                print(f"   DRIFT   {detail}")
                print(f"     draft: {' '.join(q.split())[:110]}")
                print(f"     KJV  : {idx[key][:110]}")
        if skipped and not verbose:
            print(f"   ({skipped} italic span(s) skipped as commentary — -v to list)")

    print(f"\n{checked} quotation(s) checked, {bad} problem(s)")
    sys.exit(4 if bad else 0)


if __name__ == "__main__":
    main()
