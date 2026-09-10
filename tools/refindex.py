#!/usr/bin/env python3
"""Turn a reference PDF into an index the desk can check quotations against.

WHY THIS EXISTS
  `check_verified.py` asks whether anyone SAID they checked a source. It cannot
  tell you a citation is right, and it says so. For the sources the desk owns as
  PDFs, that gap is closable: the text is right there.

  (Eric, 2026-09-10: *"in general, scriptorium framework should be able to use a
  pdf to check references."*)

  So: index once, check many. A scripture locus becomes a lookup; a quotation from
  any other source becomes a search with a page number attached.

SCHEMES
  pages   (default)  one row per page: <page>\\t<text>. Works on any PDF.
  kjv                one row per verse: <book>\\t<ch>\\t<v>\\t<text>.

USAGE
  python3 refindex.py <pdf> --out <index.tsv[.gz]> [--scheme kjv|pages]
  python3 refindex.py --verify <index.tsv[.gz]>        # scheme-aware sanity check

WHY THE KJV SCHEME USES A CLOSED BOOK LIST
  This edition prints its running header both ways round — "1 Thessalonians Page
  682" and "Page 681 1 Thessalonians" — so a regex that reads the header
  non-greedily captures "1" from the second form, and "Page N 3 John" invents a
  book called "3". Measured 2026-09-10: header parsing produced 67 books and lost
  1,455 verses. The 66 names are a closed set; use them.

  And do NOT filter blocks by geometry to drop the header. On this PDF the header
  shares a text block with verse text, so a header band filter deletes scripture —
  it cost 6,694 verses before anyone counted. `get_text()` already returns this
  PDF's two columns in reading order.
"""
import sys, os, re, gzip, unicodedata

KJV_BOOKS = [
    "Genesis","Exodus","Leviticus","Numbers","Deuteronomy","Joshua","Judges","Ruth",
    "1 Samuel","2 Samuel","1 Kings","2 Kings","1 Chronicles","2 Chronicles","Ezra",
    "Nehemiah","Esther","Job","Psalms","Proverbs","Ecclesiastes","Song of Solomon",
    "Isaiah","Jeremiah","Lamentations","Ezekiel","Daniel","Hosea","Joel","Amos",
    "Obadiah","Jonah","Micah","Nahum","Habakkuk","Zephaniah","Haggai","Zechariah",
    "Malachi","Matthew","Mark","Luke","John","Acts","Romans","1 Corinthians",
    "2 Corinthians","Galatians","Ephesians","Philippians","Colossians",
    "1 Thessalonians","2 Thessalonians","1 Timothy","2 Timothy","Titus","Philemon",
    "Hebrews","James","1 Peter","2 Peter","1 John","2 John","3 John","Jude",
    "Revelation",
]
# A running header does not always print the canonical name: this edition heads
# Song of Solomon as "Song of Songs". Aliases are matched like any other header
# and folded to the canonical book, so a locus written the usual way resolves.
HEADER_ALIASES = {"Song of Songs": "Song of Solomon", "Canticles": "Song of Solomon",
                  "Psalm": "Psalms", "The Revelation": "Revelation"}

# longest first, so "1 John" wins over "John" and "Song of Solomon" over "Song"
_BOOK_RE = re.compile("(" + "|".join(re.escape(b) for b in
                      sorted(KJV_BOOKS + list(HEADER_ALIASES), key=len, reverse=True)) + ")")
KJV_VERSES = 31102


def opener(path, mode="rt"):
    return gzip.open(path, mode, encoding="utf-8") if path.endswith(".gz") else open(path, mode)


def page_texts(pdf):
    import fitz
    doc = fitz.open(pdf)
    for n, page in enumerate(doc, 1):
        yield n, re.sub(r"\s+", " ", page.get_text()).strip()


def clean(t):
    t = unicodedata.normalize("NFC", t)
    t = re.sub(r"\s+", " ", t).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", t)


def build_pages(pdf, out):
    with opener(out, "wt") as f:
        n = 0
        for page, text in page_texts(pdf):
            if text:
                f.write(f"{page}\t{clean(text)}\n"); n += 1
    return f"{n} pages"


