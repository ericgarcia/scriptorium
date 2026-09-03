#!/usr/bin/env python3
"""Tests for check_verified.py — the gate that would have stopped the Corey Taylor publish.

Each test is a scenario the gate exists to handle, named after the real event where possible.
Run: python3 framework/tools/test_check_verified.py
"""

import os
import sys
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_verified as cv  # noqa: E402


def piece(tmp, name, readme='', notes='', log='', draft='body\n', publish=None):
    d = os.path.join(tmp, 'pieces', name)
    os.makedirs(os.path.join(d, 'log'), exist_ok=True)
    open(os.path.join(d, 'README.md'), 'w').write(readme)
    open(os.path.join(d, 'notes.md'), 'w').write(notes)
    open(os.path.join(d, 'log', '2026-08.md'), 'w').write(log)
    open(os.path.join(d, 'draft.md'), 'w').write('# T\n\n*front*\n\n---\n\n' + draft)
    if publish is not None:
        open(os.path.join(d, 'publish.yaml'), 'w').write(publish)
    return d


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- the case this tool was built for -------------------------------------------------

    def test_the_corey_case_blocks(self):
        """The real 2026-08-25 failure: the doubt was in notes/log/README, never in the draft."""
        d = piece(self.tmp, 'kge',
                  readme='## Anchors to verify before print\nEvery quote must be checked against the audio.',
                  notes='Quotes pulled from a machine-generated transcript. Verify every quote before print.',
                  log='- **Standing caveat:** quotes still from the machine transcript.')
        _, hits, cleared = cv.check(d)
        self.assertTrue(hits, 'must find the scaffold doubts')
        self.assertIsNone(cleared)
        wheres = {h[0] for h in hits}
        self.assertEqual({'README.md', 'notes.md', 'log/2026-08.md'}, wheres,
                         'must look in all three places, not just the draft')

    def test_body_is_clean_but_scaffold_is_not(self):
        """The draft alone would pass every pre-existing guard. That is the whole gap."""
        d = piece(self.tmp, 'kge', notes='Verify every quote against the audio before print.',
                  draft='A perfectly clean body with no dagger and no verify note.\n')
        _, hits, _ = cv.check(d)
        self.assertTrue(hits)
        self.assertTrue(all(h[0] != 'draft.md' for h in hits))

    # --- fail closed ----------------------------------------------------------------------

    def test_silence_is_not_clearance(self):
        d = piece(self.tmp, 'quiet', readme='A tidy README that says nothing about sources.')
        _, hits, cleared = cv.check(d)
        self.assertEqual([], hits)
        self.assertIsNone(cleared)
        self.assertEqual((None, None), cv.scaffold_clearance(d))

    # --- clearance ------------------------------------------------------------------------

    def test_publish_yaml_clearance_is_found(self):
        d = piece(self.tmp, 'ok', publish='title: X\nverified:\n  date: 2026-09-02\n  by: Eric\n')
        self.assertIn('2026-09-02', cv.clearance(d))

    def test_scaffold_clearance_is_accepted_and_located(self):
        d = piece(self.tmp, 'ok', readme='**All 15 anchors verified** against the KJV.')
        text, where = cv.scaffold_clearance(d)
        self.assertIsNotNone(text)
        self.assertEqual('README.md', where)

    def test_a_closed_statement_does_not_read_as_a_doubt(self):
        """'zero unverified markers remain' is a clearance, not an open verify note."""
        d = piece(self.tmp, 'ok',
                  readme='ALL 12 ANCHORS VERIFIED 2026-09-01 — zero unverified markers remain.')
        _, hits, _ = cv.check(d)
        self.assertEqual([], hits, 'a resolved sentence must not count as a blocker')

    def test_half_cleared_still_blocks(self):
        """A clearance plus an open doubt is not clear — the way-home-is-down shape."""
        d = piece(self.tmp, 'half',
                  readme='Anchors VERIFIED 2026-08-26 — all 32 footnotes checked.',
                  notes='The (unverified) anchor ledger for the Dostoevsky references.')
        _, hits, _ = cv.check(d)
        self.assertTrue(hits)
        self.assertIsNotNone(cv.scaffold_clearance(d)[0])

    # --- the dagger ------------------------------------------------------------------------

    def test_dagger_in_the_body_blocks(self):
        d = piece(self.tmp, 'dag', draft='A claim.† verify this locus before print\n')
        _, hits, _ = cv.check(d)
        self.assertTrue(any('†' in h[2] for h in hits))

    # --- the log is history --------------------------------------------------------------

    def test_log_only_doubt_blocks_when_nothing_is_cleared(self):
        """The Corey caveat lived in a log. Without a clearance it must still block."""
        d = piece(self.tmp, 'kge', log='- **Standing caveat:** quotes still from the transcript.')
        _, hits, _ = cv.check(d)
        self.assertTrue(hits, 'a log doubt blocks while no clearance is recorded')

    def test_a_dated_clearance_makes_the_log_history(self):
        """An append-only log entry must not block a piece forever once it has been cleared.

        The 2026-08 entry can never be edited, so if it kept blocking, the only way past the gate
        would be to falsify the log. check_refs.py exempts log/ for the same reason.
        """
        d = piece(self.tmp, 'kge', log='- Wrote notes (the full unverified anchor ledger), this log.',
                  publish='title: X\nverified:\n  date: 2026-09-02\n  by: Eric\n')
        _, hits, cleared = cv.check(d)
        self.assertIsNotNone(cleared)
        self.assertEqual([], hits, 'a dated clearance makes an old log entry history')

    def test_readme_doubt_still_blocks_despite_a_clearance(self):
        """README/notes describe the CURRENT state, so they are not excused by a clearance."""
        d = piece(self.tmp, 'kge', readme='## Anchors to verify before print',
                  publish='title: X\nverified:\n  date: 2026-09-02\n  by: Eric\n')
        _, hits, cleared = cv.check(d)
        self.assertIsNotNone(cleared)
        self.assertTrue(hits, 'a current-state doubt is not superseded by a clearance')

    # --- front matter -----------------------------------------------------------------------

    def test_unverified_in_draft_front_matter_blocks(self):
        """i-believe-in-you and krishna-and-christ both shipped saying this."""
        d = os.path.join(self.tmp, 'pieces', 'fm')
        os.makedirs(os.path.join(d, 'log'), exist_ok=True)
        open(os.path.join(d, 'draft.md'), 'w').write(
            '# T\n\n*References UNVERIFIED — see notes.md*\n\n---\n\nclean body\n')
        _, hits, _ = cv.check(d)
        self.assertTrue(any('front-matter' in h[0] for h in hits))


if __name__ == '__main__':
    unittest.main(verbosity=2)
