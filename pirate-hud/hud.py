#!/usr/bin/env python3
"""Pirate Token HUD – click-through overlay til Fortnite.

Start med start.bat (eller: py hud.py). Kun Python 3.10+, intet at installere.

    py hud.py                 normal start
    py hud.py --demo          vis HUD'en med eksempeltal (rører ikke dine data)
    py hud.py --log STI       læs en anden log-fil (til test)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import queue
import signal
import sys
import tempfile
import time
import tkinter as tk
import traceback
from pathlib import Path

import winapi
from logtail import ChestCapture, LogTail, Matcher, default_log_path
from tracker import Tracker, fmt_duration, fmt_int, fmt_pct

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
CALIB = HERE / "kalibrering"

DEFAULTS = {
    "odds_per_chest": 137500,
    "boost": 1.0,
    "corner": "tl",
    "offset_x": 0,
    "offset_y": 0,
    "scale": 1.0,
    "opacity": 0.9,
    "hide_when_not_fortnite": True,
    "show_map": True,
    "map_image": "",
    "spawns_file": "spawns.json",
    "route": [],
    "log_file": "",
    "capture_chest_windows": True,
    "hotkeys": {"chest": "F8", "undo": "F7", "found": "ctrl+F8",
                "toggle": "F9", "corner": "ctrl+F9", "new_match": "F10"},
    "patterns": {},
}

# tl/tr = øverst, ml/mr = midt på, bl/br = nederst. Ctrl+F9 går rundt i denne rækkefølge.
CORNERS = ["tl", "ml", "bl", "br", "mr", "tr"]
BG, PANEL, BORDER = "#000000", "#0d0f14", "#262a33"
ACC, FG, MUT, GOOD, WARN, BLUE, DIM = "#ffcc4d", "#f2f2f2", "#8a919c", "#5dd39e", "#ff8a5c", "#5b9dff", "#3a3f4a"
UI_FONT = "Segoe UI" if os.name == "nt" else "DejaVu Sans"


# --------------------------------------------------------------------------- config

def load_config(path: Path) -> dict:
    """Læs config.json oven på standardværdierne. Rejser ValueError med en dansk forklaring."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise ValueError(f"{path.name} mangler")
    except json.JSONDecodeError as e:
        raise ValueError(f"{path.name} linje {e.lineno}: {e.msg} (mangler der et komma eller \"?)")
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name} skal være et {{...}}-objekt")
    cfg = json.loads(json.dumps(DEFAULTS))
    for key, value in raw.items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            cfg[key].update(value)
        else:
            cfg[key] = value
    cfg["opacity"] = min(0.98, max(0.2, float(cfg["opacity"])))  # 1.0 slår click-through fra i Tk
    cfg["scale"] = min(3.0, max(0.5, float(cfg["scale"])))
    if cfg["corner"] not in CORNERS:
        cfg["corner"] = "tl"
    cfg["offset_x"], cfg["offset_y"] = int(cfg["offset_x"]), int(cfg["offset_y"])
    return cfg


