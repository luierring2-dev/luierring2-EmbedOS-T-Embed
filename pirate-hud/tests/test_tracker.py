import csv
import json
import math
import tempfile
import unittest
from pathlib import Path

from tracker import (DUPLICATE_START_WINDOW, Tracker, chests_for, fmt_int, fmt_pct,
                     p_at_least_one)

P = 1 / 137500


class MathTest(unittest.TestCase):
    def test_zero_and_bounds(self):
        self.assertEqual(p_at_least_one(0, P), 0.0)
        self.assertEqual(p_at_least_one(10, 0), 0.0)
        self.assertEqual(p_at_least_one(1, 1.0), 1.0)

    def test_one_chest_is_p(self):
        self.assertAlmostEqual(p_at_least_one(1, P), P, places=15)

    def test_matches_naive_formula(self):
        for n in (1, 10, 1000, 95306, 500000):
            self.assertAlmostEqual(p_at_least_one(n, P), 1 - (1 - P) ** n, places=9)

    def test_n50_is_exact_threshold(self):
        n50 = chests_for(0.5, P)
        self.assertGreaterEqual(p_at_least_one(n50, P), 0.5)
        self.assertLess(p_at_least_one(n50 - 1, P), 0.5)
        self.assertEqual(n50, 95308)

    def test_n90(self):
        n90 = chests_for(0.9, P)
        self.assertGreaterEqual(p_at_least_one(n90, P), 0.9)
        self.assertLess(p_at_least_one(n90 - 1, P), 0.9)

    def test_infinite_when_no_chance(self):
        self.assertEqual(chests_for(0.5, 0), math.inf)


class FormatTest(unittest.TestCase):
    def test_int(self):
        self.assertEqual(fmt_int(0), "0")
        self.assertEqual(fmt_int(137500), "137.500")
        self.assertEqual(fmt_int(1234567), "1.234.567")
        self.assertEqual(fmt_int(math.inf), "∞")

    def test_pct(self):
        self.assertEqual(fmt_pct(0), "0 %")
        self.assertEqual(fmt_pct(0.0089), "0,89 %")
        self.assertEqual(fmt_pct(P), "0,00073 %")
        self.assertEqual(fmt_pct(0.5), "50,0 %")
        self.assertEqual(fmt_pct(0.012345), "1,23 %")
        self.assertEqual(fmt_pct(0.99999), "99,9 %")
        self.assertEqual(fmt_pct(1.0), "100 %")


class TrackerTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.t = Tracker(self.dir, 137500)

    def test_chest_and_undo(self):
        for _ in range(3):
            self.t.chest()
        self.assertEqual(self.t.undo(), "kiste")
        s = self.t.state
        self.assertEqual((s.total_chests, s.since_find, s.match_chests), (2, 2, 2))

    def test_undo_never_negative(self):
        self.assertIsNone(self.t.undo())
        self.assertEqual(self.t.state.total_chests, 0)

    def test_found_resets_and_undo_restores(self):
        for _ in range(5):
            self.t.chest()
        self.assertEqual(self.t.found(now=1000), 5)
        self.assertEqual(self.t.state.since_find, 0)
        self.assertEqual(self.t.state.total_chests, 5)
        self.assertEqual(self.t.undo(), "fund")
        self.assertEqual(self.t.state.since_find, 5)
        self.assertEqual(self.t.state.finds, [])

    def test_match_flow_and_pace(self):
        self.assertTrue(self.t.match_start(now=1000))
        for _ in range(12):
            self.t.chest()
        self.assertTrue(self.t.match_end(now=1000 + 600))
        self.assertEqual(self.t.state.matches, 1)
        self.assertEqual(self.t.summary().pace, 12)
        self.assertFalse(self.t.match_end(now=1700))   # ingen kamp kører

    def test_duplicate_start_ignored(self):
        self.t.match_start(now=1000)
        self.t.chest()
        self.assertFalse(self.t.match_start(now=1000 + DUPLICATE_START_WINDOW - 1))
        self.assertEqual(self.t.state.match_chests, 1)

    def test_missed_end_is_closed_by_next_start(self):
        self.t.match_start(now=1000)
        self.t.chest()
        self.assertTrue(self.t.match_start(now=2000))
        self.assertEqual(self.t.state.matches, 1)
        self.assertEqual(self.t.state.match_chests, 0)

    def test_short_empty_match_not_counted(self):
        self.t.match_start(now=1000)
        self.t.match_end(now=1005)
        self.assertEqual(self.t.state.matches, 0)

    def test_history_csv_one_header_no_stray_bom(self):
        for i in range(3):
            self.t.match_start(now=1000 + i * 1000)
            self.t.chest()
            self.t.match_end(now=1000 + i * 1000 + 300)
        raw = (self.dir / "historik.csv").read_bytes()
        self.assertEqual(raw.count(b"\xef\xbb\xbf"), 1)          # kun én BOM, i starten
        rows = list(csv.reader(raw.decode("utf-8-sig").splitlines(), delimiter=";"))
        self.assertEqual(rows[0], ["start", "slut", "sekunder", "kister"])
        self.assertEqual(len(rows), 4)

    def test_persistence_roundtrip(self):
        for _ in range(7):
            self.t.chest()
        self.t.save()
        t2 = Tracker(self.dir, 137500)
        t2.load()
        self.assertEqual(t2.state.total_chests, 7)

    def test_corrupt_state_is_backed_up(self):
        (self.dir / "state.json").write_text("{ikke json", encoding="utf-8")
        t2 = Tracker(self.dir, 137500)
        t2.load()
        self.assertEqual(t2.state.total_chests, 0)
        self.assertTrue(t2.warnings)
        self.assertTrue(list(self.dir.glob("state.corrupt-*.json")))

    def test_unknown_keys_in_state_ignored(self):
        (self.dir / "state.json").write_text(json.dumps({"total_chests": 3, "fremtidig": 1}), encoding="utf-8")
        t2 = Tracker(self.dir, 137500)
        t2.load()
        self.assertEqual(t2.state.total_chests, 3)

    def test_boost(self):
        self.t.set_rate(137500, 2.0)
        self.assertAlmostEqual(self.t.p, 2 / 137500)
        with self.assertRaises(ValueError):
            self.t.set_rate(0)

    def test_save_retries_when_file_is_briefly_locked(self):
        import os
        import tracker as tr
        real, calls = os.replace, []
        def flaky(a, b):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError("låst af OneDrive")
            return real(a, b)
        tr.os.replace = flaky
        try:
            self.t.chest()
            self.t.save()
        finally:
            tr.os.replace = real
        self.assertEqual(len(calls), 3)
        self.assertEqual(json.loads((self.dir / "state.json").read_text(encoding="utf-8"))["total_chests"], 1)


if __name__ == "__main__":
    unittest.main()
