#!/usr/bin/env python3
"""Fejlfinding uden at gætte.

    py tools.py tjek      kør config.json's mønstre over ALLE gemte Fortnite-logs
                          (også gårsdagens) og vis hvad der rammer
    py tools.py kister    find ud af om Fortnite skriver en linje når du åbner en
                          kiste – ud fra de F8-tryk HUD'en har optaget
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from logtail import LogTail, Matcher, default_log_dir, template

HERE = Path(__file__).resolve().parent
CALIB = HERE / "kalibrering"

KEYWORDS = re.compile(
    r"match ?state|loadmap|frontend|gamephase|chest|container|search|loot|aircraft|"
    r"battlebus|elimin|victory|matchmaking|safezone|storm", re.IGNORECASE)


def read_all_lines(path: Path) -> list[str]:
    tail = LogTail(path, from_end=False)
    lines: list[str] = []
    while True:
        chunk = tail.poll()
        if not chunk:
            return lines
        lines.extend(chunk)


# --------------------------------------------------------------------------- tjek

def cmd_tjek(log_dir: Path, cfg_path: Path, out: Path) -> int:
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        print(f"Kan ikke læse {cfg_path.name}: {e}")
        return 2
    matcher = Matcher(cfg.get("patterns", {}))
    for err in matcher.errors:
        print("FEJL i mønster:", err)

    logs = sorted(log_dir.glob("FortniteGame*.log"), key=lambda p: p.stat().st_mtime)
    if not logs:
        print(f"Ingen logs i {log_dir}")
        print("Har du spillet Fortnite på denne pc? Ellers: py tools.py tjek --dir <mappe>")
        return 1

    report = [f"Mønstre fra {cfg_path.name}, kørt over {len(logs)} log-filer i {log_dir}", ""]
    totals: Counter = Counter()
    examples: dict[str, list[str]] = {}
    keyword_templates: Counter = Counter()
    keyword_example: dict[str, str] = {}

    for path in logs:
        lines = read_all_lines(path)
        per_file: Counter = Counter()
        for line in lines:
            ev = matcher.match(line)
            if ev:
                per_file[ev] += 1
                examples.setdefault(ev, [])
                if len(examples[ev]) < 3:
                    examples[ev].append(line)
            if KEYWORDS.search(line):
                tpl = template(line)
                keyword_templates[tpl] += 1
                keyword_example.setdefault(tpl, line)
        totals.update(per_file)
        hits = ", ".join(f"{ev} {n}" for ev, n in sorted(per_file.items())) or "ingen hits"
        report.append(f"{path.name}: {len(lines)} linjer · {hits}")

    report += ["", "Hits i alt pr. event:"]
    for ev in sorted(set(totals) | matcher.events()):
        n = totals.get(ev, 0)
        verdict = "OK" if n else "RAMMER IKKE – ret mønstret"
        report.append(f"  {ev:12} {n:6}  {verdict}")
        for ex in examples.get(ev, []):
            report.append(f"      eks: {ex[:160]}")
    if "CHEST" not in matcher.events():
        report.append("  CHEST        (intet mønster – brug F8 + 'tools.py kister' for at finde et)")

    summary_end = len(report)
    report += ["", "Linjer med relevante ord (til at bygge nye mønstre), flest først:"]
    for tpl, n in keyword_templates.most_common(40):
        report.append(f"  {n:6} × {keyword_example[tpl][:170]}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report[: summary_end + 12]))
    print(f"\nHele rapporten: {out}")
    return 0


# --------------------------------------------------------------------------- kister

def load_windows(path: Path) -> list[list[str]]:
    windows: list[list[str]] = []
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return windows
    for raw in raw_lines:
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        if obj.get("fortryd"):
            if windows:
                windows.pop()
        elif "linjer" in obj:
            windows.append(obj["linjer"])
    return windows


def suggest_regex(tpl: str) -> str:
    rx = re.escape(tpl[:120].strip())
    rx = rx.replace(r"\#", r"[0-9A-Fa-fx.,]+")
    return re.sub(r"(?:\\ | )+", r"\\s+", rx)


def analyze(windows: list[list[str]], baseline: dict[str, int]) -> list[dict]:
    """Ranger linje-typer efter hvor ofte de optræder lige omkring et tryk."""
    presses = len(windows)
    support: Counter = Counter()
    sample: dict[str, str] = {}
    for lines in windows:
        seen = set()
        for line in lines:
            tpl = template(line)
            if tpl and tpl not in seen:
                seen.add(tpl)
                sample.setdefault(tpl, line)
        support.update(seen)
    out = []
    for tpl, n in support.items():
        share = n / presses
        if share < 0.5:
            continue
        per_press = max(baseline.get(tpl, n), n) / presses   # hvor tit den findes i alt
        if per_press > 4:
            continue        # baggrundsstøj: skrives hele tiden, ikke kun ved kister
        out.append({"template": tpl, "share": share, "per_press": per_press, "example": sample[tpl],
                    "score": share - 0.05 * max(0.0, per_press - 1)})
    out.sort(key=lambda c: -c["score"])
    return out


def cmd_kister(folder: Path) -> int:
    windows = load_windows(folder / "tryk.jsonl")
    try:
        baseline = json.loads((folder / "baseline.json").read_text(encoding="utf-8")).get("tæller", {})
    except (OSError, ValueError):
        baseline = {}
    n = len(windows)
    print(f"{n} kiste-tryk optaget i {folder}")
    if n < 10:
        print("For få. Spil et par kampe og tryk F8 HVER gang du åbner en kiste (lige når den åbner).")
        print("HUD'en optager selv – der skal bare være mindst 10 tryk, gerne 30+.")
        return 1
    if not baseline:
        print("(baseline.json mangler – den gemmes hvert minut mens HUD'en kører. Resultatet er mindre sikkert.)")

    cands = analyze(windows, baseline)
    lines = []
    if not cands:
        lines += ["Ingen linje optræder ved mindst halvdelen af trykkene.",
                  "Konklusion: Fortnite skriver sandsynligvis ikke noget i loggen når du åbner en kiste.",
                  "Det er helt fint – F8 er den tæller der virker. Lad CHEST-mønstret være tomt."]
    else:
        best = cands[0]
        for i, c in enumerate(cands[:8], 1):
            lines.append(f"{i}. ved {c['share']:.0%} af trykkene, {c['per_press']:.1f}× pr. tryk i alt")
            lines.append(f"   {c['example'][:170]}")
        lines.append("")
        if best["share"] >= 0.8 and best["per_press"] <= 2.5:
            rx = suggest_regex(best["template"])
            hits = sum(1 for w in windows if any(re.search(rx, l, re.I) for l in w))
            lines += ["God kandidat (nr. 1). Indsæt i config.json under patterns:",
                      f'  "CHEST": [{json.dumps(rx)}]',
                      f"(mønstret rammer {hits} af {n} optagede tryk)",
                      "Når den virker: stop med at trykke F8 for kister, ellers tælles de dobbelt."]
        else:
            lines += ["Ingen sikker kandidat. Nr. 1 er for svag (skal være ved 80 %+ af trykkene",
                      "og højst ~2,5× pr. tryk). Optag flere tryk, eller bliv ved med F8."]
    print("\n".join(lines))
    (folder / "forslag.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nGemt i {folder / 'forslag.txt'}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tjek", help="kør mønstre over gemte logs")
    t.add_argument("--dir", default=str(default_log_dir()))
    t.add_argument("--config", default=str(HERE / "config.json"))
    k = sub.add_parser("kister", help="find en kiste-linje ud fra F8-tryk")
    k.add_argument("--dir", default=str(CALIB))
    args = ap.parse_args(argv)
    if args.cmd == "tjek":
        return cmd_tjek(Path(args.dir), Path(args.config), CALIB / "tjek.txt")
    return cmd_kister(Path(args.dir))


if __name__ == "__main__":
    sys.exit(main())
