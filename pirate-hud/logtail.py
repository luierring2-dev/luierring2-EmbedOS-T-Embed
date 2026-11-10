"""Læser Fortnites log-fil mens spillet kører.

Kun læsning af en tekstfil som spillet selv skriver. Ingen hukommelseslæsning,
ingen kontakt med spillets proces.

Forskelle fra den gamle logwatch.py:
- læser bytes og samler halve linjer, så en linje der skrives midt i en læsning
  ikke bliver delt i to (og mønstret misser den)
- kender forskel på "filen voksede", "filen blev nulstillet" og "Fortnite startede
  forfra med en ny log" (filens identitet, ikke kun størrelse)
- venter på at filen dukker op, hvis HUD'en startes før Fortnite
- holder ikke filen åben, så Fortnite kan omdøbe den ved næste opstart
- forstår UTF-8 (med/uden BOM) og UTF-16
"""
from __future__ import annotations

import codecs
import json
import os
import re
import time
from collections import Counter, deque
from pathlib import Path


def default_log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "FortniteGame" / "Saved" / "Logs"


def default_log_path() -> Path:
    return default_log_dir() / "FortniteGame.log"


# --------------------------------------------------------------------------- tail

class LogTail:
    MAX_READ = 2 << 20        # højst 2 MB pr. kald, så UI'et ikke fryser
    MAX_PARTIAL = 64 << 10    # en "linje" uden linjeskift længere end dette smides ud

    def __init__(self, path: Path | str, from_end: bool = True):
        self.path = Path(path)
        self.from_end = from_end
        self.exists = False
        self.rotations = 0
        self._started = False
        self._ident = None
        self._pos = 0
        self._decoder = None
        self._partial = ""

    def poll(self) -> list[str]:
        """Returnér nye, hele linjer siden sidste kald."""
        first_call = not self._started
        self._started = True
        try:
            st = os.stat(self.path)
        except OSError:
            self.exists = False
            return []
        self.exists = True

        ident = _identity(st)
        if ident != self._ident:
            if self._ident is not None:
                self.rotations += 1
            # Første gang: spring gammel historik over. Ny fil (Fortnite genstartet): læs alt.
            start = st.st_size if (first_call and self.from_end) else 0
            self._ident = ident
            self._set_position(start)
        elif st.st_size < self._pos:
            self._set_position(0)           # filen blev tømt

        if st.st_size <= self._pos:
            return []

        try:
            with open(self.path, "rb") as f:
                if self._decoder is None:
                    self._decoder = _make_decoder(f.read(4), at_start=self._pos == 0)
                f.seek(self._pos)
                data = f.read(min(st.st_size - self._pos, self.MAX_READ))
        except OSError:
            return []
        self._pos += len(data)

        text = self._partial + self._decoder.decode(data)
        parts = text.split("\n")
        self._partial = parts.pop()
        if len(self._partial) > self.MAX_PARTIAL:
            self._partial = ""
        return [p.rstrip("\r") for p in parts if p.strip()]

    def _set_position(self, pos: int) -> None:
        self._pos = pos
        self._decoder = None
        self._partial = ""


def _identity(st: os.stat_result):
    # Windows: st_ino er filens indeks og ændres når Fortnite laver en ny log.
    birth = getattr(st, "st_birthtime", None)
    if birth is None and os.name == "nt":
        birth = st.st_ctime            # på Windows er ctime = oprettelsestid
    return (st.st_dev, st.st_ino, birth)


def _make_decoder(head: bytes, at_start: bool):
    if head.startswith(codecs.BOM_UTF16_LE) or (len(head) >= 4 and head[1] == 0 and head[3] == 0):
        enc = "utf-16" if at_start and head.startswith(codecs.BOM_UTF16_LE) else "utf-16-le"
    elif head.startswith(codecs.BOM_UTF16_BE):
        enc = "utf-16" if at_start else "utf-16-be"
    else:
        enc = "utf-8-sig" if at_start else "utf-8"
    return codecs.getincrementaldecoder(enc)(errors="replace")


# --------------------------------------------------------------------------- mønstre

