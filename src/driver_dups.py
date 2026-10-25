"""Near-duplicate ExposureDrivers in a graph-v2 snapshot, with proposed aliases (no model call, writes no config).

    python src/driver_dups.py                          # the current build snapshot
    python src/driver_dups.py --snapshot FILE          # e.g. the A/B graph

Pairs of the same type whose names are near-identical ("critical minerals" / "critical materials") or where one
name's words are a subset of the other's with the same last word ("minerals" / "critical minerals"). The output is
a proposal for config/graph_aliases.yaml; nothing is added without the author's approval.
"""
import argparse
import json
from pathlib import Path

from rapidfuzz import fuzz

import config
from graph_resolve import normalise_name

RATIO = 80  # 'critical minerals' / 'critical materials' scores 84.8


def _stem(word):
    return word[:-1] if word.endswith("s") and len(word) > 3 else word


def _words(name):
    return [_stem(w) for w in normalise_name(name).split()]


def near(a, b):
    """'spelling' (near-identical), 'subset' (one name's words inside the other's, same last word) or None."""
    wa, wb = _words(a), _words(b)
    if wa == wb or fuzz.ratio(" ".join(wa), " ".join(wb)) >= RATIO:
        return "spelling"
    small, big = sorted((wa, wb), key=len)
    return "subset" if small and small[-1] == big[-1] and set(small) < set(big) else None


def groups(drivers):
    """Near-duplicates per type: 'spelling' groups (proposed aliases) and 'subset' pairs (for review only)."""
    spelling, subset = [], []
    for typ in sorted({d["type"] for d in drivers}):
        ds = [d for d in drivers if d["type"] == typ]
        parent = list(range(len(ds)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for i in range(len(ds)):
            for j in range(i + 1, len(ds)):
                kind = near(ds[i]["name"], ds[j]["name"])
                if kind == "spelling":
                    parent[find(i)] = find(j)
                elif kind == "subset":
                    pair = sorted((ds[i], ds[j]), key=lambda d: len(d["name"]))
                    subset.append({"type": typ, "names": [d["name"] for d in pair],
                                   "tickers": sorted({t for d in pair for t in d["tickers"]})})
        by = {}
        for i, d in enumerate(ds):
            by.setdefault(find(i), []).append(d)
        for g in by.values():
            if len(g) > 1:
                g.sort(key=lambda d: (-len(d["tickers"]), len(d["name"]), d["name"]))
                spelling.append({"type": typ, "canonical": g[0]["name"], "names": [d["name"] for d in g],
                                 "tickers": sorted({t for d in g for t in d["tickers"]})})
    order = lambda g: (-len(g["tickers"]), g["names"])  # noqa: E731
    return sorted(spelling, key=order), sorted(subset, key=order)


def report(gs, source):
    spelling, subset = gs
    lines = [f"# Near-duplicate ExposureDrivers – {source}", "",
             "Proposal only: nothing below is in config/graph_aliases.yaml until the author approves it.", "",
             "## Same driver, different spelling (proposed aliases)", "",
             "| Type | Names | Companies together |", "|---|---|---|"]
    lines += [f"| {g['type']} | {' / '.join(g['names'])} | {', '.join(g['tickers'])} |" for g in spelling]
    lines += ["", "```yaml"]
    lines += [f"{g['canonical']}: [{', '.join(n for n in g['names'] if n != g['canonical'])}]" for g in spelling]
    lines += ["```", "", "## Broader and narrower name (review; no alias proposed)", "",
              "One name's words sit inside the other's. They may be different drivers (\"conflict-free minerals\" is a",
              "disclosure rule; \"minerals\" is an input).", "", "| Type | Broader | Narrower | Companies together |",
              "|---|---|---|---|"]
    lines += [f"| {g['type']} | {g['names'][0]} | {g['names'][1]} | {', '.join(g['tickers'])} |" for g in subset]
    return "\n".join(lines)


def main():
    from approach2_graphrag import snapshot_path

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", help="default: the current graph-v2 build snapshot")
    parser.add_argument("--out", help="also write the report here (markdown)")
    args = parser.parse_args()
    path = Path(args.snapshot) if args.snapshot else snapshot_path()
    gs = groups(json.loads(path.read_text())["drivers"])
    text = report(gs, config.rel(path))
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
