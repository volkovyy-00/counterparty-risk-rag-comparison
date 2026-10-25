"""Approach 3 - taxonomy-first extraction.

The LLM does one narrow job: label each risk factor in a window of Item 1A with a
fixed taxonomy category and leaf, plus a verbatim quote. Everything after that -
label validation, quote checking, the company x category matrix, the ranking and
the answer text - is plain Python (verify.py, answer.py), so it is repeatable
and auditable.

taxonomy-v3.x windows hold whole risk-factor sections ([RF n] heading + body, see
corpus.split_risk_factors) and ask for one label per section plus an unscored
`driver` note. taxonomy-v2.x keeps the fixed paragraph windows and its prompt unchanged.

    python src/approach3_taxonomy.py split-report   # -> results/taxonomy_split_report.md (no model call)
"""
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import config
import llm
import taxonomy
from corpus import chunk_text, pack_sections, split_check, split_risk_factors

_BASE = (
    "You are a credit risk analyst classifying the Risk Factors section (Item 1A) of a 10-K filing.\n"
    "For EVERY distinct risk factor in the excerpt (usually introduced by a heading sentence), return:\n"
    "- heading: the risk factor's heading or a 5-12 word paraphrase of it\n"
    "- category: the single best taxonomy category id\n"
    "- leaf: the single best leaf id within that category\n"
    "- quote: 15-50 words copied EXACTLY, character for character, from the excerpt, that justify the leaf\n"
    "A risk factor that clearly covers two leaves may be returned twice, once per leaf, each with its own quote.\n"
    "Do not merge different risk factors. Do not invent text. If the excerpt contains no risk factor, "
    "return an empty list."
)
_BASE_V3 = (
    "You are a credit risk analyst classifying the Risk Factors section (Item 1A) of a 10-K filing.\n"
    "The excerpt is cut into risk-factor sections. Each section starts with a marker line \"[RF n] <heading>\" "
    "(sometimes followed by \"Sub-caption: ...\"); the text after it, up to the next marker, is that risk factor.\n"
    "For each section return ONE item:\n"
    "- rf: the section number n from its marker\n"
    "- heading: the heading from the marker, copied as is\n"
    "- category, leaf: the single taxonomy category and leaf that best describe what this risk factor is about, "
    "judged from its heading and the main point of its text. Do not label topics the section mentions only in "
    "passing.\n"
    "- quote: 15-50 words copied EXACTLY, character for character, from that section's text (not from the "
    "marker line), that justify the leaf\n"
    "- driver: 1-5 words naming the concrete exposure, e.g. \"Taiwan foundry concentration\", \"gallium export "
    "restrictions\", \"IRA 45X credits\", \"UAW contract\". Required when the leaf is an OTHER leaf; otherwise "
    "give one when the text names something concrete, else \"\".\n"
    "- secondary: false\n"
    "Return a second item for the same section (secondary: true, with its own quote) only when the heading itself "
    "names two different risks. Never more than two items per section.\n"
    "Sections whose heading is in parentheses, e.g. \"(introduction)\", are preambles or summary lists: return "
    "nothing for them. For a section marked \"(part k/m)\" with k > 1 return nothing; part 1 carries the label.\n"
    "Do not invent text. If the excerpt contains no risk factor, return an empty list."
)
# Prompt versions are kept side by side so two recorded runs can be diffed (governance screen).
VERSIONS = {
    "taxonomy-v2.0": {"split": "fixed", "base": _BASE, "extra": ""},
    "taxonomy-v2.1": {"split": "fixed", "base": _BASE,
                      "extra": ("\nPrefer the most specific leaf that the quote supports. Use OTHER only when no other "
                                "category fits, and do not label a risk factor with a category it mentions only in "
                                "passing.")},
    "taxonomy-v3.0": {"split": "heading", "base": _BASE_V3, "extra": ""},
    "taxonomy-v3.1": {"split": "heading", "base": _BASE_V3,
                      "extra": ("\nPrefer the most specific leaf that the quote supports; use a broad leaf or OTHER "
                                "only when no narrower leaf fits.")},
}
PROMPT_VERSION = config.env("TAXO_PROMPT_VERSION", "taxonomy-v3.0")
if PROMPT_VERSION not in VERSIONS:
    raise SystemExit(f"TAXO_PROMPT_VERSION={PROMPT_VERSION!r}: use one of {', '.join(VERSIONS)}")
V3 = PROMPT_VERSION.startswith("taxonomy-v3")
SPLIT = config.TAXO_SPLIT or VERSIONS[PROMPT_VERSION]["split"]
if SPLIT not in ("heading", "fixed"):
    raise SystemExit(f"TAXO_SPLIT={SPLIT!r}: use heading or fixed")
