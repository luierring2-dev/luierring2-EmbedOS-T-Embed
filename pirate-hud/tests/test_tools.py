import contextlib
import io
import json
import random
import re
import tempfile
import unittest
from pathlib import Path

import tools
from logtail import ChestCapture

CHEST_LINE = "[2026.11.10-15.{:02d}.{:02d}:000][{:3d}]LogFortContainer: Tiered_Chest_Athena_C_{} searched by player"


def noise(i):
    return random.choice([
        f"[2026.11.10-15.00.00:000][{i % 999:3d}]LogNet: tick {i}",
        f"[2026.11.10-15.00.00:000][{i % 999:3d}]LogRenderer: frame {i} took {i % 17}.2ms",
        f"[2026.11.10-15.00.00:000][{i % 999:3d}]LogAudio: voice {i % 40} stopped",
    ])


def simulate(folder: Path, presses: int, chest_logged: bool, seed=1):
    random.seed(seed)
    cap = ChestCapture(folder)
    t = 1000.0
    for p in range(presses):
        for j in range(200):                     # 20 s baggrundsstøj, 10 linjer/s
            t += 0.1
            cap.feed(t, noise(p * 1000 + j))
            cap.flush(t)
        if chest_logged:
            cap.feed(t, CHEST_LINE.format(p % 60, p % 60, p, p))
        t += 0.6                                 # spilleren trykker lidt efter
        cap.press(t)
        for j in range(40):
            t += 0.1
            cap.feed(t, noise(p * 1000 + 500 + j))
            cap.flush(t)
    cap.flush(t + 10)
    cap.save_baseline()
    return cap


class CaptureAnalyzeTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_finds_planted_chest_line_and_regex_matches(self):
        simulate(self.dir, 25, chest_logged=True)
        windows = tools.load_windows(self.dir / "tryk.jsonl")
        self.assertEqual(len(windows), 25)
        baseline = json.loads((self.dir / "baseline.json").read_text(encoding="utf-8"))["tæller"]
        cands = tools.analyze(windows, baseline)
        self.assertTrue(cands)
        best = cands[0]
        self.assertIn("Tiered_Chest_Athena_C_#", best["template"])
        self.assertEqual(best["share"], 1.0)
        rx = tools.suggest_regex(best["template"])
        self.assertTrue(re.search(rx, CHEST_LINE.format(1, 2, 3, 999), re.I))
        self.assertFalse(re.search(rx, noise(5), re.I))
        # Forslaget skal kunne sættes direkte ind i config.json
        self.assertEqual(json.loads(json.dumps(rx)), rx)

    def test_no_signal_gives_no_candidate(self):
        simulate(self.dir, 25, chest_logged=False)
        windows = tools.load_windows(self.dir / "tryk.jsonl")
        baseline = json.loads((self.dir / "baseline.json").read_text(encoding="utf-8"))["tæller"]
        self.assertEqual(tools.analyze(windows, baseline), [])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tools.cmd_kister(self.dir), 0)
        self.assertIn("sandsynligvis ikke", (self.dir / "forslag.txt").read_text(encoding="utf-8"))

    def test_undo_removes_last_window(self):
        cap = ChestCapture(self.dir)
        cap.feed(1.0, "a")
        cap.press(1.0)
        cap.flush(10)
        cap.press(11.0)
        cap.flush(20)
        cap.undo()                     # efter flush -> skrives som 'fortryd'
        cap.press(21.0)
        cap.undo()                     # før flush -> fjernes bare
        cap.flush(30)
        self.assertEqual(len(tools.load_windows(self.dir / "tryk.jsonl")), 1)

    def test_baseline_survives_restart(self):
        cap = ChestCapture(self.dir)
        cap.feed(1.0, "LogX: hello 1")
        cap.save_baseline()
        cap2 = ChestCapture(self.dir)
        cap2.feed(2.0, "LogX: hello 2")
        cap2.save_baseline()
        data = json.loads((self.dir / "baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(data["tæller"]["LogX: hello #"], 2)

    def test_disabled_capture_writes_nothing(self):
        cap = ChestCapture(self.dir, enabled=False)
        cap.feed(1.0, "x")
        cap.press(1.0)
        cap.flush(100)
        cap.save_baseline()
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_cmd_kister_needs_enough_presses(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tools.cmd_kister(self.dir), 1)


class TjekTest(unittest.TestCase):
    def test_reports_hits_and_misses(self):
        d = Path(tempfile.mkdtemp())
        (d / "FortniteGame.log").write_text(
            "[2026.11.10-15.00.00:000][  1]LogGameState: Match State Changed from WaitingToStart to InProgress\n"
            "[2026.11.10-15.20.00:000][  2]LogLoad: LoadMap: /Game/Maps/Frontend\n", encoding="utf-8")
        cfg = d / "config.json"
        cfg.write_text(json.dumps({"patterns": {
            "MATCH_START": ["to InProgress"], "LOBBY": ["Frontend"], "MATCH_END": ["WaitingPostMatch"]}}))
        out = d / "tjek.txt"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tools.cmd_tjek(d, cfg, out), 0)
        report = out.read_text(encoding="utf-8")
        self.assertRegex(report, r"MATCH_START\s+1\s+OK")
        self.assertRegex(report, r"MATCH_END\s+0\s+RAMMER IKKE")

    def test_no_logs(self):
        d = Path(tempfile.mkdtemp())
        cfg = d / "config.json"
        cfg.write_text("{}")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tools.cmd_tjek(d, cfg, d / "out.txt"), 1)


if __name__ == "__main__":
    unittest.main()
