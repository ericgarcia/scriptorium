# Fixture corpus

Not writing. These are **golden files** for `test_suite.py`, and they exist so the
framework's own tests can run in the framework's own repository.

The real corpus lives in an instance repo (`writing-desk/pieces/`), which is private.
If the suite only ever ran there, the JS patcher's regression tests — including the
one guarding the off-by-one that once deleted a footnote from a live post — would run
only in a repo that happens to hold drafts, and never in the repo that owns the code.

`kitchen-sink` is deliberately dense: it carries every construct that has ever caused
a converter bug — escaped asterisks, adjacent blockquotes, a bullet list, smart quotes,
an image, three footnotes (two are needed before the patcher's reorder check can run at
all), and a `†` editorial note that must be stripped before it can reach a post.

Its `sync-baseline.json` is a **golden hash**, sealed from the converter's own output.
Any change that alters rendering breaks CI here — which is the point. Reseal it only
when the change in output is the change you intended:

    python3 tools/test_suite.py --reseal-fixtures

`plain-draft` has no `public_url`; it exercises the "composed but not live" path.