if not V3 and SPLIT != "fixed":
    raise SystemExit(f"{PROMPT_VERSION} always uses TAXO_SPLIT=fixed, so its recorded runs stay reproducible")


def system(version=None):
    v = VERSIONS[version or PROMPT_VERSION]
    return v["base"] + v["extra"] + "\n\nTaxonomy (use only these ids):\n" + taxonomy.prompt_listing()


SYSTEM = system()

_ITEM = {"heading": {"type": "string"}, "category": {"type": "string", "enum": taxonomy.CATEGORY_IDS},
         "leaf": {"type": "string", "enum": taxonomy.LEAF_IDS}, "quote": {"type": "string"}}
if V3:
    _ITEM = {"rf": {"type": "integer"}, **_ITEM, "driver": {"type": "string"}, "secondary": {"type": "boolean"}}
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["risk_factors"],
    "properties": {
        "risk_factors": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": list(_ITEM),
                "properties": _ITEM,
            },
        }
    },
}


def split_filing(filing, method=None):
    """(windows, info) for one filing. windows: [(window_ref, text, [section idx, ...])].

    info: {method, reason, sections}. The heading split falls back to fixed windows (and says why) when
    corpus.split_check finds too few headings or an oversize section.
    """
    method, t, size = method or SPLIT, filing["ticker"], config.TAXO_WINDOW_CHARS
    info = {"method": method, "reason": None, "sections": []}
    if method == "heading":
        sections = split_risk_factors(filing["text"])
        info["reason"] = split_check(sections, size)
        if info["reason"] is None:
            info["sections"] = sections
            return [(f"{t}:w{n + 1}", w, idxs) for n, (w, idxs) in enumerate(pack_sections(sections, size))], info
        info["method"] = "fixed"
    return [(f"{t}:w{n + 1}", w, []) for n, (_, w) in enumerate(chunk_text(filing["text"], size, 0))], info


def windows_for(filing):
    """[(window_ref, text)] - the windows the model sees for this filing."""
    return [(ref, w) for ref, w, _ in split_filing(filing)[0]]


def _classify_window(filing, ref, window, idxs):
    user = (f"Company: {filing['company']} ({filing['ticker']}), 10-K accession {filing['accession']}.\n"
            f"Excerpt {ref}:\n\n{window}")
    with llm.METER.as_stage("taxonomy.build"):
        reply = llm.chat(SYSTEM, user, schema=SCHEMA, schema_name="risk_factors")
    out = []
    for rf in reply.get("risk_factors", []):
        n = rf.get("rf")
        claim = {"company": filing["ticker"], "category": rf.get("category", ""), "leaf": rf.get("leaf", ""),
                 "quote": rf.get("quote", ""), "risk": rf.get("heading", ""), "window_ref": ref,
                 "source_ref": f"{filing['ticker']}:rf{n}" if n in idxs else ref}
        if V3:
            claim.update(driver=(rf.get("driver") or "").strip(), secondary=bool(rf.get("secondary")), rf=n,
                         rf_unmapped=bool(idxs) and n not in idxs)  # an rf this window did not contain
        out.append(claim)
    return out


def _secondary_supported(leaf, heading):
    """A second label needs the heading itself to name two risks: keywords of two leaves, or an
    explicit pairing ('/' or 'and') next to keywords of this leaf."""
    found = taxonomy.leaves_for(heading)
    return leaf in found and (len(found) >= 2 or bool(re.search(r"/|\band\b", heading)))


def validate_v3(claims, sections):
    """Approach-3 label rules, applied in code. Sets `label_error` (verify.py rejects those as labels).

    sections: {source_ref: section dict} for the heading-split filings.
    """
    primary, secondary = set(), set()
    for c in claims:
        if c["leaf"].startswith("OTHER.") and not c.get("driver"):
            c["label_error"] = "OTHER label without a driver"
            continue
        sec = sections.get(c["source_ref"])
        if sec is None:  # fixed windows, or an rf the window did not contain
            continue
        key = c["source_ref"]
        if sec["heading"].startswith("("):
            c["label_error"] = f"label on {sec['heading']}, which is not a risk factor"
        elif c.get("secondary"):
            if not _secondary_supported(c["leaf"], sec["heading"]):
                c["label_error"] = "secondary label not supported by the heading"
            elif key in secondary:
                c["label_error"] = f"more than one secondary label for {key}"
            secondary.add(key)
        elif key in primary:
            c["label_error"] = f"second primary label for {key} (one label per risk factor)"
        else:
            primary.add(key)
    return claims


