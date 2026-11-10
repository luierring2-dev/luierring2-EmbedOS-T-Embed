import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import convert_dump
import winapi


class HotkeyParseTest(unittest.TestCase):
    def test_simple_and_mods(self):
        self.assertEqual(winapi.parse_hotkey("F8"), (0, 0x77))
        self.assertEqual(winapi.parse_hotkey("ctrl+F8"), (winapi.MOD_CONTROL, 0x77))
        self.assertEqual(winapi.parse_hotkey("Ctrl + Shift + f9"),
                         (winapi.MOD_CONTROL | winapi.MOD_SHIFT, 0x78))
        self.assertEqual(winapi.parse_hotkey("alt+K"), (winapi.MOD_ALT, ord("K")))

    def test_numpad(self):
        self.assertEqual(winapi.parse_hotkey("NUM+"), (0, 0x6B))
        self.assertEqual(winapi.parse_hotkey("ctrl+num+"), (winapi.MOD_CONTROL, 0x6B))
        self.assertEqual(winapi.parse_hotkey("num5"), (0, 0x65))

    def test_rejects(self):
        for bad in ("", "F99", "hyper+F8", "F12"):
            with self.assertRaises(ValueError, msg=bad):
                winapi.parse_hotkey(bad)

    def test_hotkeys_noop_off_windows(self):
        if winapi.IS_WINDOWS:
            self.skipTest("kun uden for Windows")
        hk = winapi.Hotkeys({"chest": "F8"}, lambda n: None)
        hk.start_and_wait()
        self.assertTrue(hk.failed)
        hk.stop()


class ConfigTest(unittest.TestCase):
    def setUp(self):
        import hud
        self.hud = hud
        self.dir = Path(tempfile.mkdtemp())

    def test_shipped_config_loads(self):
        cfg = self.hud.load_config(self.hud.HERE / "config.json")
        self.assertEqual(cfg["hotkeys"]["chest"], "F8")
        self.assertEqual(cfg["patterns"]["CHEST"], [])

    def test_partial_config_gets_defaults(self):
        p = self.dir / "c.json"
        p.write_text(json.dumps({"hotkeys": {"chest": "F6"}, "opacity": 1.0}))
        cfg = self.hud.load_config(p)
        self.assertEqual(cfg["hotkeys"]["chest"], "F6")
        self.assertEqual(cfg["hotkeys"]["undo"], "F7")     # fra standard
        self.assertLess(cfg["opacity"], 1.0)                # 1.0 ville slå click-through fra

    def test_bad_json_names_the_line(self):
        p = self.dir / "c.json"
        p.write_text('{\n  "a": 1\n  "b": 2\n}')
        with self.assertRaisesRegex(ValueError, "linje 3"):
            self.hud.load_config(p)


class ConvertTest(unittest.TestCase):
    def test_flat_with_bounds_not_stretched(self):
        pts = convert_dump.extract_points([{"x": 0, "y": 0}, {"x": 50, "y": 50, "type": "rare"}])
        out, warnings = convert_dump.convert(pts, bounds=(-100, 100, -100, 100))
        self.assertEqual(warnings, [])
        self.assertEqual([(s["nx"], s["ny"]) for s in out["spawns"]], [(0.5, 0.5), (0.75, 0.75)])
        self.assertEqual(out["spawns"][1]["type"], "rare")
        self.assertFalse(out["example"])

    def test_without_bounds_warns(self):
        pts = convert_dump.extract_points([{"x": 0, "y": 0}, {"x": 50, "y": 50}])
        out, warnings = convert_dump.convert(pts)
        self.assertTrue(warnings)

    def test_swap_flip_and_grid(self):
        pts = [{"x": 90.0, "y": -90.0, "poi": "A", "type": "std"}]
        out, _ = convert_dump.convert(pts, bounds=(-100, 100, -100, 100), swap_xy=True, flip_y=True)
        s = out["spawns"][0]
        self.assertEqual((s["nx"], s["ny"]), (0.05, 0.05))
        self.assertEqual(s["grid"], "A1")

    def test_points_outside_bounds_skipped(self):
        pts = [{"x": 500.0, "y": 0.0, "poi": "A", "type": "std"}]
        out, warnings = convert_dump.convert(pts, bounds=(-100, 100, -100, 100))
        self.assertEqual(out["spawns"], [])
        self.assertTrue(any("uden for" in w for w in warnings))

    def test_fmodel_style_root_component(self):
        raw = [
            {"Type": "Tiered_Chest_Athena_C", "Name": "Tiered_Chest_Athena_C_1",
             "Properties": {"RootComponent": {"ObjectName": "SceneComponent'Tiered_Chest_Athena_C_1.Root'"}}},
            {"Type": "SceneComponent", "Name": "Root", "Outer": "Tiered_Chest_Athena_C_1",
             "Properties": {"RelativeLocation": {"X": 10.0, "Y": 20.0, "Z": 5.0}}},
            {"Type": "SceneComponent", "Name": "Root", "Outer": "SomeTree_2",
             "Properties": {"RelativeLocation": {"X": 999.0, "Y": 999.0, "Z": 5.0}}},
            {"Type": "Tiered_Chest_Athena_Rare_C", "Name": "Rare_1",
             "Properties": {"RelativeLocation": {"X": 1.0, "Y": 2.0, "Z": 0.0}}},
            {"Type": "Tree_C", "Name": "SomeTree_2", "Properties": {}},
        ]
        pts = convert_dump.extract_points(raw)
        self.assertEqual(sorted((p["x"], p["y"], p["type"]) for p in pts),
                         [(1.0, 2.0, "rare"), (10.0, 20.0, "std")])

    def test_cli(self):
        d = Path(tempfile.mkdtemp())
        (d / "dump.json").write_text(json.dumps({"spawns": [{"x": 1, "y": 1, "poi": "P"}]}))
        with contextlib.redirect_stdout(io.StringIO()):
            rc = convert_dump.main([str(d / "dump.json"), str(d / "spawns.json"), "--bounds", "0", "2", "0", "2"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads((d / "spawns.json").read_text())["spawns"][0]["grid"], "F6")


if __name__ == "__main__":
    unittest.main()