def build_kjv(pdf, out):
    """Accumulate each book's stream, then split it on {chapter:verse} markers."""
    streams, order, book = {}, [], None
    for _, text in page_texts(pdf):
        if not text:
            continue
        # Strip a leading "Page N" FIRST, then require the book name at position 0.
        # A loose search finds a book name anywhere in the head — and the page
        # number's own last digit forms one: "Page 621 John" matches "1 John" under
        # longest-first alternation, which filed 26 Gospel verses under 1 John and
        # 3 John (measured 2026-09-10). The header is a prefix; match it like one.
        head = re.sub(r"^Page\s+\d+\s*", "", text)
        m = _BOOK_RE.match(head)
        if m:
            book = HEADER_ALIASES.get(m.group(1), m.group(1))
            text = head[m.end():]
            if book not in streams:
                streams[book] = []; order.append(book)
        if book is None or "{" not in text:
            continue
        streams.setdefault(book, []).append(text)

    rows, seen = [], set()
    for book in order:
        s = re.sub(r"\{\s*(\d+)\s*:\s*(\d+)\s*\}", r"{\1:\2}", " ".join(streams[book]))
        parts = re.split(r"\{(\d+):(\d+)\}", s)
        for i in range(1, len(parts), 3):
            c, v, t = int(parts[i]), int(parts[i + 1]), clean(parts[i + 2])
            if t and (book, c, v) not in seen:
                seen.add((book, c, v)); rows.append((book, c, v, t))
    with opener(out, "wt") as f:
        for book, c, v, t in rows:
            f.write(f"{book}\t{c}\t{v}\t{t}\n")
    return f"{len(rows)} verses, {len(order)} books"


def verify(path):
    """Fail on what breaks a lookup; report what does not.

    An interior gap is fatal: a chapter missing verse 9 will answer "not in index"
    for a locus that exists, and the reader of that answer will not know whether
    the citation or the index is wrong. A missing or unknown book is fatal for the
    same reason.

    A shortfall at the END of chapters is a property of the source edition, not of
    the parse. This PDF carries 31,098 verse markers where the canonical KJV has
    31,102; the four are absent from the file itself (their markers do not appear
    in its raw text). That is reported, never silently absorbed — and it costs
    nothing, because a locus the index does not hold is reported NOT FOUND rather
    than passed.
    """
    import collections
    rows = [l.rstrip("\n").split("\t") for l in opener(path) if l.strip()]
    if not (rows and len(rows[0]) == 4):
        print(f"page index: {len(rows)} pages")
        return 0

    books = {r[0] for r in rows}
    missing = [b for b in KJV_BOOKS if b not in books]
    extra = sorted(books - set(KJV_BOOKS))
    chapters = collections.defaultdict(set)
    for b, c, v, _ in rows:
        chapters[(b, int(c))].add(int(v))
    gaps = []
    for (b, c), vs in sorted(chapters.items()):
        holes = [x for x in range(1, max(vs) + 1) if x not in vs]
        if holes:
            gaps.append(f"{b} {c}: missing {holes[:6]}")

    print(f"kjv index: {len(rows)} verses, {len(books)} books, {len(chapters)} chapters")
    ok = True
    if missing:
        print(f"  MISSING BOOKS ({len(missing)}): {missing}"); ok = False
    if extra:
        print(f"  UNKNOWN BOOKS ({len(extra)}): {extra}"); ok = False
    if gaps:
        print(f"  INTERIOR GAPS ({len(gaps)}) — fatal, a lookup would answer wrongly:")
        for g in gaps[:10]:
            print(f"    {g}")
        ok = False
    delta = len(rows) - KJV_VERSES
    if delta:
        print(f"  note: {abs(delta)} verse(s) {'fewer' if delta < 0 else 'more'} than the "
              f"canonical {KJV_VERSES:,} — a property of this edition, not of the parse; "
              f"any locus not held is reported NOT FOUND, never passed")
    print("  OK" if ok else "  NOT USABLE AS A CHECKER")
    return 0 if ok else 4


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__.strip()); sys.exit(1)
    if a[0] == "--verify":
        sys.exit(verify(a[1]))
    pdf = a[0]
    out = a[a.index("--out") + 1] if "--out" in a else None
    scheme = a[a.index("--scheme") + 1] if "--scheme" in a else "pages"
    if not out:
        print("--out is required"); sys.exit(1)
    if not os.path.exists(pdf):
        print(f"no such pdf: {pdf}"); sys.exit(1)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    got = build_kjv(pdf, out) if scheme == "kjv" else build_pages(pdf, out)
    print(f"{got} -> {out}")
    sys.exit(verify(out))


if __name__ == "__main__":
    main()
