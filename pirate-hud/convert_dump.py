#!/usr/bin/env python3
"""Lav spawns.json ud fra et dump af kiste-positioner.

    py convert_dump.py dump.json spawns.json --bounds MINX MAXX MINY MAXY
    py convert_dump.py dump.json spawns.json --bounds ... --swap-xy --flip-y

Forstår to formater:
  1) en liste af {"x": .., "y": .., "poi": "..", "type": "std|rare|buried"}
  2) en FModel-agtig JSON-eksport: objekter med "Type"/"Name" og en
     "RelativeLocation": {"X": .., "Y": ..} – direkte i "Properties" eller i den
     komponent "RootComponent" peger på. Kun objekter hvis Type/Name matcher
     --match (standard: Chest) tages med.

VIGTIGT om --bounds: Positionerne skal regnes om i forhold til HELE kortets kant,
ikke i forhold til kisterne selv (de ligger aldrig helt ude ved kanten). Den
gamle version brugte kisternes min/max, så alle punkter blev strakt ud over
kortet. Uden --bounds gør dette script det samme, men advarer.

Unreal-koordinater: på mange Fortnite-kort peger X mod nord og Y mod øst. Prøv
--swap-xy og --flip-y, og tjek mod et kendt landemærke, før du stoler på kortet.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


def _loc(props: dict):
    loc = props.get("RelativeLocation") if isinstance(props, dict) else None
    if isinstance(loc, dict) and "X" in loc and "Y" in loc:
        return float(loc["X"]), float(loc["Y"])
    return None


def _ref_parts(ref) -> tuple[str | None, str | None]:
    """"StaticMeshComponent'Chest_C_1.Root'" -> ("Chest_C_1", "Root")"""
    name = ref.get("ObjectName") if isinstance(ref, dict) else ref
    if not isinstance(name, str):
        return None, None
    m = re.search(r"'([^']+)'", name)
    path = (m.group(1) if m else name).split(":")[-1]
    parts = path.split(".")
    return (parts[-2] if len(parts) > 1 else None), parts[-1]


def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def extract_points(raw, match: str = "Chest") -> list[dict]:
    items = raw.get("spawns") or raw.get("objects") if isinstance(raw, dict) else raw
    if isinstance(items, list) and items and all(isinstance(o, dict) and "x" in o and "y" in o for o in items):
        return [{"x": float(o["x"]), "y": float(o["y"]), "poi": o.get("poi") or "ukendt",
                 "type": o.get("type", "std")} for o in items]

    objs = [o for o in _walk(raw) if isinstance(o.get("Name"), str)]
    by_outer_name = {(o.get("Outer"), o["Name"]): o for o in objs}
    by_name: dict[str, list] = {}
    for o in objs:
        by_name.setdefault(o["Name"], []).append(o)

    rx = re.compile(match, re.IGNORECASE)
    points = []
    for o in objs:
        label = f"{o.get('Type', '')} {o['Name']}"
        if not rx.search(label) or "Component" in str(o.get("Type", "")):
            continue
        props = o.get("Properties") or {}
        xy = _loc(props)
        if xy is None and "RootComponent" in props:
            outer, comp = _ref_parts(props["RootComponent"])
            target = by_outer_name.get((outer or o["Name"], comp))
            if target is None and len(by_name.get(comp, [])) == 1:
                target = by_name[comp][0]
            if target is not None:
                xy = _loc(target.get("Properties") or {})
        if xy is None:
            continue
        kind = "rare" if re.search(r"rare", label, re.I) else "buried" if re.search(r"bur+ied", label, re.I) else "std"
        points.append({"x": xy[0], "y": xy[1], "poi": "ukendt", "type": kind})
    return points


def convert(points: list[dict], bounds=None, swap_xy=False, flip_x=False, flip_y=False,
            cols=10, rows=10, map_name="") -> tuple[dict, list[str]]:
    warnings = []
    if not points:
        raise ValueError("ingen punkter fundet i dumpet")
    pts = [((p["y"], p["x"]) if swap_xy else (p["x"], p["y"]), p) for p in points]
    if bounds:
        minx, maxx, miny, maxy = bounds
    else:
        xs = [xy[0] for xy, _ in pts]
        ys = [xy[1] for xy, _ in pts]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        warnings.append("ingen --bounds: bruger kisternes egne yderpunkter, så kortet bliver strakt")
    sx, sy = (maxx - minx) or 1.0, (maxy - miny) or 1.0

    out = {"map": map_name, "example": False, "grid": {"cols": cols, "rows": rows}, "pois": [], "spawns": []}
    outside = 0
    for (x, y), p in pts:
        nx, ny = (x - minx) / sx, (y - miny) / sy
        if flip_x:
            nx = 1 - nx
        if flip_y:
            ny = 1 - ny
        if not (0 <= nx <= 1 and 0 <= ny <= 1):
            outside += 1
            continue
        col = min(cols - 1, int(nx * cols))
        row = min(rows - 1, int(ny * rows))
        out["spawns"].append({"poi": p["poi"], "grid": f"{chr(65 + col)}{row + 1}",
                              "nx": round(nx, 4), "ny": round(ny, 4), "type": p["type"]})
    if outside:
        warnings.append(f"{outside} punkter lå uden for --bounds og er sprunget over")
    counts = Counter(s["poi"] for s in out["spawns"])
    out["pois"] = [{"name": k, "std": v} for k, v in counts.most_common()]
    return out, warnings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--bounds", nargs=4, type=float, metavar=("MINX", "MAXX", "MINY", "MAXY"))
    ap.add_argument("--swap-xy", action="store_true")
    ap.add_argument("--flip-x", action="store_true")
    ap.add_argument("--flip-y", action="store_true")
    ap.add_argument("--match", default="Chest", help="regex for hvilke objekter der er kister")
    ap.add_argument("--map-name", default="")
    args = ap.parse_args(argv)

    raw = json.loads(Path(args.src).read_text(encoding="utf-8-sig"))
    points = extract_points(raw, args.match)
    if points:
        xs = [p["x"] for p in points]
        ys = [p["y"] for p in points]
        print(f"{len(points)} punkter. Rå x: {min(xs):.0f} … {max(xs):.0f}, y: {min(ys):.0f} … {max(ys):.0f}")
    try:
        out, warnings = convert(points, args.bounds, args.swap_xy, args.flip_x, args.flip_y,
                                map_name=args.map_name)
    except ValueError as e:
        print("Fejl:", e)
        return 1
    for w in warnings:
        print("Advarsel:", w)
    Path(args.dst).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Skrev {len(out['spawns'])} spawns -> {args.dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
