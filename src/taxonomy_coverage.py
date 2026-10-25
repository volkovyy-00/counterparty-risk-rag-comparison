"""Does the closed taxonomy already cover the group's four big drivers? No model call.

    python src/taxonomy_coverage.py      # -> results/taxonomy_coverage.md

For each driver: grep every Item 1A sentence for its terms, map each hit sentence onto a leaf with the
same keyword rules the verifier's fallback uses (taxonomy.leaves_for), and report where it lands for each
company. A company's mentions "fit" when at least half of its hit sentences can reach one of the
driver's fitting leaves (listed below) by keywords - the top-ranked leaf may differ when a sentence lists
several risks ("tariffs, export controls ..."); that is ambiguity, not a gap. A new leaf is justified
only if one driver lands in an ill-fitting leaf for 3 or more companies - and even then this script only
proposes it: taxonomy.yaml is edited by hand, after the owner agrees (a new leaf adds a column to the key).

Keyword mapping is a proxy for what a model would choose, not a measurement of it; the report says so.
"""
import re
from collections import Counter

import config
import taxonomy
from corpus import load_corpus

ILL_FIT_MIN_COMPANIES = 3
DRIVERS = {
    "Taiwan / geographic concentration": {
        "terms": ["taiwan", "tsmc", "geographic concentration", "geographically concentrated"],
        # Foundry concentration is a supply-concentration risk; landing in china_exposure lumps it with China.
        "fits": {"SUPPLY_CHAIN.outsourced_manufacturing", "SUPPLY_CHAIN.single_source"},
        "proposal": "GEOPOLITICAL_TRADE.taiwan_geographic_concentration",
    },
    "Export controls": {
        "terms": ["export control*", "export restriction*", "export licens*", "entity list", "bis",
                  "bureau of industry and security"],
        "fits": {"GEOPOLITICAL_TRADE.export_controls"},
    },
    "Critical minerals": {
        "terms": ["gallium", "germanium", "rare earth*", "lithium", "cobalt", "nickel", "critical mineral*"],
        "fits": {"COMMODITY_INPUTS.critical_minerals", "EMISSIONS_EV_TRANSITION.battery_supply_cost"},
    },
    "EV and chip incentives": {
        "terms": ["chips act", "chips and science", "inflation reduction act", "ira", "45x", "tax credit*",
                  "production credit*", "ev credit*"],
        "fits": {"REGULATION_LEGAL.government_incentives"},
    },
}


def _sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", " ".join(text.split())) if len(s) > 40]


def coverage(filings):
    out = {}
    for name, d in DRIVERS.items():
        patterns = [taxonomy._pattern(t) for t in d["terms"]]
        rows = []
        for f in filings:
            hits = [s for s in _sentences(f["text"]) if any(p.search(s) for p in patterns)]
            if not hits:
                continue
            leaves = [taxonomy.leaves_for(s) for s in hits]
            landing = Counter((lv or ["(no leaf)"])[0] for lv in leaves)
            top, n_top = landing.most_common(1)[0]
            reach = sum(bool(d["fits"] & set(lv)) for lv in leaves) / len(hits)
            rows.append({"ticker": f["ticker"], "sentences": len(hits), "leaf": top, "share": n_top / len(hits),
                         "reach": reach, "fits": reach >= 0.5, "landing": dict(landing.most_common(3)),
                         "example": min(hits, key=len)[:220]})
        ill = [r["ticker"] for r in rows if not r["fits"]]
        out[name] = {"rows": rows, "ill_fit": ill, "justified": len(ill) >= ILL_FIT_MIN_COMPANIES,
                     "fits": sorted(d["fits"]), "proposal": d.get("proposal")}
    return out


def report(cov, path=None):
    path = path or config.RESULTS_DIR / "taxonomy_coverage.md"
    justified = [n for n, c in cov.items() if c["justified"]]
    lines = ["# Taxonomy coverage of the group's drivers", "",
             f"Taxonomy v{taxonomy.VERSION} (sha256 `{taxonomy.SHA256[:12]}`), corpus `{config.CORPUS}`. "
             "Each Item 1A sentence that names a driver term is mapped onto a leaf by the taxonomy's keyword "
             "rules (`taxonomy.leaves_for`, the verifier's fallback). This is a proxy for where a model would put "
             "it, not a measurement. No model call.", "",
             f"**New leaf justified: {'YES' if justified else 'NO'}.** Rule: a driver landing in an ill-fitting "
             f"leaf for {ILL_FIT_MIN_COMPANIES} or more companies. "
             + (f"Triggered by: {', '.join(justified)}. Proposal below; taxonomy.yaml is NOT edited until the "
                "owner agrees (one new leaf = one more answer-key column of 10 cells, and taxonomy version 3)."
                if justified else "The existing leaves take every driver; the v3 `driver` note carries the detail."),
             ""]
    near = {n: c["ill_fit"] for n, c in cov.items() if c["ill_fit"] and not c["justified"]}
    for n, tickers in near.items():
        lines += [f"Near miss: **{n}** lands badly for {', '.join(tickers)} only ({len(tickers)} < "
                  f"{ILL_FIT_MIN_COMPANIES}). Under taxonomy-v3 these sections keep their closest leaf and the "
                  "`driver` note names the exposure (e.g. \"Taiwan foundry concentration\"); review the drivers after "
                  "the A/B before adding a leaf.", ""]
    for name, c in cov.items():
        lines += [f"## {name}", "",
                  f"Fitting leaves: {', '.join(f'`{x}`' for x in c['fits'])}. Companies mentioning it: "
                  f"{len(c['rows'])} of {len(config.TICKERS)}. Ill-fitting landings: "
                  f"{len(c['ill_fit'])} ({', '.join(c['ill_fit']) or 'none'}).", "",
                  "| Ticker | Sentences | Top leaf (share) | Reaches a fitting leaf | Fits | Also | Shortest example |",
                  "|---|---|---|---|---|---|---|"]
        for r in c["rows"]:
            also = ", ".join(f"{k} {v}" for k, v in list(r["landing"].items())[1:])
            lines.append(f"| {r['ticker']} | {r['sentences']} | `{r['leaf']}` ({r['share']:.0%}) | {r['reach']:.0%} | "
                         f"{'yes' if r['fits'] else '**no**'} | {also} | {r['example'].replace('|', '/')} |")
        if c["justified"] and c["proposal"]:
            lines += ["", f"**Proposed leaf (not added):** `{c['proposal']}`: dependence on one geography, chiefly "
                      "Taiwan foundries and assembly, for supply. It would split this out of `china_exposure`, "
                      "which today covers China sales, supply and operations together with Taiwan."]
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
    return path


if __name__ == "__main__":
    cov = coverage(load_corpus())
    print(f"-> {config.rel(report(cov))}")
    for name, c in cov.items():
        print(f"  {name}: {len(c['rows'])} companies, ill-fitting {c['ill_fit'] or 'none'}"
              f"{'  -> new leaf justified' if c['justified'] else ''}")