class Matcher:
    """Mønstre fra config.json: {"EVENT": ["regex", "regex"], "_note": "..."}"""

    def __init__(self, patterns: dict):
        self.rules: list[tuple[str, re.Pattern]] = []
        self.errors: list[str] = []
        for event, rxs in (patterns or {}).items():
            if event.startswith("_"):
                continue
            if isinstance(rxs, str):
                rxs = [rxs]
            for rx in rxs or []:
                if not rx:
                    continue
                try:
                    self.rules.append((event, re.compile(rx, re.IGNORECASE)))
                except re.error as e:
                    self.errors.append(f"{event}: {rx!r} er ugyldig regex ({e})")

    def events(self) -> set[str]:
        return {ev for ev, _ in self.rules}

    def match(self, line: str) -> str | None:
        for event, rx in self.rules:
            if rx.search(line):
                return event
        return None


# --------------------------------------------------------------------------- kalibrering

_TIMESTAMP = re.compile(r"^\[\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{3}\]\[\s*\d+\]")
_HEX = re.compile(r"\b(?:0x)?[0-9A-Fa-f]{8,}\b")
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_SPACE = re.compile(r"\s+")


def template(line: str) -> str:
    """Fjern tidsstempel og tal, så ens linjer kan tælles sammen.

    '[2026.11.10-15.14.33:123][ 45]LogX: Chest_C_12 opened at 1.5' -> 'LogX: Chest_C_# opened at #'
    """
    s = _TIMESTAMP.sub("", line)
    s = _HEX.sub("#", s)
    s = _NUM.sub("#", s)
    return _SPACE.sub(" ", s).strip()[:240]


class ChestCapture:
    """Gemmer loglinjerne omkring hvert kiste-tryk (F8).

    Efter et par kampe kan analyser-kister.bat se, om der findes en linje som
    Fortnite skriver hver gang du åbner en kiste. Findes den, kan tælleren blive
    automatisk. Findes den ikke, ved du det – i stedet for at gætte.
    """
    MAX_KEYS = 60_000

    def __init__(self, folder: Path, before: float = 5.0, after: float = 3.0, enabled: bool = True):
        self.folder = Path(folder)
        self.before = before
        self.after = after
        self.enabled = enabled
        self.recent: deque[tuple[float, str]] = deque()
        self.pending: list[float] = []
        self.windows_written = 0
        self.baseline: Counter = Counter()
        self.lines_seen = 0
        self._dirty = False
        self._load_baseline()

    @property
    def windows_path(self) -> Path:
        return self.folder / "tryk.jsonl"

    @property
    def baseline_path(self) -> Path:
        return self.folder / "baseline.json"

    def feed(self, t: float, line: str) -> None:
        if not self.enabled:
            return
        self.recent.append((t, line))
        keep_from = t - (self.before + self.after + 2)
        while self.recent and self.recent[0][0] < keep_from:
            self.recent.popleft()
        key = template(line)
        if key in self.baseline or len(self.baseline) < self.MAX_KEYS:
            self.baseline[key] += 1
        self.lines_seen += 1
        self._dirty = True

    def press(self, t: float) -> None:
        if self.enabled:
            self.pending.append(t)

    def undo(self) -> None:
        """F7 lige efter F8: tag trykket ud af kalibreringen igen."""
        if not self.enabled:
            return
        if self.pending:
            self.pending.pop()
        else:
            self._write({"fortryd": True})

    def flush(self, now: float) -> None:
        if not self.enabled:
            return
        ready = [t for t in self.pending if now >= t + self.after]
        self.pending = [t for t in self.pending if now < t + self.after]
        for t in ready:
            lines = [l for (lt, l) in self.recent if t - self.before <= lt <= t + self.after]
            self._write({"t": round(t, 2), "linjer": lines})
            self.windows_written += 1

    def save_baseline(self) -> None:
        if not (self.enabled and self._dirty):
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.baseline_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"linjer": sum(self.baseline.values()),
                                   "tæller": dict(self.baseline.most_common())},
                                  ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.baseline_path)
        self._dirty = False

    def _load_baseline(self) -> None:
        try:
            raw = json.loads(self.baseline_path.read_text(encoding="utf-8"))
            self.baseline.update(raw.get("tæller", {}))
        except (OSError, ValueError, AttributeError):
            pass

    def _write(self, obj: dict) -> None:
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            with self.windows_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        except OSError:
            pass
