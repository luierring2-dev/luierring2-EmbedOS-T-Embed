"""Tælleren: kister, kampe, fund og sandsynlighed.

Ingen Tk og ingen Windows-kald her, så alt kan testes på enhver maskine.
Tilstanden gemmes i data/state.json efter hver ændring, så tallet overlever
genstart af HUD'en, af pc'en og af Fortnite.
"""
from __future__ import annotations

import csv
import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

MIN_MATCH_SECONDS = 30      # kortere "kampe" er falske skift i loggen
DUPLICATE_START_WINDOW = 30  # en ny MATCH_START inden for 30 s er en dublet


# --------------------------------------------------------------------------- matematik

def p_at_least_one(n: int, p: float) -> float:
    """Chancen for mindst ét fund i n uafhængige kister med chance p hver."""
    if n <= 0 or p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    # 1 - (1-p)^n, regnet uden at miste præcision ved små p
    return -math.expm1(n * math.log1p(-p))


def chests_for(q: float, p: float) -> int | float:
    """Hvor mange kister der skal til for q chance (fx 0.5) for mindst ét fund."""
    if p <= 0:
        return math.inf
    if p >= 1:
        return 1
    return math.ceil(math.log1p(-q) / math.log1p(-p))


# --------------------------------------------------------------------------- dansk talformat

def fmt_int(n: float) -> str:
    """1234567 -> '1.234.567'"""
    if n == math.inf:
        return "∞"
    return f"{int(round(n)):,}".replace(",", ".")


def fmt_pct(fraction: float) -> str:
    """0.0089 -> '0,89 %', 7.27e-6 -> '0,00073 %' (altid ~2 betydende cifre)."""
    pc = fraction * 100
    if pc <= 0:
        return "0 %"
    if pc >= 99.95:
        return "100 %" if fraction >= 1 else "99,9 %"
    if pc >= 10:
        decimals = 1
    else:
        decimals = min(8, max(2, 1 - math.floor(math.log10(pc))))
    return f"{pc:.{decimals}f}".replace(".", ",") + " %"


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


# --------------------------------------------------------------------------- tilstand

@dataclass
class State:
    total_chests: int = 0
    since_find: int = 0
    finds: list = field(default_factory=list)
    matches: int = 0              # afsluttede kampe
    match_chests_sum: int = 0     # kister i afsluttede kampe (til tempo)
    in_match: bool = False
    match_start: float = 0.0
    match_chests: int = 0         # kister i den kamp der kører (eller siden F10)
    last_match_chests: int | None = None


@dataclass
class Summary:
    p: float
    since_find: int
    total_chests: int
    match_chests: int
    finds: int
    chance_so_far: float
    n50: int | float
    n90: int | float
    pace: float | None            # kister pr. kamp
    matches_to_50: float | None   # kampe til 50 %-punktet med dit tempo


