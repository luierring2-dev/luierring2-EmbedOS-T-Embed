"""Starter den rigtige HUD (uden Windows-delene) mod en falsk log og trykker på 'tasterne'."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

try:
    import tkinter as tk
    HAVE_TK = bool(os.environ.get("DISPLAY")) or os.name == "nt"
except ImportError:
    HAVE_TK = False


@unittest.skipUnless(HAVE_TK, "kræver tkinter og en skærm (xvfb-run på Linux)")
class HudSmokeTest(unittest.TestCase):
    def setUp(self):
        import hud
        self.hud = hud
        self.dir = Path(tempfile.mkdtemp())
        self._old = (hud.DATA, hud.CALIB)
        hud.DATA, hud.CALIB = self.dir / "data", self.dir / "kalibrering"
        self.log = self.dir / "FortniteGame.log"
        self.log.write_text("gammel historik der skal springes over\n", encoding="utf-8")
        self.cfg = self.dir / "config.json"
        shipped = json.loads((hud.HERE / "config.json").read_text(encoding="utf-8"))
        shipped["hide_when_not_fortnite"] = False
        self.cfg.write_text(json.dumps(shipped), encoding="utf-8")
        self.root = tk.Tk()
        self.app = hud.App(self.root, self.cfg, str(self.log), use_hotkeys=False)

    def tearDown(self):
        self.hud.DATA, self.hud.CALIB = self._old
        try:
            self.app.shutdown()
        except tk.TclError:
            pass

    def pump(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.root.update()
            time.sleep(0.02)

    def write_log(self, line):
        with open(self.log, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def press(self, *names):
        for n in names:
            self.app.events.put(n)
        self.pump(0.2)

    def test_full_flow(self):
        app, st = self.app, self.app.tracker.state
        self.pump(0.4)
        self.assertTrue(app.tail.exists)
        self.assertFalse(st.in_match)

        self.write_log("[2026.11.10-15.00.00:000][  1]LogGameState: Match State Changed from WaitingToStart to InProgress")
        self.pump(0.5)
        self.assertTrue(st.in_match)
        self.assertTrue(app.view.status.cget("text").startswith("kamp "))

        self.press("chest", "chest", "chest")
        self.assertEqual(st.since_find, 3)
        self.assertEqual(app.view.count.cget("text"), "3")
        saved = json.loads((self.dir / "data" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["total_chests"], 3)

        self.press("undo")
        self.assertEqual(st.since_find, 2)
        self.press("found")
        self.assertEqual(st.since_find, 0)
        self.assertEqual(len(st.finds), 1)
        self.assertIn("FUNDET", app.view.status.cget("text"))

        # config ændres mens den kører
        cfg = json.loads(self.cfg.read_text(encoding="utf-8"))
        cfg["route"] = ["Loguetown"]
        cfg["boost"] = 2.0
        time.sleep(0.05)
        self.cfg.write_text(json.dumps(cfg), encoding="utf-8")
        self.pump(1.3)
        self.assertEqual(app.cfg["route"], ["Loguetown"])
        self.assertAlmostEqual(app.tracker.p, 2 / 137500)
        self.assertIn("Loguetown", app.view.route.cget("text"))

        # ødelagt config: den gamle beholdes
        self.cfg.write_text("{ ødelagt", encoding="utf-8")
        self.pump(1.3)
        self.assertEqual(app.cfg["route"], ["Loguetown"])
        self.assertIn("ikke indlæst", app.view.status.cget("text"))

        self.write_log("[2026.11.10-15.20.00:000][  2]LogLoad: LoadMap: /Game/Maps/Frontend")
        self.pump(0.5)
        self.assertFalse(st.in_match)
        self.assertTrue((self.dir / "data" / "historik.csv").exists())

        # kalibreringen fik et vindue pr. tilbageværende F8-tryk efter shutdown
        app.shutdown()
        lines = (self.dir / "kalibrering" / "tryk.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len([l for l in lines if '"linjer"' in l]), 2)
        self.assertTrue((self.dir / "kalibrering" / "baseline.json").exists())

    def test_count_survives_restart(self):
        self.press("chest", "chest")
        self.app.shutdown()
        self.root = tk.Tk()
        self.app = self.hud.App(self.root, self.cfg, str(self.log), use_hotkeys=False)
        self.assertEqual(self.app.tracker.state.since_find, 2)

    def test_corner_cycles_and_is_remembered(self):
        self.press("corner")
        self.assertEqual(self.app.corner, "ml")
        ui = json.loads((self.dir / "data" / "ui.json").read_text(encoding="utf-8"))
        self.assertEqual(ui["corner"], "ml")

    def test_exception_in_loop_does_not_freeze_hud(self):
        calls = []
        real_poll = self.app.tail.poll
        def boom():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("test")
            return real_poll()
        self.app.tail.poll = boom
        import contextlib, io
        with contextlib.redirect_stderr(io.StringIO()):
            self.pump(0.8)
        self.assertGreater(len(calls), 1)            # løkken kørte videre efter fejlen
        self.assertIn("intern fejl", self.app.view.status.cget("text"))

    def test_bad_corner_in_ui_json_is_ignored(self):
        self.app.shutdown()
        (self.dir / "data").mkdir(exist_ok=True)
        (self.dir / "data" / "ui.json").write_text('{"corner": "xx"}', encoding="utf-8")
        self.root = tk.Tk()
        self.app = self.hud.App(self.root, self.cfg, str(self.log), use_hotkeys=False)
        self.press("corner")
        self.assertIn(self.app.corner, self.hud.CORNERS)

    def test_hides_when_fortnite_not_focused_but_never_in_demo(self):
        import winapi
        real = winapi.fortnite_has_focus
        winapi.fortnite_has_focus = lambda: False
        try:
            self.app.cfg["hide_when_not_fortnite"] = True
            self.app.started -= 10                      # forbi de første 8 sekunder
            self.app.apply_visibility()
            self.assertEqual(float(self.root.attributes("-alpha")), 0.0)
            winapi.fortnite_has_focus = lambda: True
            self.app.apply_visibility()
            self.assertGreater(float(self.root.attributes("-alpha")), 0.5)

            winapi.fortnite_has_focus = lambda: False
            self.app.shutdown()
            self.root = tk.Tk()
            self.app = self.hud.App(self.root, self.cfg, str(self.log), demo=True, use_hotkeys=False)
            self.app.cfg["hide_when_not_fortnite"] = True
            self.app.started -= 10
            self.app.apply_visibility()
            self.assertGreater(float(self.root.attributes("-alpha")), 0.5)
        finally:
            winapi.fortnite_has_focus = real


if __name__ == "__main__":
    unittest.main()