def load_spawns(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        data.setdefault("spawns", [])
        return data
    except (OSError, ValueError):
        return {"spawns": [], "missing": True}


# --------------------------------------------------------------------------- visning

class HudView:
    W = 272    # bredde ved 100 % skalering
    MAP = 176  # kortets side ved 100 % skalering

    def __init__(self, root: tk.Tk, cfg: dict):
        self.root = root
        self.k = root.winfo_fpixels("1i") / 96 * cfg["scale"]
        self.fs = cfg["scale"]
        self.width = int(self.W * self.k)
        root.configure(bg=BG)

        outer = tk.Frame(root, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        outer.pack(fill="both", expand=True)
        self.body = body = tk.Frame(outer, bg=PANEL)
        body.pack(fill="both", expand=True, padx=self.px(10), pady=self.px(8))

        head = tk.Frame(body, bg=PANEL)
        head.pack(fill="x")
        tk.Label(head, text="PIRATE TOKEN", bg=PANEL, fg=MUT, font=self.font(7, "bold")).pack(side="left")
        self.dot = tk.Label(head, text="●", bg=PANEL, fg=DIM, font=self.font(8))
        self.dot.pack(side="right")

        row = tk.Frame(body, bg=PANEL)
        row.pack(fill="x")
        self.count = tk.Label(row, text="0", bg=PANEL, fg=ACC, font=self.font(24, "bold"))
        self.count.pack(side="left")
        tk.Label(row, text=" kister\n siden fund", bg=PANEL, fg=MUT, justify="left",
                 font=self.font(7)).pack(side="left", anchor="s", pady=(0, self.px(7)))

        row2 = tk.Frame(body, bg=PANEL)
        row2.pack(fill="x")
        self.chance = tk.Label(row2, text="0 %", bg=PANEL, fg=FG, font=self.font(11, "bold"))
        self.chance.pack(side="left")
        tk.Label(row2, text="  chance for mindst ét fund", bg=PANEL, fg=MUT,
                 font=self.font(7)).pack(side="left", anchor="s", pady=(0, self.px(2)))

        self.bar = tk.Canvas(body, height=self.px(6), bg=DIM, highlightthickness=0, width=self.width - self.px(22))
        self.bar.pack(fill="x", pady=(self.px(4), self.px(2)))
        self.bar_fill = self.bar.create_rectangle(0, 0, 0, self.px(6), fill=ACC, width=0)

        self.milestones = self.small(body)
        self.rate = self.small(body)
        self.counts = self.small(body)
        self.pace = self.small(body)

        self.map_frame = tk.Frame(body, bg=PANEL)
        self.map = tk.Canvas(self.map_frame, bg="#080a0e", highlightthickness=1,
                             highlightbackground=BORDER, width=self.px(self.MAP), height=self.px(self.MAP))
        self.map.pack(pady=(self.px(6), 0))   # centreret
        self._map_img = None

        self.route = tk.Label(body, text="", bg=PANEL, fg=FG, font=self.font(8), justify="left",
                              anchor="w", wraplength=self.width - self.px(22))
        self.route.pack(fill="x", pady=(self.px(6), 0))
        self.status = tk.Label(body, text="", bg=PANEL, fg=MUT, font=self.font(8), justify="left",
                               anchor="w", wraplength=self.width - self.px(22))
        self.status.pack(fill="x", pady=(self.px(4), 0))
        self.hint = tk.Label(body, text="", bg=PANEL, fg=DIM, font=self.font(7), justify="left",
                             anchor="w", wraplength=self.width - self.px(22))
        self.hint.pack(fill="x")
        self._flash_job = None

    def px(self, n: float) -> int:
        return max(1, int(round(n * self.k)))

    def font(self, size: float, weight: str = "normal"):
        return (UI_FONT, max(6, int(round(size * self.fs))), weight)

    def small(self, parent) -> tk.Label:
        lbl = tk.Label(parent, text="", bg=PANEL, fg=MUT, font=self.font(8), anchor="w", justify="left")
        lbl.pack(fill="x")
        return lbl

    # ---------------------------------------------------------- opdatering
    def render(self, s, status: str, status_color: str, dot_color: str, route: list, hint: str) -> None:
        self.count.config(text=fmt_int(s.since_find))
        self.chance.config(text=fmt_pct(s.chance_so_far))
        frac = 0.0 if s.n50 == math.inf else min(1.0, s.since_find / s.n50)
        w = self.bar.winfo_width() or (self.width - self.px(22))
        self.bar.coords(self.bar_fill, 0, 0, w * frac, self.px(6))
        self.milestones.config(text=f"50 % ved {fmt_int(s.n50)} · 90 % ved {fmt_int(s.n90)} kister")
        self.rate.config(text=f"hver kiste: 1:{fmt_int(1 / s.p)} ({fmt_pct(s.p)}) – altid")
        self.counts.config(text=f"denne kamp {fmt_int(s.match_chests)} · i alt {fmt_int(s.total_chests)}"
                                f" · fund {s.finds}")
        if s.pace:
            self.pace.config(text=f"tempo {s.pace:.1f}/kamp".replace(".", ",")
                                  + f" → ~{fmt_int(s.matches_to_50)} kampe til 50 %")
        else:
            self.pace.config(text="tempo: kendes når en kamp er spillet færdig")
        self.route.config(text=("Rute: " + " → ".join(route)) if route else "")
        self.status.config(text=status, fg=status_color)
        self.dot.config(fg=dot_color)
        self.hint.config(text=hint)

    def flash(self, color: str = GOOD) -> None:
        self.count.config(fg=color)
        if self._flash_job:
            self.root.after_cancel(self._flash_job)
        self._flash_job = self.root.after(350, lambda: self.count.config(fg=ACC))

    def draw_map(self, spawns: dict, route: list, image_path: str, show: bool) -> None:
        if not show:
            self.map_frame.pack_forget()
            return
        self.map_frame.pack(fill="x", before=self.route)
        c = self.map
        c.delete("all")
        size = int(c["width"])
        self._map_img = None
        if image_path:
            p = Path(image_path)
            p = p if p.is_absolute() else HERE / p
            try:
                img = tk.PhotoImage(file=str(p))          # PNG/GIF
                factor = max(1, math.ceil(max(img.width(), img.height()) / size))
                self._map_img = img.subsample(factor, factor)
                c.create_image(size // 2, size // 2, image=self._map_img)
            except tk.TclError:
                c.create_text(size // 2, self.px(10), text=f"kan ikke læse {p.name}", fill=WARN,
                              font=self.font(7))
        grid = spawns.get("grid", {"cols": 10, "rows": 10})
        cols, rows = int(grid.get("cols", 10)), int(grid.get("rows", 10))
        for i in range(1, cols):
            c.create_line(size * i / cols, 0, size * i / cols, size, fill="#1a1d24")
        for i in range(1, rows):
            c.create_line(0, size * i / rows, size, size * i / rows, fill="#1a1d24")
        for i in range(cols):
            c.create_text(size * (i + 0.5) / cols, self.px(6), text=chr(65 + i), fill=DIM, font=self.font(6))
        wanted = {r.lower() for r in route}
        for sp in spawns.get("spawns", []):
            try:
                x, y = float(sp["nx"]) * size, float(sp["ny"]) * size
            except (KeyError, TypeError, ValueError):
                continue
            kind = sp.get("type", "std")
            on_route = str(sp.get("poi", "")).lower() in wanted
            color = {"rare": ACC, "buried": BLUE}.get(kind, FG if on_route else "#5f6670")
            r = self.px(3.5 if on_route else 2.5)
            c.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="")
            if on_route and kind == "std":
                c.create_oval(x - r - 2, y - r - 2, x + r + 2, y + r + 2, outline=ACC)
        if spawns.get("missing"):
            c.create_text(size // 2, size // 2, text="spawns.json mangler", fill=MUT, font=self.font(8))
        elif spawns.get("example", False) or spawns.get("eksempel", False):
            c.create_text(size // 2, size - self.px(16), text="EKSEMPELDATA\nikke rigtige positioner",
                          fill=WARN, font=self.font(7, "bold"), justify="center")


# --------------------------------------------------------------------------- app

class App:
    def __init__(self, root: tk.Tk, cfg_path: Path, log_override: str | None = None,
                 demo: bool = False, use_hotkeys: bool = True):
        self.root = root
        self.cfg_path = cfg_path
        self.demo = demo
        self.events: queue.Queue = queue.Queue()
        self.messages: list[str] = []        # vedvarende advarsler
        self.toast = ("", 0.0, FG)           # kortvarig besked
        self.manual_hidden = False
        self.started = time.time()
        self.last_line_at = 0.0
        self.last_event = ""
        self.quit_requested = False
        self.closed = False
        self._last_baseline_save = time.time()

        try:
            self.cfg = load_config(cfg_path)
        except ValueError as e:
            self.cfg = json.loads(json.dumps(DEFAULTS))
            self.messages.append(f"config: {e} – bruger standardværdier")
        self._cfg_mtime = self._mtime(cfg_path)

        data_dir = DATA if not demo else Path(tempfile.mkdtemp(prefix="pirate-hud-demo-"))
        self.tracker = Tracker(data_dir, self.cfg["odds_per_chest"], self.cfg["boost"])
        if demo:
            self._fill_demo()
        else:
            self.tracker.load()
        self.matcher = Matcher(self.cfg["patterns"])
        log_path = Path(log_override or self.cfg.get("log_file") or default_log_path())
        self.tail = LogTail(log_path)
        self.capture = ChestCapture(CALIB, enabled=bool(self.cfg["capture_chest_windows"]) and not demo)
        self.ui_state = self._load_ui_state()
        self.corner = self.ui_state.get("corner", self.cfg["corner"])
        if self.corner not in CORNERS:
            self.corner = self.cfg["corner"]

        self.prev_foreground = winapi.foreground_window()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", self.cfg["opacity"])
        self.view = HudView(root, self.cfg)
        self.spawns = load_spawns(HERE / self.cfg["spawns_file"])
        self.view.draw_map(self.spawns, self.cfg["route"], self.cfg["map_image"], self.cfg["show_map"])

        self.hotkeys = winapi.Hotkeys(self.cfg["hotkeys"] if use_hotkeys else {}, self.events.put)
        if use_hotkeys:
            self.hotkeys.start_and_wait()

        root.update_idletasks()
        self.hwnd = None
        self._overlay()
        self.place()
        winapi.set_foreground(self.prev_foreground)   # giv fokus tilbage til spillet/konsollen

        self.refresh()
        self._every(40, self._tick_pump)
        self._every(250, self._tick_log)
        self._every(1000, self._tick_slow)

    # ---------------------------------------------------------- løkker
    def _every(self, ms: int, fn) -> None:
        """Kør fn hvert ms millisekund. En fejl må aldrig stoppe løkken (så fryser HUD'en)."""
        def run():
            if self.closed:
                return
            try:
                fn()
            except Exception:
                traceback.print_exc()
                self.say("intern fejl – se konsolvinduet", WARN, 10)
            if not self.closed:
                self.root.after(ms, run)
        self.root.after(ms, run)

    def _tick_pump(self) -> None:
        if self.quit_requested:
            self.shutdown()
            return
        changed = False
        while True:
            try:
                name = self.events.get_nowait()
            except queue.Empty:
                break
            self.on_hotkey(name)
            changed = True
        if changed:
            self.refresh()

    def _tick_log(self) -> None:
        if not self.demo:
            now = time.time()
            changed = False
            for line in self.tail.poll():
                self.last_line_at = now
                self.capture.feed(now, line)
                event = self.matcher.match(line)
                if event:
                    changed |= self.on_log_event(event, now)
            self.capture.flush(now)
            if changed:
                self.save()
                self.refresh()

    def _tick_slow(self) -> None:
        now = time.time()
        self._reload_config_if_changed()
        if now - self._last_baseline_save > 60:
            self._save_baseline()
        winapi.keep_on_top(self.hwnd)
        self.apply_visibility()
        self.refresh()

    # ---------------------------------------------------------- input
    def on_hotkey(self, name: str) -> None:
        now = time.time()
        t = self.tracker
        if name == "chest":
            t.chest(now)
            self.capture.press(now)
            self.view.flash()
        elif name == "undo":
            what = t.undo()
            if what == "kiste":
                self.capture.undo()
            self.say(f"fortrudt: {what}" if what else "intet at fortryde", MUT)
        elif name == "found":
            took = t.found(now)
            self.say(f"FUNDET efter {fmt_int(took)} kister! (F7 fortryder)", GOOD, 15)
            self.view.flash(GOOD)
        elif name == "toggle":
            self.manual_hidden = not self.manual_hidden
            self.apply_visibility()
        elif name == "corner":
            self.corner = CORNERS[(CORNERS.index(self.corner) + 1) % len(CORNERS)]
            self.ui_state["corner"] = self.corner
            self._save_ui_state()
            self.place()
        elif name == "new_match":
            t.new_match_manual(now)
            self.say("ny kamp startet manuelt", MUT)
        self.save()

    def on_log_event(self, event: str, now: float) -> bool:
        t = self.tracker
        self.last_event = event
        if event == "MATCH_START":
            return t.match_start(now)
        if event in ("MATCH_END", "LOBBY"):
            return t.match_end(now)
        if event == "CHEST":
            t.chest(now)
            self.view.flash(BLUE)
            return True
        return False

    def say(self, text: str, color: str = FG, seconds: float = 4) -> None:
        self.toast = (text, time.time() + seconds, color)
        self.refresh()

    # ---------------------------------------------------------- tegning
    def refresh(self) -> None:
        s = self.tracker.summary()
        now = time.time()
        warnings = self.messages + self.matcher.errors + self.tracker.warnings[-2:] + self.hotkeys.failed
        if self.toast[1] > now:
            status, color = self.toast[0], self.toast[2]
        elif warnings:
            status, color = "⚠ " + "\n⚠ ".join(warnings[-3:]), WARN
        elif self.demo:
            status, color = "demo – dine data røres ikke", MUT
        elif not self.tail.exists:
            status, color = "venter på Fortnite-loggen (start spillet)", MUT
        elif self.tracker.state.in_match:
            status, color = f"kamp {fmt_duration(now - self.tracker.state.match_start)}", FG
        elif "MATCH_START" not in self.matcher.events():
            status, color = "intet kamp-mønster – brug F10 ved ny kamp", MUT
        else:
            status, color = "lobby / venter på kamp", MUT
        if self.demo:
            dot = GOOD
        elif not self.tail.exists:
            dot = WARN
        else:
            dot = GOOD if now - self.last_line_at < 30 else DIM
        self.view.render(s, status, color, dot, self.cfg["route"], self._hint())

    def _hint(self) -> str:
        reg = self.hotkeys.registered or ({} if winapi.IS_WINDOWS else self.cfg["hotkeys"])
        labels = [("chest", "+1"), ("undo", "fortryd"), ("found", "fundet"), ("toggle", "skjul"),
                  ("new_match", "ny kamp")]
        return " · ".join(f"{reg[k]} {lbl}" for k, lbl in labels if reg.get(k))

    def place(self) -> None:
        self.root.update_idletasks()
        w, h = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        m = self.view.px(16)
        x = sw - w - m if self.corner.endswith("r") else m
        y = {"t": m, "m": (sh - h) // 2, "b": sh - h - m - self.view.px(40)}[self.corner[0]]
        x += self.view.px(self.cfg["offset_x"])
        y += self.view.px(self.cfg["offset_y"])
        self.root.geometry(f"+{x}+{y}")

    def apply_visibility(self) -> None:
        visible = not self.manual_hidden
        if visible and self.cfg["hide_when_not_fortnite"] and time.time() - self.started > 8:
            focus = winapi.fortnite_has_focus()
            visible = focus is not False
        alpha = self.cfg["opacity"] if visible else 0.0
        if abs(float(self.root.attributes("-alpha")) - alpha) > 0.01:
            self.root.attributes("-alpha", alpha)
            self._overlay()                      # Tk kan nulstille stilen når alpha ændres

    def _overlay(self) -> None:
        self.hwnd = winapi.toplevel_hwnd(self.root)
        winapi.make_overlay(self.hwnd)

    # ---------------------------------------------------------- config og lagring
    def _reload_config_if_changed(self) -> None:
        mtime = self._mtime(self.cfg_path)
        if mtime == self._cfg_mtime:
            return
        self._cfg_mtime = mtime
        try:
            new = load_config(self.cfg_path)
            self.tracker.set_rate(new["odds_per_chest"], new["boost"])
        except (ValueError, TypeError) as e:
            self.say(f"config.json ikke indlæst: {e}", WARN, 10)
            return
        old, self.cfg = self.cfg, new
        self.messages = [m for m in self.messages if not m.startswith("config:")]
        self.matcher = Matcher(new["patterns"])
        self.capture.enabled = bool(new["capture_chest_windows"]) and not self.demo
        self.root.attributes("-alpha", new["opacity"])
        self._overlay()
        if (new["corner"], new["offset_x"], new["offset_y"]) != (old["corner"], old["offset_x"], old["offset_y"]):
            self.corner = new["corner"] if new["corner"] != old["corner"] else self.corner
            self.ui_state["corner"] = self.corner
            self._save_ui_state()
        if any(new[k] != old[k] for k in ("route", "map_image", "show_map", "spawns_file")):
            self.spawns = load_spawns(HERE / new["spawns_file"])
            self.view.draw_map(self.spawns, new["route"], new["map_image"], new["show_map"])
        if new["hotkeys"] != old["hotkeys"]:
            self.say("config indlæst – nye taster virker efter genstart", MUT, 6)
        else:
            self.say("config.json indlæst", MUT, 3)
        self.place()

    def save(self) -> None:
        if self.demo:
            return
        try:
            self.tracker.save()
        except OSError as e:
            self.say(f"kunne ikke gemme: {e}", WARN, 10)

    def _save_baseline(self) -> None:
        self._last_baseline_save = time.time()
        try:
            self.capture.save_baseline()
        except OSError:
            pass

    def _load_ui_state(self) -> dict:
        try:
            return json.loads((DATA / "ui.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_ui_state(self) -> None:
        if self.demo:
            return
        try:
            DATA.mkdir(parents=True, exist_ok=True)
            (DATA / "ui.json").write_text(json.dumps(self.ui_state), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    def _fill_demo(self) -> None:
        st = self.tracker.state
        st.total_chests, st.since_find, st.match_chests = 2318, 2318, 14
        st.matches, st.match_chests_sum = 171, 2304
        st.in_match, st.match_start = True, time.time() - 312

    def shutdown(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.save()
        self.capture.flush(time.time() + 3600)
        self._save_baseline()
        self.hotkeys.stop()
        self.root.destroy()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pirate Token HUD")
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--log", help="læs denne log-fil i stedet for Fortnites")
    ap.add_argument("--demo", action="store_true", help="vis eksempeltal, gem intet")
    ap.add_argument("--no-hotkeys", action="store_true")
    args = ap.parse_args(argv)

    winapi.enable_dpi_awareness()
    root = tk.Tk()
    root.title("Pirate Token HUD")
    app = App(root, Path(args.config), args.log, args.demo, not args.no_hotkeys)

    def request_quit(*_):
        app.quit_requested = True
    signal.signal(signal.SIGINT, request_quit)
    print("HUD kører. Luk dette vindue eller tryk Ctrl+C for at stoppe.")
    if app.hotkeys.failed:
        print("Advarsel:", "; ".join(app.hotkeys.failed))
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