def run(question, filings):
    jobs, split_by_ticker, sections, sources = [], {}, {}, {}
    for f in filings:
        windows, info = split_filing(f)
        split_by_ticker[f["ticker"]] = {"method": info["method"], "reason": info["reason"],
                                        "sections": len(info["sections"]), "windows": len(windows)}
        for s in info["sections"]:
            ref = f"{f['ticker']}:rf{s['idx']}"
            sections[ref] = {k: s[k] for k in ("start", "end", "heading", "subcaption")}
            sources[ref] = s["text"]
        jobs += [(f, ref, w, idxs) for ref, w, idxs in windows]
        sources.update({ref: w for ref, w, _ in windows})
    claims = []
    with llm.METER.track("taxonomy.build"), ThreadPoolExecutor(config.LLM_CONCURRENCY) as pool:
        for out in pool.map(lambda job: _classify_window(*job), jobs):
            claims += out
    if V3:
        validate_v3(claims, sections)
    with llm.METER.track("taxonomy.ask"):  # no LLM call: the answer is computed from the verified claims
        pass
    return {
        "approach": "3_taxonomy_first",
        "summary": None,  # written by code from the verified claims (answer.finalise)
        "raw_claims": claims,
        "sources": sources,
        "stages": {"build": "taxonomy.build", "ask": "taxonomy.ask"},
        "details": {"windows_classified": len(jobs), "prompt_version": PROMPT_VERSION, "split": SPLIT,
                    "split_by_ticker": split_by_ticker, "sections": sections,
                    "rf_unmapped": sum(bool(c.get("rf_unmapped")) for c in claims),
                    "label_rule_rejections": sum("label_error" in c for c in claims)},
    }


# --------------------------------------------------------------------------- split report (no model call)
def split_report(filings, path=None):
    path = path or config.RESULTS_DIR / "taxonomy_split_report.md"
    size = config.TAXO_WINDOW_CHARS
    rows, totals = [], {"heading": 0, "fixed": 0}
    for f in filings:
        windows, info = split_filing(f, "heading")
        fixed = len(chunk_text(f["text"], size, 0))
        found = split_risk_factors(f["text"])
        largest = max(len(s["text"]) for s in found)
        heads = [s["heading"] for s in found if not s["heading"].startswith("(")][:3]
        totals["heading"] += len(windows)
        totals["fixed"] += fixed
        rows.append(f"| {f['ticker']} | {len(f['text']):,} | {sum(not s['heading'].startswith('(') for s in found)} | "
                    f"{len(windows)} | {fixed} | {largest:,} | **{info['method']}** | {info['reason'] or ''} | "
                    + ("<br>".join(h[:90].replace("|", "/") for h in heads) if info["method"] == "heading" else "-")
                    + " |")
    n_heading = sum("| **heading** |" in r for r in rows)
    run_in = [f["ticker"] for f in filings if "run into" in (split_filing(f, "heading")[1]["reason"] or "")]
    lines = [
        "# Approach 3: risk-factor split per filing", "",
        f"Corpus `{config.CORPUS}`, window {size:,} characters. Rules: `corpus.split_risk_factors` (plain line rules, "
        "no model call). A heading is a line of 6-60 words ending in a period and followed by a longer line; a "
        "sub-caption is a short line naming risks (\"Risks Related to ...\"). A filing falls back to the fixed "
        f"windows if it has fewer than 8 headings or a section over 3x the window.", "",
        f"**{n_heading} of {len(rows)} filings split by heading.** Windows sent to the model: "
        f"{totals['heading']} with this split vs {totals['fixed']} with the old fixed windows.", "",
        "| Ticker | Item 1A chars | Headings | Windows | Fixed windows | Largest section | Method | Fallback reason "
        "| First 3 headings |",
        "|---|---|---|---|---|---|---|---|---|", *rows, "",
    ] + ([f"Why {', '.join(run_in)} fall back: these 10-Ks set each heading in bold at the start of its first "
          "paragraph. The text extraction keeps the words but not the bold, so heading and body share one line and no "
          "rule can tell where the heading ends without guessing. They keep the fixed windows, which is what v2 used "
          "for every filing.", ""] if run_in else [])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
    return path


if __name__ == "__main__":
    if sys.argv[1:] != ["split-report"]:
        raise SystemExit("usage: python src/approach3_taxonomy.py split-report")
    from corpus import load_corpus

    print(f"-> {config.rel(split_report(load_corpus()))}")