class Tracker:
    def __init__(self, data_dir: Path, odds: float = 137500, boost: float = 1.0):
        self.data_dir = Path(data_dir)
        self.state_path = self.data_dir / "state.json"
        self.history_path = self.data_dir / "historik.csv"
        self.finds_path = self.data_dir / "fund.csv"
        self.set_rate(odds, boost)
        self.state = State()
        self.warnings: list[str] = []
        self._undo: list[tuple] = []

    # ---------------------------------------------------------- rate
    def set_rate(self, odds: float, boost: float = 1.0) -> None:
        odds = float(odds)
        boost = float(boost)
        if odds < 1 or boost <= 0:
            raise ValueError("odds_per_chest skal være >= 1 og boost > 0")
        self.odds = odds
        self.boost = boost
        self.p = min(1.0, boost / odds)

    # ---------------------------------------------------------- handlinger
    def chest(self, now: float | None = None) -> None:
        s = self.state
        s.total_chests += 1
        s.since_find += 1
        s.match_chests += 1
        self._push(("chest",))

    def undo(self) -> str | None:
        """Fortryd sidste tryk (kiste eller fund). Returnerer hvad der blev fortrudt."""
        if not self._undo:
            return None
        action = self._undo.pop()
        s = self.state
        if action[0] == "chest":
            s.total_chests = max(0, s.total_chests - 1)
            s.since_find = max(0, s.since_find - 1)
            s.match_chests = max(0, s.match_chests - 1)
            return "kiste"
        if action[0] == "found":
            _, before = action
            s.since_find = before
            if s.finds:
                s.finds.pop()
            return "fund"
        return None

    def found(self, now: float | None = None) -> int:
        """Registrér et fund. Returnerer hvor mange kister det tog."""
        now = time.time() if now is None else now
        s = self.state
        took = s.since_find
        s.finds.append({"tid": _iso(now), "kister": took})
        self._push(("found", took))
        s.since_find = 0
        self._append_csv(self.finds_path, ["tid", "kister_siden_sidste_fund", "kister_i_alt"],
                         [_iso(now), took, s.total_chests])
        return took

    def match_start(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        s = self.state
        if s.in_match and now - s.match_start < DUPLICATE_START_WINDOW:
            return False                   # dublet-linje i loggen
        if s.in_match:
            self.match_end(now)            # vi missede slutningen på forrige kamp
        s.in_match = True
        s.match_start = now
        s.match_chests = 0
        return True

    def match_end(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        s = self.state
        if not s.in_match:
            return False
        duration = now - s.match_start
        s.in_match = False
        s.last_match_chests = s.match_chests
        if duration >= MIN_MATCH_SECONDS or s.match_chests > 0:
            s.matches += 1
            s.match_chests_sum += s.match_chests
            self._append_csv(self.history_path, ["start", "slut", "sekunder", "kister"],
                             [_iso(s.match_start), _iso(now), int(duration), s.match_chests])
        s.match_chests = 0
        return True

    def new_match_manual(self, now: float | None = None) -> None:
        """F10: afslut evt. kørende kamp og start en ny – til når loggen ikke fanger det."""
        now = time.time() if now is None else now
        if self.state.in_match:
            self.match_end(now)
        else:
            self.state.match_chests = 0
        self.state.in_match = True
        self.state.match_start = now

    # ---------------------------------------------------------- visning
    def summary(self) -> Summary:
        s = self.state
        n50 = chests_for(0.5, self.p)
        pace = (s.match_chests_sum / s.matches) if s.matches and s.match_chests_sum else None
        to50 = None
        if pace and n50 != math.inf:
            to50 = max(0.0, (n50 - s.since_find) / pace)
        return Summary(
            p=self.p, since_find=s.since_find, total_chests=s.total_chests,
            match_chests=s.match_chests, finds=len(s.finds),
            chance_so_far=p_at_least_one(s.since_find, self.p),
            n50=n50, n90=chests_for(0.9, self.p), pace=pace, matches_to_50=to50,
        )

    # ---------------------------------------------------------- lagring
    def load(self) -> None:
        if not self.state_path.exists():
            return
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            known = {k: v for k, v in raw.items() if k in State.__dataclass_fields__}
            self.state = State(**known)
        except (OSError, ValueError, TypeError) as e:
            backup = self.state_path.with_name(f"state.corrupt-{int(time.time())}.json")
            try:
                self.state_path.replace(backup)
            except OSError:
                pass
            self.warnings.append(f"state.json var ødelagt ({e}); gemt som {backup.name}")
            self.state = State()
        # En kamp der "kører" fra en gammel session er ikke reel
        if self.state.in_match and time.time() - self.state.match_start > 3600:
            self.state.in_match = False

    def save(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self.state), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.state_path)   # atomisk: ingen halve filer ved strømsvigt

    # ---------------------------------------------------------- intern
    def _push(self, action: tuple) -> None:
        self._undo.append(action)
        del self._undo[:-50]

    def _append_csv(self, path: Path, header: list, row: list) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            new = not path.exists()
            with path.open("a", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")   # semikolon = dansk Excel åbner den rigtigt
                if new:
                    w.writerow(header)
                w.writerow(row)
        except OSError as e:
            self.warnings.append(f"kunne ikke skrive {path.name}: {e}")


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t).isoformat(timespec="seconds")
